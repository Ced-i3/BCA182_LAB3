/*
 * MQTT 3.1.1 socket helpers, one-shot connectivity test, and manually started
 * motion publisher. Motion data uses a static bounded queue and a separate
 * low-priority thread; no network work runs in the sensor acquisition loop.
 */

#include <rtthread.h>

#ifdef RT_USING_FINSH
#include <finsh.h>
#include <errno.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>
#include <lwip/inet.h>
#include <lwip/sockets.h>
#include <dev_wlan_mgnt.h>

#include "mqtt_config.h"
#include "motion_mqtt.h"
#include "time_sync.h"

#define MQTT_TEST_CONNECT_TIMEOUT_MS     3000
#define MQTT_TEST_OPERATION_TIMEOUT_MS   3000
#define MQTT_TEST_DISCONNECT_TIMEOUT_MS  500
#define MQTT_TEST_PACKET_CAPACITY         128
#define MQTT_TEST_PACKET_ID               1

#define MQTT_STREAM_TOPIC                 "lab3/sensors/motion"
#define MQTT_STREAM_PUBLISH_RATE_DEFAULT  5U
#define MQTT_STREAM_QUEUE_CAPACITY        10U
#define MQTT_STREAM_STACK_SIZE            4096U
#define MQTT_STREAM_THREAD_PRIORITY       20U
#define MQTT_STREAM_CONNECT_TIMEOUT_MS    3000U
#define MQTT_STREAM_OPERATION_TIMEOUT_MS  2000U
#define MQTT_STREAM_DISCONNECT_TIMEOUT_MS 250U
#define MQTT_STREAM_QUEUE_WAIT_MS         100U
#define MQTT_STREAM_STOP_TIMEOUT_MS       8000U
#define MQTT_STREAM_KEEPALIVE_SECONDS      20U
#define MQTT_STREAM_DIAGNOSTIC_SECONDS     10U
#define MQTT_STREAM_BACKOFF_INITIAL_MS    1000U
#define MQTT_STREAM_BACKOFF_MAX_MS       30000U
#define MQTT_STREAM_PACKET_CAPACITY        320U
#define MQTT_STREAM_SAMPLE_RATE_HZ         25U

/* milli-(m/s^2) per raw accel count and milli-(rad/s) per gyro count */
#define MQTT_ACCEL_MILLI_NUMERATOR       980665LL
#define MQTT_ACCEL_MILLI_DENOMINATOR     819200LL
#define MQTT_GYRO_MILLI_NUMERATOR        3141593LL
#define MQTT_GYRO_MILLI_DENOMINATOR      11790000LL

static const char mqtt_test_topic[] = "lab3/test/connectivity";
static const char mqtt_test_payload[] = "rt-spark MQTT connectivity test";

static rt_tick_t mqtt_deadline(rt_uint32_t timeout_ms)
{
    return rt_tick_get() + rt_tick_from_millisecond((rt_int32_t)timeout_ms);
}

/* Return RT_EOK when ready, otherwise set error_code to errno/ETIMEDOUT. */
static rt_err_t mqtt_wait_socket(int sock, rt_bool_t write_ready,
                                 rt_bool_t watch_exception,
                                 rt_tick_t deadline, int *error_code)
{
    for (;;)
    {
        rt_int32_t remaining_ticks;
        struct timeval timeout;
        fd_set read_set;
        fd_set write_set;
        fd_set exception_set;
        int result;

        remaining_ticks = (rt_int32_t)(deadline - rt_tick_get());
        if (remaining_ticks <= 0)
        {
            *error_code = ETIMEDOUT;
            return -RT_ETIMEOUT;
        }

        timeout.tv_sec = remaining_ticks / RT_TICK_PER_SECOND;
        timeout.tv_usec = ((remaining_ticks % RT_TICK_PER_SECOND) * 1000000) /
                          RT_TICK_PER_SECOND;
        if (timeout.tv_sec == 0 && timeout.tv_usec == 0)
        {
            timeout.tv_usec = 1;
        }

        FD_ZERO(&read_set);
        FD_ZERO(&write_set);
        FD_ZERO(&exception_set);
        if (write_ready)
        {
            FD_SET(sock, &write_set);
        }
        else
        {
            FD_SET(sock, &read_set);
        }
        if (watch_exception)
        {
            FD_SET(sock, &exception_set);
        }

        result = lwip_select(sock + 1, &read_set, &write_set,
                             &exception_set, &timeout);
        if (result < 0)
        {
            *error_code = (int)rt_get_errno();
            if (*error_code == EINTR)
            {
                continue;
            }
            return -RT_ERROR;
        }
        if (result == 0)
        {
            continue;
        }
        if (watch_exception && FD_ISSET(sock, &exception_set))
        {
            return RT_EOK;
        }
        if ((write_ready && FD_ISSET(sock, &write_set)) ||
            (!write_ready && FD_ISSET(sock, &read_set)))
        {
            return RT_EOK;
        }
    }
}

static rt_err_t mqtt_send_all(int sock, const rt_uint8_t *data,
                              rt_size_t length, rt_tick_t deadline,
                              int *error_code)
{
    rt_size_t sent = 0;

    while (sent < length)
    {
        int result;

        if (mqtt_wait_socket(sock, RT_TRUE, RT_FALSE, deadline,
                             error_code) != RT_EOK)
        {
            return -RT_ERROR;
        }

        result = lwip_send(sock, data + sent, length - sent, 0);
        if (result > 0)
        {
            sent += (rt_size_t)result;
            continue;
        }
        if (result == 0)
        {
            *error_code = EPIPE;
            return -RT_ERROR;
        }

        *error_code = (int)rt_get_errno();
        if (*error_code == EINTR || *error_code == EWOULDBLOCK ||
            *error_code == EAGAIN)
        {
            continue;
        }
        return -RT_ERROR;
    }

    return RT_EOK;
}

static rt_err_t mqtt_receive_exact(int sock, rt_uint8_t *data,
                                   rt_size_t length, rt_tick_t deadline,
                                   int *error_code)
{
    rt_size_t received = 0;

    while (received < length)
    {
        int result;

        if (mqtt_wait_socket(sock, RT_FALSE, RT_FALSE, deadline,
                             error_code) != RT_EOK)
        {
            return -RT_ERROR;
        }

        result = lwip_recv(sock, data + received, length - received, 0);
        if (result > 0)
        {
            received += (rt_size_t)result;
            continue;
        }
        if (result == 0)
        {
            *error_code = ECONNRESET;
            return -RT_ERROR;
        }

        *error_code = (int)rt_get_errno();
        if (*error_code == EINTR || *error_code == EWOULDBLOCK ||
            *error_code == EAGAIN)
        {
            continue;
        }
        return -RT_ERROR;
    }

    return RT_EOK;
}

static rt_size_t mqtt_encode_remaining_length(rt_uint32_t remaining,
                                              rt_uint8_t *destination)
{
    rt_size_t count = 0;

    do
    {
        rt_uint8_t digit = (rt_uint8_t)(remaining % 128);
        remaining /= 128;
        if (remaining > 0)
        {
            digit |= 0x80;
        }
        destination[count++] = digit;
    } while (remaining > 0 && count < 4);

    return count;
}

