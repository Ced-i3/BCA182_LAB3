#ifndef BCA152_MQTT_CONFIG_H
#define BCA152_MQTT_CONFIG_H

#include <rtthread.h>

#define MQTT_CONFIG_BROKER_HOST_SIZE 128U
#define MQTT_CONFIG_DEVICE_ID_SIZE  33U
#define MQTT_CONFIG_CLIENT_ID_SIZE  48U

#define MQTT_CONFIG_DEFAULT_BROKER_HOST "192.168.1.11"
#define MQTT_CONFIG_DEFAULT_BROKER_PORT 1883U
#define MQTT_CONFIG_DEFAULT_DEVICE_ID   "rt-spark-001"

struct mqtt_config_values
{
    char broker_host[MQTT_CONFIG_BROKER_HOST_SIZE];
    rt_uint16_t broker_port;
    char device_id[MQTT_CONFIG_DEVICE_ID_SIZE];
};

enum mqtt_config_client_role
{
    MQTT_CONFIG_CLIENT_TEST = 0,
    MQTT_CONFIG_CLIENT_STREAM
};

void mqtt_config_get(struct mqtt_config_values *values);
rt_err_t mqtt_config_set_broker(const char *host);
rt_err_t mqtt_config_set_port(rt_uint16_t port);
rt_err_t mqtt_config_set_device_id(const char *device_id);
rt_err_t mqtt_config_make_client_id(const struct mqtt_config_values *values,
                                    enum mqtt_config_client_role role,
                                    char *destination,
                                    rt_size_t destination_size);
int mqtt_config_resolve_ipv4(const char *host, rt_uint32_t *address);
void mqtt_config_set_stream_active(rt_bool_t active);

#endif /* BCA152_MQTT_CONFIG_H */
