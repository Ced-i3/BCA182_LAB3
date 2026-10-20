#ifndef BCA152_TIME_SYNC_H
#define BCA152_TIME_SYNC_H

#include <rtthread.h>
#include <sys/time.h>

/* Return UTC only while the software RTC has a recent successful SNTP sync. */
rt_err_t bca_time_sync_get_utc(struct timeval *utc_time);
rt_bool_t bca_time_sync_is_valid(void);

#endif /* BCA152_TIME_SYNC_H */