static rt_size_t mqtt_test_build_connect(rt_uint8_t *packet,
                                         rt_size_t capacity,
                                         const char *client_id)
{
    rt_size_t client_id_length;
    rt_uint32_t remaining_length;
    rt_size_t offset = 0;

    if ((packet == RT_NULL) || (client_id == RT_NULL))
    {
        return 0;
    }
    client_id_length = rt_strlen(client_id);
    remaining_length = 12U + (rt_uint32_t)client_id_length;

    if (capacity < 2U + remaining_length || client_id_length > 0xFFFFU)
    {
        return 0;
    }

    packet[offset++] = 0x10; /* CONNECT */
    offset += mqtt_encode_remaining_length(remaining_length, packet + offset);
    packet[offset++] = 0x00;
    packet[offset++] = 0x04;
    rt_memcpy(packet + offset, "MQTT", 4);
    offset += 4;
    packet[offset++] = 0x04; /* MQTT 3.1.1 */
    packet[offset++] = 0x02; /* clean session; no credentials or will */
    packet[offset++] = 0x00;
    packet[offset++] = 0x0A; /* keep alive: 10 seconds */
    packet[offset++] = (rt_uint8_t)(client_id_length >> 8);
    packet[offset++] = (rt_uint8_t)client_id_length;
    rt_memcpy(packet + offset, client_id, client_id_length);
    offset += client_id_length;

    return offset;
}

static rt_size_t mqtt_test_build_publish(rt_uint8_t *packet,
                                         rt_size_t capacity)
{
    rt_size_t topic_length = sizeof(mqtt_test_topic) - 1;
    rt_size_t payload_length = sizeof(mqtt_test_payload) - 1;
    rt_uint32_t remaining_length = 2 + (rt_uint32_t)topic_length + 2 +
                                   (rt_uint32_t)payload_length;
    rt_size_t offset = 0;

    if (topic_length > 0xFFFF || payload_length > 0xFFFF ||
        capacity < 6 + remaining_length)
    {
        return 0;
    }

    packet[offset++] = 0x32; /* PUBLISH, QoS 1, not retained */
    offset += mqtt_encode_remaining_length(remaining_length, packet + offset);
    packet[offset++] = (rt_uint8_t)(topic_length >> 8);
    packet[offset++] = (rt_uint8_t)topic_length;
    rt_memcpy(packet + offset, mqtt_test_topic, topic_length);
    offset += topic_length;
    packet[offset++] = (rt_uint8_t)(MQTT_TEST_PACKET_ID >> 8);
    packet[offset++] = (rt_uint8_t)MQTT_TEST_PACKET_ID;
    rt_memcpy(packet + offset, mqtt_test_payload, payload_length);
    offset += payload_length;

    return offset;
}

static void mqtt_test(int argc, char **argv)
{
    static const rt_uint8_t disconnect_packet[] = {0xE0, 0x00};
    rt_uint8_t packet[MQTT_TEST_PACKET_CAPACITY];
    rt_uint8_t response[4];
    rt_uint32_t nonblocking = 1;
    rt_size_t packet_length;
    int sock = -1;
    int error_code = 0;
    int result;
    int socket_error = 0;
    socklen_t option_length;
    rt_bool_t mqtt_connected = RT_FALSE;
    struct sockaddr_in server_address;
    struct mqtt_config_values config;
    rt_uint32_t broker_address;
    char client_id[MQTT_CONFIG_CLIENT_ID_SIZE];
    int resolve_result;

    if (argc != 1)
    {
        rt_kprintf("Usage: mqtt_test\r\n");
        return;
    }

    mqtt_config_get(&config);
    if (mqtt_config_make_client_id(&config, MQTT_CONFIG_CLIENT_TEST,
                                   client_id, sizeof(client_id)) != RT_EOK)
    {
        rt_kprintf("MQTT test FAIL: invalid device ID configuration.\r\n");
        return;
    }

    rt_kprintf("MQTT test: connecting to %s:%u (timeout %u ms)...\r\n",
               config.broker_host, (unsigned int)config.broker_port,
               MQTT_TEST_CONNECT_TIMEOUT_MS);

    resolve_result = mqtt_config_resolve_ipv4(config.broker_host, &broker_address);
    if (resolve_result != 0)
    {
        rt_kprintf("MQTT test FAIL: resolving broker host %s failed (lwIP error=%d).\r\n",
                   config.broker_host, resolve_result);
        return;
    }

    sock = lwip_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock < 0)
    {
        rt_kprintf("MQTT test FAIL: socket errno=%d\r\n", (int)rt_get_errno());
        return;
    }

    if (lwip_ioctl(sock, FIONBIO, &nonblocking) < 0)
    {
        error_code = (int)rt_get_errno();
        rt_kprintf("MQTT test FAIL: nonblocking setup errno=%d\r\n", error_code);
        goto cleanup;
    }

    rt_memset(&server_address, 0, sizeof(server_address));
    server_address.sin_family = AF_INET;
    server_address.sin_port = lwip_htons(config.broker_port);
    server_address.sin_addr.s_addr = broker_address;

    result = lwip_connect(sock, (const struct sockaddr *)&server_address,
                          sizeof(server_address));
    if (result < 0)
    {
        error_code = (int)rt_get_errno();
        if (error_code != EINPROGRESS && error_code != EALREADY &&
            error_code != EWOULDBLOCK)
        {
            rt_kprintf("MQTT test FAIL: TCP connect errno=%d\r\n", error_code);
            goto cleanup;
        }

        if (mqtt_wait_socket(sock, RT_TRUE, RT_TRUE,
                             mqtt_deadline(MQTT_TEST_CONNECT_TIMEOUT_MS),
                             &error_code) != RT_EOK)
        {
            rt_kprintf("MQTT test FAIL: TCP connect errno=%d\r\n", error_code);
            goto cleanup;
        }

        option_length = sizeof(socket_error);
        if (lwip_getsockopt(sock, SOL_SOCKET, SO_ERROR, &socket_error,
                            &option_length) < 0)
        {
            error_code = (int)rt_get_errno();
            rt_kprintf("MQTT test FAIL: connect completion errno=%d\r\n", error_code);
            goto cleanup;
        }
        if (socket_error != 0)
        {
            rt_kprintf("MQTT test FAIL: TCP connect errno=%d\r\n", socket_error);
            goto cleanup;
        }
    }

    packet_length = mqtt_test_build_connect(packet, sizeof(packet), client_id);
    if (packet_length == 0)
    {
        rt_kprintf("MQTT test FAIL: could not build CONNECT packet\r\n");
        goto cleanup;
    }
    if (mqtt_send_all(sock, packet, packet_length,
                      mqtt_deadline(MQTT_TEST_OPERATION_TIMEOUT_MS),
                      &error_code) != RT_EOK)
    {
        rt_kprintf("MQTT test FAIL: sending CONNECT errno=%d\r\n", error_code);
        goto cleanup;
    }
    if (mqtt_receive_exact(sock, response, sizeof(response),
                           mqtt_deadline(MQTT_TEST_OPERATION_TIMEOUT_MS),
                           &error_code) != RT_EOK)
    {
        rt_kprintf("MQTT test FAIL: waiting for CONNACK errno=%d\r\n", error_code);
        goto cleanup;
    }
    if (response[0] != 0x20 || response[1] != 0x02 || response[2] != 0x00)
    {
        rt_kprintf("MQTT test FAIL: malformed CONNACK (%02x %02x %02x %02x)\r\n",
                   response[0], response[1], response[2], response[3]);
        goto cleanup;
    }
    if (response[3] != 0)
    {
        rt_kprintf("MQTT test FAIL: broker rejected CONNECT, return code=%u\r\n",
                   response[3]);
        goto cleanup;
    }
    mqtt_connected = RT_TRUE;
    rt_kprintf("MQTT CONNECT accepted (CONNACK return code 0)\r\n");

    packet_length = mqtt_test_build_publish(packet, sizeof(packet));
    if (packet_length == 0)
    {
        rt_kprintf("MQTT test FAIL: could not build PUBLISH packet\r\n");
        goto cleanup;
    }
    if (mqtt_send_all(sock, packet, packet_length,
                      mqtt_deadline(MQTT_TEST_OPERATION_TIMEOUT_MS),
                      &error_code) != RT_EOK)
    {
        rt_kprintf("MQTT test FAIL: sending PUBLISH errno=%d\r\n", error_code);
        goto cleanup;
    }
    if (mqtt_receive_exact(sock, response, sizeof(response),
                           mqtt_deadline(MQTT_TEST_OPERATION_TIMEOUT_MS),
                           &error_code) != RT_EOK)
    {
        rt_kprintf("MQTT test FAIL: waiting for PUBACK errno=%d\r\n", error_code);
        goto cleanup;
    }
    if (response[0] != 0x40 || response[1] != 0x02 || response[2] != 0x00 ||
        response[3] != MQTT_TEST_PACKET_ID)
    {
        rt_kprintf("MQTT test FAIL: unexpected PUBACK (%02x %02x %02x %02x)\r\n",
                   response[0], response[1], response[2], response[3]);
        goto cleanup;
    }

    rt_kprintf("MQTT PUBLISH acknowledged on %s (QoS 1, one test message)\r\n",
               mqtt_test_topic);

