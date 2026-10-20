/*
 * RAM-only broker and device configuration for the RT-Spark MQTT commands.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <rtthread.h>

#include <lwip/inet.h>
#include <lwip/ip4_addr.h>
#include <lwip/netdb.h>
#include <lwip/sockets.h>

#ifdef RT_USING_FINSH
#include <finsh.h>
#endif

#include "mqtt_config.h"

#define MQTT_CONFIG_CLIENT_PREFIX "bca152-"

static struct mqtt_config_values mqtt_config_current =
{
    MQTT_CONFIG_DEFAULT_BROKER_HOST,
    MQTT_CONFIG_DEFAULT_BROKER_PORT,
    MQTT_CONFIG_DEFAULT_DEVICE_ID
};
static rt_bool_t mqtt_config_stream_active;

static rt_bool_t mqtt_config_validate_host(const char *host)
{
    rt_size_t length;
    rt_size_t label_length = 0U;
    rt_size_t index;
    rt_bool_t numeric_ipv4 = RT_TRUE;
    rt_uint32_t dot_count = 0U;

    if (host == RT_NULL)
    {
        return RT_FALSE;
    }

    length = rt_strlen(host);
    if ((length == 0U) || (length >= MQTT_CONFIG_BROKER_HOST_SIZE) ||
        (length > 253U))
    {
        return RT_FALSE;
    }

    for (index = 0U; index < length; index++)
    {
        char character = host[index];

        if ((character >= '0') && (character <= '9'))
        {
            continue;
        }
        if (character == '.')
        {
            dot_count++;
            continue;
        }
        numeric_ipv4 = RT_FALSE;
    }

    if (numeric_ipv4)
    {
        ip4_addr_t parsed_address;

        return (dot_count == 3U) &&
               (ip4addr_aton(host, &parsed_address) != 0);
    }

    for (index = 0U; index < length; index++)
    {
        char character = host[index];

        if (character == '.')
        {
            if ((label_length == 0U) || (host[index - 1U] == '-') ||
                (label_length > 63U))
            {
                return RT_FALSE;
            }
            label_length = 0U;
            continue;
        }

        if (!(((character >= 'a') && (character <= 'z')) ||
              ((character >= 'A') && (character <= 'Z')) ||
              ((character >= '0') && (character <= '9')) ||
              (character == '-')))
        {
            return RT_FALSE;
        }
        if ((label_length == 0U) && (character == '-'))
        {
            return RT_FALSE;
        }
        label_length++;
        if (label_length > 63U)
        {
            return RT_FALSE;
        }
    }

    return (label_length > 0U) && (host[length - 1U] != '-');
}

static rt_bool_t mqtt_config_validate_device_id(const char *device_id)
{
    rt_size_t length;
    rt_size_t index;

    if (device_id == RT_NULL)
    {
        return RT_FALSE;
    }

    length = rt_strlen(device_id);
    if ((length == 0U) || (length >= MQTT_CONFIG_DEVICE_ID_SIZE))
    {
        return RT_FALSE;
    }

    for (index = 0U; index < length; index++)
    {
        char character = device_id[index];
        rt_bool_t alphanumeric =
            (((character >= 'a') && (character <= 'z')) ||
             ((character >= 'A') && (character <= 'Z')) ||
             ((character >= '0') && (character <= '9')));

        if (!alphanumeric && (character != '-') && (character != '_') &&
            (character != '.'))
        {
            return RT_FALSE;
        }
        if (((index == 0U) || (index == length - 1U)) && !alphanumeric)
        {
            return RT_FALSE;
        }
    }

    return RT_TRUE;
}

void mqtt_config_get(struct mqtt_config_values *values)
{
    if (values == RT_NULL)
    {
        return;
    }

    rt_enter_critical();
    rt_memcpy(values, &mqtt_config_current, sizeof(*values));
    rt_exit_critical();
}

rt_err_t mqtt_config_set_broker(const char *host)
{
    rt_size_t length;

    if (!mqtt_config_validate_host(host))
    {
        return -RT_EINVAL;
    }

    length = rt_strlen(host);
    rt_enter_critical();
    if (mqtt_config_stream_active)
    {
        rt_exit_critical();
        return -RT_EBUSY;
    }
    rt_memset(mqtt_config_current.broker_host, 0,
              sizeof(mqtt_config_current.broker_host));
    rt_memcpy(mqtt_config_current.broker_host, host, length);
    rt_exit_critical();

    return RT_EOK;
}

rt_err_t mqtt_config_set_port(rt_uint16_t port)
{
    if (port == 0U)
    {
        return -RT_EINVAL;
    }

    rt_enter_critical();
    if (mqtt_config_stream_active)
    {
        rt_exit_critical();
        return -RT_EBUSY;
    }
    mqtt_config_current.broker_port = port;
    rt_exit_critical();

    return RT_EOK;
}

rt_err_t mqtt_config_set_device_id(const char *device_id)
{
    rt_size_t length;

    if (!mqtt_config_validate_device_id(device_id))
    {
        return -RT_EINVAL;
    }

    length = rt_strlen(device_id);
    rt_enter_critical();
    if (mqtt_config_stream_active)
    {
        rt_exit_critical();
        return -RT_EBUSY;
    }
    rt_memset(mqtt_config_current.device_id, 0,
              sizeof(mqtt_config_current.device_id));
    rt_memcpy(mqtt_config_current.device_id, device_id, length);
    rt_exit_critical();

    return RT_EOK;
}

rt_err_t mqtt_config_make_client_id(const struct mqtt_config_values *values,
                                    enum mqtt_config_client_role role,
                                    char *destination,
                                    rt_size_t destination_size)
{
    const char *suffix;
    int result;

    if ((values == RT_NULL) || (destination == RT_NULL) ||
        (destination_size == 0U) ||
        !mqtt_config_validate_device_id(values->device_id))
    {
        return -RT_EINVAL;
    }

    if (role == MQTT_CONFIG_CLIENT_TEST)
    {
        suffix = "-test";
    }
    else if (role == MQTT_CONFIG_CLIENT_STREAM)
    {
        suffix = "-stream";
    }
    else
    {
        return -RT_EINVAL;
    }

    result = rt_snprintf(destination, destination_size, MQTT_CONFIG_CLIENT_PREFIX
                         "%s%s", values->device_id, suffix);
    if ((result <= 0) || ((rt_size_t)result >= destination_size))
    {
        destination[0] = '\0';
        return -RT_EINVAL;
    }

    return RT_EOK;
}

/*
 * lwIP getaddrinfo handles numeric IPv4 literals directly and uses its
 * configured DNS resolver for hostnames. DNS retries are bounded by lwIP.
 */
