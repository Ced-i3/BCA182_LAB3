#ifndef BCA152_MOTION_MQTT_H
#define BCA152_MOTION_MQTT_H

#include <rtthread.h>

/* Called once per 25 Hz acquisition cycle; raw_axes is required only if valid. */
void motion_mqtt_sample_tick(rt_bool_t valid, const rt_int16_t *raw_axes);

#endif /* BCA152_MOTION_MQTT_H */