cleanup:
    if (sock >= 0 && mqtt_connected)
    {
        error_code = 0;
        if (mqtt_send_all(sock, disconnect_packet,
                          sizeof(disconnect_packet),
                          mqtt_deadline(MQTT_TEST_DISCONNECT_TIMEOUT_MS),
                          &error_code) != RT_EOK)
        {
            rt_kprintf("MQTT test warning: DISCONNECT send errno=%d\r\n", error_code);
        }
    }
    if (sock >= 0 && lwip_close(sock) < 0)
    {
        rt_kprintf("MQTT test warning: socket close errno=%d\r\n",
                   (int)rt_get_errno());
    }
}

MSH_CMD_EXPORT(mqtt_test, publish one MQTT connectivity test message);

/*
 * Motion stream implementation.
 * Queue policy: decimate the 25 Hz acquisition to the configured output rate,
 * timestamp at acquisition, then queue up to two seconds of selected samples.
 * On a full queue the newest selected sample is dropped; the sensor thread
 * never waits for queue space or network activity.
 */
struct mqtt_stream_sample
{
    rt_int16_t raw_axes[6];
    struct timeval acquired_utc;
};

enum mqtt_stream_state
{
    MQTT_STREAM_STOPPED = 0,
    MQTT_STREAM_STARTING,
    MQTT_STREAM_CONNECTING,
    MQTT_STREAM_CONNECTED,
    MQTT_STREAM_WAIT_WIFI,
    MQTT_STREAM_WAIT_TIME,
    MQTT_STREAM_BACKOFF,
    MQTT_STREAM_STOPPING
};

static struct rt_messagequeue mqtt_stream_queue;
static rt_uint64_t mqtt_stream_queue_pool[
    (RT_MQ_BUF_SIZE(sizeof(struct mqtt_stream_sample), MQTT_STREAM_QUEUE_CAPACITY) +
     sizeof(rt_uint64_t) - 1U) / sizeof(rt_uint64_t)];
static struct rt_semaphore mqtt_stream_wake_sem;
static struct rt_semaphore mqtt_stream_stopped_sem;
static struct rt_thread mqtt_stream_thread;
static rt_uint64_t mqtt_stream_thread_stack[MQTT_STREAM_STACK_SIZE / sizeof(rt_uint64_t)];

static rt_bool_t mqtt_stream_initialized;
static rt_bool_t mqtt_stream_enabled;
static rt_bool_t mqtt_stream_worker_busy;
static rt_uint8_t mqtt_stream_rate_hz = MQTT_STREAM_PUBLISH_RATE_DEFAULT;
static rt_uint8_t mqtt_stream_phase;
static enum mqtt_stream_state mqtt_stream_current_state = MQTT_STREAM_STOPPED;
static rt_uint32_t mqtt_stream_queued_count;
static rt_uint32_t mqtt_stream_published_count;
static rt_uint32_t mqtt_stream_invalid_sample_drops;
static rt_uint32_t mqtt_stream_unsynced_drops;
static rt_uint32_t mqtt_stream_queue_drops;
static rt_uint32_t mqtt_stream_stop_drops;
static rt_uint32_t mqtt_stream_publish_failures;
static rt_uint32_t mqtt_stream_connect_failures;
static rt_uint32_t mqtt_stream_reconnect_attempts;
static rt_uint32_t mqtt_stream_wifi_disconnects;
static rt_uint32_t mqtt_stream_connection_drops;
static int mqtt_stream_last_error;

static const char *mqtt_stream_state_name(enum mqtt_stream_state state)
{
    switch (state)
    {
    case MQTT_STREAM_STARTING:   return "starting";
    case MQTT_STREAM_CONNECTING: return "connecting";
    case MQTT_STREAM_CONNECTED:  return "connected";
    case MQTT_STREAM_WAIT_WIFI:  return "wait-wifi";
    case MQTT_STREAM_WAIT_TIME:  return "wait-time";
    case MQTT_STREAM_BACKOFF:    return "backoff";
    case MQTT_STREAM_STOPPING:   return "stopping";
    default:                     return "stopped";
    }
}

static rt_bool_t mqtt_stream_is_enabled(void)
{
    rt_bool_t enabled;

    rt_enter_critical();
    enabled = mqtt_stream_enabled;
    rt_exit_critical();
    return enabled;
}

static void mqtt_stream_set_state(enum mqtt_stream_state state)
{
    rt_enter_critical();
    mqtt_stream_current_state = state;
    rt_exit_critical();
}

static void mqtt_stream_increment(rt_uint32_t *counter)
{
    rt_enter_critical();
    (*counter)++;
    rt_exit_critical();
}