int mqtt_config_resolve_ipv4(const char *host, rt_uint32_t *address)
{
    struct addrinfo hints;
    struct addrinfo *result = RT_NULL;
    int resolve_result;

    if (!mqtt_config_validate_host(host) || (address == RT_NULL))
    {
        return EAI_NONAME;
    }

    rt_memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    resolve_result = lwip_getaddrinfo(host, RT_NULL, &hints, &result);
    if ((resolve_result != 0) || (result == RT_NULL) ||
        (result->ai_addr == RT_NULL) ||
        (result->ai_addrlen < sizeof(struct sockaddr_in)) ||
        (result->ai_family != AF_INET))
    {
        if (result != RT_NULL)
        {
            lwip_freeaddrinfo(result);
        }
        return (resolve_result != 0) ? resolve_result : EAI_FAIL;
    }

    *address = ((struct sockaddr_in *)result->ai_addr)->sin_addr.s_addr;
    lwip_freeaddrinfo(result);
    return 0;
}

void mqtt_config_set_stream_active(rt_bool_t active)
{
    rt_enter_critical();
    mqtt_config_stream_active = active;
    rt_exit_critical();
}

#ifdef RT_USING_FINSH
static rt_bool_t mqtt_config_parse_port(const char *text, rt_uint16_t *port)
{
    rt_uint32_t value = 0U;
    const char *cursor = text;

    if ((cursor == RT_NULL) || (*cursor == '\0') || (port == RT_NULL))
    {
        return RT_FALSE;
    }

    while (*cursor != '\0')
    {
        rt_uint32_t digit;

        if ((*cursor < '0') || (*cursor > '9'))
        {
            return RT_FALSE;
        }
        digit = (rt_uint32_t)(*cursor - '0');
        if (value > (65535U - digit) / 10U)
        {
            return RT_FALSE;
        }
        value = value * 10U + digit;
        cursor++;
    }

    if ((value == 0U) || (value > 65535U))
    {
        return RT_FALSE;
    }

    *port = (rt_uint16_t)value;
    return RT_TRUE;
}

static void mqtt_config(int argc, char **argv)
{
    struct mqtt_config_values values;
    rt_err_t result;

    if ((argc == 2) && (rt_strcmp(argv[1], "show") == 0))
    {
        char test_client_id[MQTT_CONFIG_CLIENT_ID_SIZE];
        char stream_client_id[MQTT_CONFIG_CLIENT_ID_SIZE];

        mqtt_config_get(&values);
        if ((mqtt_config_make_client_id(&values, MQTT_CONFIG_CLIENT_TEST,
                                        test_client_id, sizeof(test_client_id)) != RT_EOK) ||
            (mqtt_config_make_client_id(&values, MQTT_CONFIG_CLIENT_STREAM,
                                        stream_client_id, sizeof(stream_client_id)) != RT_EOK))
        {
            rt_kprintf("mqtt_config: unable to derive client IDs from current settings.\r\n");
            return;
        }
        rt_kprintf("MQTT broker: %s:%u\r\n", values.broker_host,
                   (unsigned int)values.broker_port);
        rt_kprintf("Device ID: %s\r\n", values.device_id);
        rt_kprintf("Client IDs: test=%s stream=%s\r\n",
                   test_client_id, stream_client_id);
        rt_kprintf("Storage: RAM only; settings reset to development defaults after reboot.\r\n");
        return;
    }

    if ((argc == 4) && (rt_strcmp(argv[1], "set") == 0))
    {
        if (rt_strcmp(argv[2], "broker") == 0)
        {
            result = mqtt_config_set_broker(argv[3]);
            if (result == RT_EOK)
            {
                rt_kprintf("MQTT broker host set to %s.\r\n", argv[3]);
                return;
            }
            if (result == -RT_EBUSY)
            {
                rt_kprintf("mqtt_config: stop mqtt_stream before changing configuration.\r\n");
                return;
            }
            rt_kprintf("mqtt_config: invalid hostname or IPv4 address (maximum %u characters).\r\n",
                       (unsigned int)(MQTT_CONFIG_BROKER_HOST_SIZE - 1U));
            return;
        }

        if (rt_strcmp(argv[2], "port") == 0)
        {
            rt_uint16_t port;

            if (!mqtt_config_parse_port(argv[3], &port))
            {
                rt_kprintf("mqtt_config: port must be a decimal integer from 1 to 65535.\r\n");
                return;
            }
            result = mqtt_config_set_port(port);
            if (result == RT_EOK)
            {
                rt_kprintf("MQTT broker port set to %u.\r\n", (unsigned int)port);
                return;
            }
            rt_kprintf("mqtt_config: stop mqtt_stream before changing configuration.\r\n");
            return;
        }

        if (rt_strcmp(argv[2], "device_id") == 0)
        {
            result = mqtt_config_set_device_id(argv[3]);
            if (result == RT_EOK)
            {
                rt_kprintf("MQTT device ID set to %s.\r\n", argv[3]);
                return;
            }
            if (result == -RT_EBUSY)
            {
                rt_kprintf("mqtt_config: stop mqtt_stream before changing configuration.\r\n");
                return;
            }
            rt_kprintf("mqtt_config: device ID must be 1-%u characters using letters, digits, '.', '_' or '-'.\r\n",
                       (unsigned int)(MQTT_CONFIG_DEVICE_ID_SIZE - 1U));
            return;
        }
    }

    rt_kprintf("Usage: mqtt_config show | set broker HOST | set port PORT | set device_id ID\r\n");
}
MSH_CMD_EXPORT(mqtt_config, show or set RAM-only MQTT connection configuration);
#endif /* RT_USING_FINSH */