static void mqtt_stream_print_stats(void)
{
    enum mqtt_stream_state state;
    rt_uint8_t rate_hz;
    rt_uint16_t depth;
    rt_uint32_t queued;
    rt_uint32_t published;
    rt_uint32_t invalid_drops;
    rt_uint32_t unsynced_drops;
    rt_uint32_t queue_drops;
    rt_uint32_t stop_drops;
    rt_uint32_t publish_failures;
    rt_uint32_t connect_failures;
    rt_uint32_t reconnects;
    rt_uint32_t wifi_disconnects;
    rt_uint32_t connection_drops;
    int last_error;

    rt_enter_critical();
    state = mqtt_stream_current_state;
    rate_hz = mqtt_stream_rate_hz;
    depth = mqtt_stream_queue.entry;
    queued = mqtt_stream_queued_count;
    published = mqtt_stream_published_count;
    invalid_drops = mqtt_stream_invalid_sample_drops;
    unsynced_drops = mqtt_stream_unsynced_drops;
    queue_drops = mqtt_stream_queue_drops;
    stop_drops = mqtt_stream_stop_drops;
    publish_failures = mqtt_stream_publish_failures;
    connect_failures = mqtt_stream_connect_failures;
    reconnects = mqtt_stream_reconnect_attempts;
    wifi_disconnects = mqtt_stream_wifi_disconnects;
    connection_drops = mqtt_stream_connection_drops;
    last_error = mqtt_stream_last_error;
    rt_exit_critical();

    rt_kprintf("MQTT stream: state=%s rate=%u Hz queue=%u/%u queued=%u sent=%u\r\n",
               mqtt_stream_state_name(state), (unsigned int)rate_hz,
               (unsigned int)depth, (unsigned int)MQTT_STREAM_QUEUE_CAPACITY,
               (unsigned int)queued, (unsigned int)published);
    rt_kprintf("MQTT stream drops: invalid=%u unsynced=%u queue-full=%u stop=%u; ",
               (unsigned int)invalid_drops, (unsigned int)unsynced_drops,
               (unsigned int)queue_drops, (unsigned int)stop_drops);
    rt_kprintf("publish-fail=%u connect-fail=%u reconnects=%u wifi-disconnects=%u ",
               (unsigned int)publish_failures, (unsigned int)connect_failures,
               (unsigned int)reconnects, (unsigned int)wifi_disconnects);
    rt_kprintf("connection-drops=%u last-error=%d\r\n",
               (unsigned int)connection_drops, last_error);
}

static void mqtt_stream_set_last_error(int error_code)
{
    rt_enter_critical();
    mqtt_stream_last_error = error_code;
    rt_exit_critical();
}

void motion_mqtt_sample_tick(rt_bool_t valid, const rt_int16_t *raw_axes)
{
    struct mqtt_stream_sample sample;
    rt_uint8_t rate_hz;
    rt_bool_t due = RT_FALSE;

    if (!mqtt_stream_initialized)
    {
        return;
    }

    rt_enter_critical();
    if (mqtt_stream_enabled)
    {
        rate_hz = mqtt_stream_rate_hz;
        mqtt_stream_phase = (rt_uint8_t)(mqtt_stream_phase + rate_hz);
        if (mqtt_stream_phase >= MQTT_STREAM_SAMPLE_RATE_HZ)
        {
            mqtt_stream_phase = (rt_uint8_t)(mqtt_stream_phase - MQTT_STREAM_SAMPLE_RATE_HZ);
            due = RT_TRUE;
        }
    }
    else
    {
        rate_hz = 0;
    }
    rt_exit_critical();

    if (!due)
    {
        return;
    }
    if (!valid || (raw_axes == RT_NULL))
    {
        mqtt_stream_increment(&mqtt_stream_invalid_sample_drops);
        return;
    }
    if (bca_time_sync_get_utc(&sample.acquired_utc) != RT_EOK)
    {
        mqtt_stream_increment(&mqtt_stream_unsynced_drops);
        return;
    }

    rt_memcpy(sample.raw_axes, raw_axes, sizeof(sample.raw_axes));

    /* rt_mq_send has a zero-wait implementation; keep this producer bounded. */
    rt_enter_critical();
    if (mqtt_stream_enabled)
    {
        if (rt_mq_send(&mqtt_stream_queue, &sample, sizeof(sample)) == RT_EOK)
        {
            mqtt_stream_queued_count++;
        }
        else
        {
            mqtt_stream_queue_drops++;
        }
    }
    rt_exit_critical();
}

static rt_int32_t mqtt_stream_round_divide(rt_int64_t numerator, rt_int64_t denominator)
{
    if (numerator >= 0)
    {
        numerator += denominator / 2;
    }
    else
    {
        numerator -= denominator / 2;
    }

    return (rt_int32_t)(numerator / denominator);
}

static void mqtt_stream_format_milli(rt_int32_t value, char *destination,
                                     rt_size_t capacity)
{
    rt_uint32_t magnitude = (rt_uint32_t)(value < 0 ? -(rt_int64_t)value : value);

    rt_snprintf(destination, capacity, "%s%u.%03u", value < 0 ? "-" : "",
                (unsigned int)(magnitude / 1000U),
                (unsigned int)(magnitude % 1000U));
}

static rt_bool_t mqtt_stream_format_timestamp(const struct timeval *utc,
                                              char *destination,
                                              rt_size_t capacity)
{
    struct tm utc_tm;
    rt_int64_t seconds;
    int result;

    if ((utc == RT_NULL) || (destination == RT_NULL) || (capacity == 0U))
    {
        return RT_FALSE;
    }

    seconds = (rt_int64_t)utc->tv_sec;
    if ((seconds < 1704067200LL) || (seconds > 2147483647LL) ||
        (utc->tv_usec < 0) || (utc->tv_usec >= 1000000))
    {
        return RT_FALSE;
    }
    if (gmtime_r(&utc->tv_sec, &utc_tm) == RT_NULL)
    {
        return RT_FALSE;
    }

    result = rt_snprintf(destination, capacity,
                         "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ",
                         utc_tm.tm_year + 1900, utc_tm.tm_mon + 1,
                         utc_tm.tm_mday, utc_tm.tm_hour, utc_tm.tm_min,
                         utc_tm.tm_sec, (int)(utc->tv_usec / 1000));
    return (result > 0) && ((rt_size_t)result < capacity);
}

static rt_bool_t mqtt_stream_build_payload(const struct mqtt_stream_sample *sample,
                                           const char *device_id,
                                           char *payload, rt_size_t capacity,
                                           rt_size_t *payload_length)
{
    char timestamp[32];
    char accel[3][16];
    char gyro[3][16];
    rt_int32_t accel_milli[3];
    rt_int32_t gyro_milli[3];
    int result;
    rt_uint32_t axis;

    if ((sample == RT_NULL) || (device_id == RT_NULL) || (payload == RT_NULL) ||
        (payload_length == RT_NULL) ||
        !bca_time_sync_is_valid() ||
        !mqtt_stream_format_timestamp(&sample->acquired_utc, timestamp, sizeof(timestamp)))
    {
        return RT_FALSE;
    }

    for (axis = 0; axis < 3U; axis++)
    {
        accel_milli[axis] = mqtt_stream_round_divide(
            (rt_int64_t)sample->raw_axes[axis] * MQTT_ACCEL_MILLI_NUMERATOR,
            MQTT_ACCEL_MILLI_DENOMINATOR);
        gyro_milli[axis] = mqtt_stream_round_divide(
            (rt_int64_t)sample->raw_axes[axis + 3U] * MQTT_GYRO_MILLI_NUMERATOR,
            MQTT_GYRO_MILLI_DENOMINATOR);
        mqtt_stream_format_milli(accel_milli[axis], accel[axis], sizeof(accel[axis]));
        mqtt_stream_format_milli(gyro_milli[axis], gyro[axis], sizeof(gyro[axis]));
    }

    result = rt_snprintf(payload, capacity,
                         "{\"device_id\":\"%s\",\"timestamp\":\"%s\","
                         "\"accel_m_s2\":{\"x\":%s,\"y\":%s,\"z\":%s},"
                         "\"gyro_rad_s\":{\"x\":%s,\"y\":%s,\"z\":%s}}",
                         device_id, timestamp,
                         accel[0], accel[1], accel[2],
                         gyro[0], gyro[1], gyro[2]);
    if ((result <= 0) || ((rt_size_t)result >= capacity))
    {
        return RT_FALSE;
    }

    *payload_length = (rt_size_t)result;
    return RT_TRUE;
}

static rt_size_t mqtt_stream_build_connect(rt_uint8_t *packet, rt_size_t capacity,
                                           const char *client_id)
{
    rt_size_t client_id_length;
    rt_uint32_t remaining_length;
    rt_size_t offset = 0;

    if ((packet == RT_NULL) || (client_id == RT_NULL))
    {
        return 0;
    }
    client_id_length = rt_strlen(client_id);
    remaining_length = 12U + (rt_uint32_t)client_id_length;

    if ((capacity < remaining_length + 2U) || (client_id_length > 0xFFFFU))
    {
        return 0;
    }

    packet[offset++] = 0x10;
    offset += mqtt_encode_remaining_length(remaining_length, packet + offset);
    packet[offset++] = 0x00;
    packet[offset++] = 0x04;
    rt_memcpy(packet + offset, "MQTT", 4U);
    offset += 4U;
    packet[offset++] = 0x04;
    packet[offset++] = 0x02;
    packet[offset++] = 0x00;
    packet[offset++] = (rt_uint8_t)MQTT_STREAM_KEEPALIVE_SECONDS;
    packet[offset++] = (rt_uint8_t)(client_id_length >> 8);
    packet[offset++] = (rt_uint8_t)client_id_length;
    rt_memcpy(packet + offset, client_id, client_id_length);
    offset += client_id_length;

    return offset;
}

static rt_bool_t mqtt_stream_build_publish(const struct mqtt_stream_sample *sample,
                                           const char *device_id,
                                           rt_uint16_t packet_id,
                                           rt_uint8_t *packet, rt_size_t capacity,
                                           rt_size_t *packet_length)
{
    char payload[256];
    rt_size_t payload_length;
    rt_size_t topic_length = sizeof(MQTT_STREAM_TOPIC) - 1U;
    rt_uint32_t remaining_length;
    rt_size_t offset = 0;

    if ((packet == RT_NULL) || (packet_length == RT_NULL) ||
        !mqtt_stream_build_payload(sample, device_id, payload, sizeof(payload),
                                   &payload_length))
    {
        return RT_FALSE;
    }
    if ((topic_length > 0xFFFFU) || (payload_length > 0xFFFFU))
    {
        return RT_FALSE;
    }

    remaining_length = 2U + (rt_uint32_t)topic_length + 2U + (rt_uint32_t)payload_length;
    if (capacity < remaining_length + 6U)
    {
        return RT_FALSE;
    }

    packet[offset++] = 0x32;
    offset += mqtt_encode_remaining_length(remaining_length, packet + offset);
    packet[offset++] = (rt_uint8_t)(topic_length >> 8);
    packet[offset++] = (rt_uint8_t)topic_length;
    rt_memcpy(packet + offset, MQTT_STREAM_TOPIC, topic_length);
    offset += topic_length;
    packet[offset++] = (rt_uint8_t)(packet_id >> 8);
    packet[offset++] = (rt_uint8_t)packet_id;
    rt_memcpy(packet + offset, payload, payload_length);
    offset += payload_length;
    *packet_length = offset;
    return RT_TRUE;
}

static int mqtt_stream_connect_broker(const struct mqtt_config_values *config,
                                      const char *client_id,
                                      int *error_code)
{
    rt_uint8_t packet[64];
    rt_uint8_t response[4];
    rt_size_t packet_length;
    rt_uint32_t nonblocking = 1U;
    int sock = -1;
    int result;
    int resolve_result;
    int socket_error = 0;
    socklen_t option_length = sizeof(socket_error);
    rt_uint32_t broker_address;
    struct sockaddr_in server_address;

    if ((config == RT_NULL) || (client_id == RT_NULL) || (error_code == RT_NULL))
    {
        return -1;
    }

    resolve_result = mqtt_config_resolve_ipv4(config->broker_host, &broker_address);
    if (resolve_result != 0)
    {
        *error_code = EHOSTUNREACH;
        rt_kprintf("MQTT stream: DNS resolution for %s failed (lwIP error=%d).\r\n",
                   config->broker_host, resolve_result);
        return -1;
    }

    sock = lwip_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock < 0)
    {
        *error_code = (int)rt_get_errno();
        return -1;
    }
    if (lwip_ioctl(sock, FIONBIO, &nonblocking) < 0)
    {
        *error_code = (int)rt_get_errno();
        goto failed;
    }

    rt_memset(&server_address, 0, sizeof(server_address));
    server_address.sin_family = AF_INET;
    server_address.sin_port = lwip_htons(config->broker_port);
    server_address.sin_addr.s_addr = broker_address;
    result = lwip_connect(sock, (const struct sockaddr *)&server_address,
                          sizeof(server_address));
    if (result < 0)
    {
        *error_code = (int)rt_get_errno();
        if (*error_code != EINPROGRESS && *error_code != EALREADY &&
            *error_code != EWOULDBLOCK)
        {
            goto failed;
        }
        if (mqtt_wait_socket(sock, RT_TRUE, RT_TRUE,
                             mqtt_deadline(MQTT_STREAM_CONNECT_TIMEOUT_MS),
                             error_code) != RT_EOK)
        {
            goto failed;
        }
        if (lwip_getsockopt(sock, SOL_SOCKET, SO_ERROR, &socket_error,
                            &option_length) < 0)
        {
            *error_code = (int)rt_get_errno();
            goto failed;
        }
        if (socket_error != 0)
        {
            *error_code = socket_error;
            goto failed;
        }
    }

    packet_length = mqtt_stream_build_connect(packet, sizeof(packet), client_id);
    if ((packet_length == 0U) ||
        (mqtt_send_all(sock, packet, packet_length,
                       mqtt_deadline(MQTT_STREAM_OPERATION_TIMEOUT_MS),
                       error_code) != RT_EOK) ||
        (mqtt_receive_exact(sock, response, sizeof(response),
                            mqtt_deadline(MQTT_STREAM_OPERATION_TIMEOUT_MS),
                            error_code) != RT_EOK))
    {
        if (packet_length == 0U)
        {
            *error_code = EINVAL;
        }
        goto failed;
    }
    if ((response[0] != 0x20U) || (response[1] != 0x02U) ||
        (response[2] != 0x00U) || (response[3] != 0x00U))
    {
        *error_code = EACCES;
        goto failed;
    }

    return sock;

failed:
    if (sock >= 0)
    {
        lwip_close(sock);
    }
    return -1;
}

static rt_err_t mqtt_stream_send_disconnect(int sock)
{
    static const rt_uint8_t packet[] = {0xE0U, 0x00U};
    int error_code = 0;

    return mqtt_send_all(sock, packet, sizeof(packet),
                         mqtt_deadline(MQTT_STREAM_DISCONNECT_TIMEOUT_MS),
                         &error_code);
}

static rt_err_t mqtt_stream_send_ping(int sock, int *error_code)
{
    static const rt_uint8_t request[] = {0xC0U, 0x00U};
    rt_uint8_t response[2];

    if (mqtt_send_all(sock, request, sizeof(request),
                      mqtt_deadline(MQTT_STREAM_OPERATION_TIMEOUT_MS),
                      error_code) != RT_EOK)
    {
        return -RT_ERROR;
    }
    if (mqtt_receive_exact(sock, response, sizeof(response),
                           mqtt_deadline(MQTT_STREAM_OPERATION_TIMEOUT_MS),
                           error_code) != RT_EOK)
    {
        return -RT_ERROR;
    }
    if ((response[0] != 0xD0U) || (response[1] != 0x00U))
    {
        *error_code = EPROTO;
        return -RT_ERROR;
    }

    return RT_EOK;
}

static rt_err_t mqtt_stream_publish_sample(int sock,
                                           const struct mqtt_stream_sample *sample,
                                           const char *device_id,
                                           rt_uint16_t packet_id,
                                           int *error_code)
{
    rt_uint8_t packet[MQTT_STREAM_PACKET_CAPACITY];
    rt_uint8_t response[4];
    rt_size_t packet_length;

    if (!mqtt_stream_build_publish(sample, device_id, packet_id, packet,
                                   sizeof(packet), &packet_length))
    {
        *error_code = EINVAL;
        return -RT_ERROR;
    }
    if (mqtt_send_all(sock, packet, packet_length,
                      mqtt_deadline(MQTT_STREAM_OPERATION_TIMEOUT_MS),
                      error_code) != RT_EOK)
    {
        return -RT_ERROR;
    }
    if (mqtt_receive_exact(sock, response, sizeof(response),
                           mqtt_deadline(MQTT_STREAM_OPERATION_TIMEOUT_MS),
                           error_code) != RT_EOK)
    {
        return -RT_ERROR;
    }
    if ((response[0] != 0x40U) || (response[1] != 0x02U) ||
        (response[2] != (rt_uint8_t)(packet_id >> 8)) ||
        (response[3] != (rt_uint8_t)packet_id))
    {
        *error_code = EPROTO;
        return -RT_ERROR;
    }

    return RT_EOK;
}

static void mqtt_stream_wait(rt_uint32_t timeout_ms)
{
    rt_tick_t timeout = rt_tick_from_millisecond((rt_int32_t)timeout_ms);

    rt_sem_take(&mqtt_stream_wake_sem, (rt_int32_t)timeout);
}

static void mqtt_stream_flush_queue(rt_bool_t count_as_stop_drops)
{
    struct mqtt_stream_sample unused_sample;
    rt_uint32_t dropped = 0;

    while (rt_mq_recv(&mqtt_stream_queue, &unused_sample, sizeof(unused_sample),
                      RT_WAITING_NO) > 0)
    {
        dropped++;
    }

    if (count_as_stop_drops && (dropped > 0U))
    {
        rt_enter_critical();
        mqtt_stream_stop_drops += dropped;
        rt_exit_critical();
    }
}

static void mqtt_stream_worker_finish(int sock, rt_bool_t graceful_disconnect)
{
    if (sock >= 0)
    {
        if (graceful_disconnect)
        {
            mqtt_stream_send_disconnect(sock);
        }
        lwip_close(sock);
    }

    mqtt_stream_flush_queue(RT_TRUE);
    rt_enter_critical();
    mqtt_stream_current_state = MQTT_STREAM_STOPPED;
    mqtt_stream_worker_busy = RT_FALSE;
    rt_exit_critical();
    mqtt_config_set_stream_active(RT_FALSE);
    rt_sem_release(&mqtt_stream_stopped_sem);
}

static void mqtt_stream_worker(void *parameter)
{
    LWIP_UNUSED_ARG(parameter);

    for (;;)
    {
        int sock = -1;
        rt_bool_t ever_connected = RT_FALSE;
        rt_uint32_t attempt_number = 0;
        rt_uint32_t backoff_ms = MQTT_STREAM_BACKOFF_INITIAL_MS;
        rt_uint16_t packet_id = 1U;
        rt_tick_t last_tx_tick = rt_tick_get();
        rt_tick_t last_diagnostic_tick = last_tx_tick;
        struct mqtt_config_values config;
        char client_id[MQTT_CONFIG_CLIENT_ID_SIZE];

        rt_sem_take(&mqtt_stream_wake_sem, RT_WAITING_FOREVER);
        if (!mqtt_stream_is_enabled())
        {
            rt_bool_t pending_stop;

            rt_enter_critical();
            pending_stop = mqtt_stream_worker_busy;
            rt_exit_critical();
            if (pending_stop)
            {
                mqtt_stream_worker_finish(-1, RT_FALSE);
            }
            continue;
        }

        mqtt_config_get(&config);
        if (mqtt_config_make_client_id(&config, MQTT_CONFIG_CLIENT_STREAM,
                                       client_id, sizeof(client_id)) != RT_EOK)
        {
            rt_kprintf("MQTT stream: invalid device ID configuration.\r\n");
            rt_enter_critical();
            mqtt_stream_enabled = RT_FALSE;
            rt_exit_critical();
            mqtt_stream_worker_finish(-1, RT_FALSE);
            continue;
        }

        rt_enter_critical();
        mqtt_stream_worker_busy = RT_TRUE;
        rt_exit_critical();
        mqtt_stream_set_state(MQTT_STREAM_CONNECTING);

        while (mqtt_stream_is_enabled())
        {
            rt_bool_t wifi_connected = rt_wlan_is_connected();

            if (!wifi_connected)
            {
                if (sock >= 0)
                {
                    lwip_close(sock);
                    sock = -1;
                    ever_connected = RT_FALSE;
                    mqtt_stream_increment(&mqtt_stream_wifi_disconnects);
                    mqtt_stream_increment(&mqtt_stream_connection_drops);
                }
                mqtt_stream_set_state(MQTT_STREAM_WAIT_WIFI);
                mqtt_stream_wait(500U);
                continue;
            }

            if (!bca_time_sync_is_valid())
            {
                if (sock >= 0)
                {
                    mqtt_stream_send_disconnect(sock);
                    lwip_close(sock);
                    sock = -1;
                    mqtt_stream_increment(&mqtt_stream_connection_drops);
                }
                mqtt_stream_set_state(MQTT_STREAM_WAIT_TIME);
                mqtt_stream_wait(1000U);
                continue;
            }

            if (sock < 0)
            {
                int error_code = 0;

                attempt_number++;
                if (attempt_number > 1U)
                {
                    mqtt_stream_increment(&mqtt_stream_reconnect_attempts);
                }
                mqtt_stream_set_state(MQTT_STREAM_CONNECTING);
                sock = mqtt_stream_connect_broker(&config, client_id, &error_code);
                if (sock < 0)
                {
                    mqtt_stream_increment(&mqtt_stream_connect_failures);
                    mqtt_stream_set_last_error(error_code);
                    mqtt_stream_set_state(MQTT_STREAM_BACKOFF);
                    mqtt_stream_wait(backoff_ms);
                    if (backoff_ms < MQTT_STREAM_BACKOFF_MAX_MS)
                    {
                        backoff_ms *= 2U;
                        if (backoff_ms > MQTT_STREAM_BACKOFF_MAX_MS)
                        {
                            backoff_ms = MQTT_STREAM_BACKOFF_MAX_MS;
                        }
                    }
                    continue;
                }

                ever_connected = RT_TRUE;
                backoff_ms = MQTT_STREAM_BACKOFF_INITIAL_MS;
                last_tx_tick = rt_tick_get();
                mqtt_stream_set_last_error(0);
                rt_kprintf("MQTT stream: connected to %s:%u (QoS 1).\r\n",
                           config.broker_host, (unsigned int)config.broker_port);
                mqtt_stream_set_state(MQTT_STREAM_CONNECTED);
            }

            if (!mqtt_stream_is_enabled())
            {
                break;
            }

            {
                struct mqtt_stream_sample sample;
                rt_ssize_t received;

                received = rt_mq_recv(&mqtt_stream_queue, &sample, sizeof(sample),
                                      (rt_int32_t)rt_tick_from_millisecond(MQTT_STREAM_QUEUE_WAIT_MS));
                if (received == (rt_ssize_t)sizeof(sample))
                {
                    int error_code = 0;

                    if (!bca_time_sync_is_valid())
                    {
                        mqtt_stream_increment(&mqtt_stream_unsynced_drops);
                    }
                    else if (mqtt_stream_publish_sample(sock, &sample,
                                                        config.device_id, packet_id,
                                                        &error_code) != RT_EOK)
                    {
                        if (error_code == EINVAL)
                        {
                            mqtt_stream_increment(&mqtt_stream_unsynced_drops);
                        }
                        else
                        {
                            mqtt_stream_increment(&mqtt_stream_publish_failures);
                            mqtt_stream_set_last_error(error_code);
                            if (!rt_wlan_is_connected())
                            {
                                mqtt_stream_increment(&mqtt_stream_wifi_disconnects);
                            }
                            if (ever_connected)
                            {
                                mqtt_stream_increment(&mqtt_stream_connection_drops);
                            }
                            lwip_close(sock);
                            sock = -1;
                            ever_connected = RT_FALSE;
                            mqtt_stream_set_state(MQTT_STREAM_BACKOFF);
                            mqtt_stream_wait(backoff_ms);
                            if (backoff_ms < MQTT_STREAM_BACKOFF_MAX_MS)
                            {
                                backoff_ms *= 2U;
                                if (backoff_ms > MQTT_STREAM_BACKOFF_MAX_MS)
                                {
                                    backoff_ms = MQTT_STREAM_BACKOFF_MAX_MS;
                                }
                            }
                        }
                    }
                    else
                    {
                        mqtt_stream_increment(&mqtt_stream_published_count);
                        mqtt_stream_set_last_error(0);
                        packet_id++;
                        if (packet_id == 0U)
                        {
                            packet_id = 1U;
                        }
                        last_tx_tick = rt_tick_get();
                    }
                }
                else if (received < 0 && received != -RT_ETIMEOUT &&
                         received != -RT_ERROR)
                {
                    mqtt_stream_set_last_error((int)received);
                }
            }

            if ((sock >= 0) &&
                ((rt_tick_t)(rt_tick_get() - last_tx_tick) >=
                 (rt_tick_t)(MQTT_STREAM_KEEPALIVE_SECONDS / 2U) * RT_TICK_PER_SECOND))
            {
                int error_code = 0;

                if (mqtt_stream_send_ping(sock, &error_code) != RT_EOK)
                {
                    mqtt_stream_set_last_error(error_code);
                    mqtt_stream_increment(&mqtt_stream_connection_drops);
                    if (ever_connected && !rt_wlan_is_connected())
                    {
                        mqtt_stream_increment(&mqtt_stream_wifi_disconnects);
                    }
                    lwip_close(sock);
                    sock = -1;
                    ever_connected = RT_FALSE;
                    mqtt_stream_set_state(MQTT_STREAM_BACKOFF);
                }
                else
                {
                    last_tx_tick = rt_tick_get();
                }
            }

            if ((rt_tick_t)(rt_tick_get() - last_diagnostic_tick) >=
                (rt_tick_t)MQTT_STREAM_DIAGNOSTIC_SECONDS * RT_TICK_PER_SECOND)
            {
                mqtt_stream_print_stats();
                last_diagnostic_tick = rt_tick_get();
            }
        }

        rt_enter_critical();
        mqtt_stream_current_state = MQTT_STREAM_STOPPING;
        rt_exit_critical();
        mqtt_stream_worker_finish(sock, RT_TRUE);
    }
}

static int mqtt_stream_init(void)
{
    rt_err_t result;

    result = rt_mq_init(&mqtt_stream_queue, "mqdat", mqtt_stream_queue_pool,
                        sizeof(struct mqtt_stream_sample),
                        sizeof(mqtt_stream_queue_pool), RT_IPC_FLAG_FIFO);
    if (result != RT_EOK)
    {
        rt_kprintf("MQTT stream: sample queue initialization failed (%d).\r\n", result);
        return result;
    }

    result = rt_sem_init(&mqtt_stream_wake_sem, "mqwake", 0, RT_IPC_FLAG_FIFO);
    if (result != RT_EOK)
    {
        rt_mq_detach(&mqtt_stream_queue);
        rt_kprintf("MQTT stream: wake semaphore initialization failed (%d).\r\n", result);
        return result;
    }
    result = rt_sem_init(&mqtt_stream_stopped_sem, "mqstop", 0, RT_IPC_FLAG_FIFO);
    if (result != RT_EOK)
    {
        rt_sem_detach(&mqtt_stream_wake_sem);
        rt_mq_detach(&mqtt_stream_queue);
        rt_kprintf("MQTT stream: stop semaphore initialization failed (%d).\r\n", result);
        return result;
    }

    result = rt_thread_init(&mqtt_stream_thread, "mqpub", mqtt_stream_worker,
                            RT_NULL, mqtt_stream_thread_stack,
                            sizeof(mqtt_stream_thread_stack),
                            MQTT_STREAM_THREAD_PRIORITY, 10U);
    if (result != RT_EOK)
    {
        rt_sem_detach(&mqtt_stream_stopped_sem);
        rt_sem_detach(&mqtt_stream_wake_sem);
        rt_mq_detach(&mqtt_stream_queue);
        rt_kprintf("MQTT stream: publisher thread initialization failed (%d).\r\n", result);
        return result;
    }
    result = rt_thread_startup(&mqtt_stream_thread);
    if (result != RT_EOK)
    {
        rt_thread_detach(&mqtt_stream_thread);
        rt_sem_detach(&mqtt_stream_stopped_sem);
        rt_sem_detach(&mqtt_stream_wake_sem);
        rt_mq_detach(&mqtt_stream_queue);
        rt_kprintf("MQTT stream: publisher thread start failed (%d).\r\n", result);
        return result;
    }

    mqtt_stream_initialized = RT_TRUE;
    return RT_EOK;
}
INIT_APP_EXPORT(mqtt_stream_init);

static rt_bool_t mqtt_stream_parse_rate(const char *text, rt_uint8_t *rate_hz)
{
    rt_uint32_t value = 0;
    const char *cursor = text;

    if ((cursor == RT_NULL) || (*cursor == '\0'))
    {
        return RT_FALSE;
    }
    while (*cursor != '\0')
    {
        if ((*cursor < '0') || (*cursor > '9'))
        {
            return RT_FALSE;
        }
        value = value * 10U + (rt_uint32_t)(*cursor - '0');
        if (value > MQTT_STREAM_SAMPLE_RATE_HZ)
        {
            return RT_FALSE;
        }
        cursor++;
    }
    if ((value == 0U) || (value > MQTT_STREAM_SAMPLE_RATE_HZ))
    {
        return RT_FALSE;
    }

    *rate_hz = (rt_uint8_t)value;
    return RT_TRUE;
}

static void mqtt_stream(int argc, char **argv)
{
    rt_uint8_t requested_rate = MQTT_STREAM_PUBLISH_RATE_DEFAULT;

    if (!mqtt_stream_initialized)
    {
        rt_kprintf("mqtt_stream: service initialization failed.\r\n");
        return;
    }
    if ((argc < 2) || (argc > 3))
    {
        rt_kprintf("Usage: mqtt_stream start [1-25] | stop | status\r\n");
        return;
    }

    if (rt_strcmp(argv[1], "status") == 0)
    {
        if (argc != 2)
        {
            rt_kprintf("Usage: mqtt_stream status\r\n");
            return;
        }
        mqtt_stream_print_stats();
        return;
    }

    if (rt_strcmp(argv[1], "start") == 0)
    {
        rt_bool_t busy;

        if ((argc == 3) && !mqtt_stream_parse_rate(argv[2], &requested_rate))
        {
            rt_kprintf("mqtt_stream: rate must be an integer from 1 to 25 Hz.\r\n");
            return;
        }
        if (!bca_time_sync_is_valid())
        {
            rt_kprintf("mqtt_stream: UTC clock is not synchronized or has expired; run time_sync first.\r\n");
            return;
        }

        rt_enter_critical();
        busy = mqtt_stream_enabled || mqtt_stream_worker_busy;
        rt_exit_critical();
        if (busy)
        {
            rt_kprintf("mqtt_stream: already active or stopping; run status.\r\n");
            return;
        }

        while (rt_sem_take(&mqtt_stream_stopped_sem, RT_WAITING_NO) == RT_EOK)
        {
            /* discard a stale stop acknowledgement from a previous run */
        }
        while (rt_sem_take(&mqtt_stream_wake_sem, RT_WAITING_NO) == RT_EOK)
        {
            /* discard wake tokens left by a stop request */
        }
        mqtt_stream_flush_queue(RT_FALSE);

        mqtt_config_set_stream_active(RT_TRUE);

        rt_enter_critical();
        mqtt_stream_rate_hz = requested_rate;
        mqtt_stream_phase = 0;
        mqtt_stream_queued_count = 0;
        mqtt_stream_published_count = 0;
        mqtt_stream_invalid_sample_drops = 0;
        mqtt_stream_unsynced_drops = 0;
        mqtt_stream_queue_drops = 0;
        mqtt_stream_stop_drops = 0;
        mqtt_stream_publish_failures = 0;
        mqtt_stream_connect_failures = 0;
        mqtt_stream_reconnect_attempts = 0;
        mqtt_stream_wifi_disconnects = 0;
        mqtt_stream_connection_drops = 0;
        mqtt_stream_last_error = 0;
        mqtt_stream_current_state = MQTT_STREAM_STARTING;
        mqtt_stream_worker_busy = RT_TRUE;
        mqtt_stream_enabled = RT_TRUE;
        rt_exit_critical();

        if (rt_sem_release(&mqtt_stream_wake_sem) != RT_EOK)
        {
            rt_enter_critical();
            mqtt_stream_enabled = RT_FALSE;
            mqtt_stream_worker_busy = RT_FALSE;
            mqtt_stream_current_state = MQTT_STREAM_STOPPED;
            rt_exit_critical();
            mqtt_config_set_stream_active(RT_FALSE);
            rt_kprintf("mqtt_stream: could not wake the publisher thread.\r\n");
            return;
        }

        rt_kprintf("mqtt_stream: started at %u Hz; decimating valid 25 Hz samples, queue depth %u.\r\n",
                   (unsigned int)requested_rate, (unsigned int)MQTT_STREAM_QUEUE_CAPACITY);
        return;
    }

    if (rt_strcmp(argv[1], "stop") == 0)
    {
        rt_bool_t active;
        rt_err_t result;

        if (argc != 2)
        {
            rt_kprintf("Usage: mqtt_stream stop\r\n");
            return;
        }
        rt_enter_critical();
        active = mqtt_stream_enabled || mqtt_stream_worker_busy;
        if (active)
        {
            mqtt_stream_enabled = RT_FALSE;
            mqtt_stream_current_state = MQTT_STREAM_STOPPING;
        }
        rt_exit_critical();
        if (!active)
        {
            rt_kprintf("mqtt_stream: already stopped.\r\n");
            return;
        }

        rt_sem_release(&mqtt_stream_wake_sem);
        result = rt_sem_take(&mqtt_stream_stopped_sem,
                             (rt_int32_t)rt_tick_from_millisecond(MQTT_STREAM_STOP_TIMEOUT_MS));
        if (result == RT_EOK)
        {
            rt_kprintf("mqtt_stream: stopped; any queued unsent samples were counted as stop drops.\r\n");
        }
        else
        {
            rt_kprintf("mqtt_stream: stop requested, but publisher did not acknowledge within %u ms; check status.\r\n",
                       (unsigned int)MQTT_STREAM_STOP_TIMEOUT_MS);
        }
        return;
    }

    rt_kprintf("Usage: mqtt_stream start [1-25] | stop | status\r\n");
}
MSH_CMD_EXPORT(mqtt_stream, start stop or inspect continuous motion MQTT publishing);
#endif /* RT_USING_FINSH */
