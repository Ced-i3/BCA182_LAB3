/*
 * Manually triggered lwIP SNTP synchronization using RT-Thread's software RTC.
 * The SNTP receive callback runs in lwIP's TCP/IP thread; it performs only a
 * bounded software-RTC update and semaphore release. It never waits for I/O.
 */

#include <rtthread.h>
#include <rtdevice.h>
#include <sys/time.h>
#include <time.h>
#include <string.h>

#include <lwip/apps/sntp.h>
#include <lwip/tcpip.h>

#ifdef RT_USING_FINSH
#include <finsh.h>
#endif

#include "time_sync.h"

#define TIME_SYNC_DEFAULT_SERVER             "pool.ntp.org"
#define TIME_SYNC_SERVER_NAME_CAPACITY       64U
#define TIME_SYNC_WAIT_TIMEOUT_MS            15000U
#define TIME_SYNC_VALIDITY_MAX_AGE_SECONDS   86400U
#define TIME_SYNC_MIN_UNIX_SECONDS           1704067200U /* 2024-01-01T00:00:00Z */
#define TIME_SYNC_MAX_UNIX_SECONDS           2147483647U /* signed 32-bit time_t limit */

static struct rt_mutex time_sync_mutex;
static struct rt_semaphore time_sync_result_sem;
static rt_bool_t time_sync_initialized;
static rt_bool_t time_sync_request_active;
static rt_bool_t time_sync_callback_completed;
static rt_err_t time_sync_callback_result;
static rt_bool_t time_sync_ever_succeeded;
static rt_tick_t time_sync_last_success_tick;
static char time_sync_server[TIME_SYNC_SERVER_NAME_CAPACITY] = TIME_SYNC_DEFAULT_SERVER;
static char time_sync_last_success_server[TIME_SYNC_SERVER_NAME_CAPACITY];

static rt_bool_t time_sync_age_is_valid(rt_tick_t now, rt_tick_t synced_at)
{
    rt_tick_t max_age = (rt_tick_t)TIME_SYNC_VALIDITY_MAX_AGE_SECONDS * RT_TICK_PER_SECOND;

    return (rt_tick_t)(now - synced_at) <= max_age;
}

rt_bool_t bca_time_sync_is_valid(void)
{
    rt_bool_t valid;
    rt_tick_t now;
    now = rt_tick_get();
    rt_enter_critical();
    valid = time_sync_ever_succeeded && time_sync_age_is_valid(now, time_sync_last_success_tick);
    rt_exit_critical();

    return valid;
}

rt_err_t bca_time_sync_get_utc(struct timeval *utc_time)
{
    if (utc_time == RT_NULL)
    {
        return -RT_EINVAL;
    }

    if (!bca_time_sync_is_valid())
    {
        return -RT_ERROR;
    }

    return (gettimeofday(utc_time, RT_NULL) == 0) ? RT_EOK : -RT_ERROR;
}

/*
 * SNTP_CHECK_RESPONSE=2 needs an originate timestamp to match the reply.
 * This monotonic token is used only for request/reply correlation; it is not
 * treated as UTC and is never returned by the timestamp API.
 */
void bca_sntp_get_request_time(unsigned long *seconds, unsigned long *microseconds)
{
    rt_tick_t tick = rt_tick_get();

    if ((seconds == RT_NULL) || (microseconds == RT_NULL))
    {
        return;
    }

    *seconds = (unsigned long)(tick / RT_TICK_PER_SECOND);
    *microseconds = (unsigned long)(((tick % RT_TICK_PER_SECOND) * 1000000ULL) /
                                    RT_TICK_PER_SECOND);
}

static void time_sync_complete(rt_err_t result, rt_bool_t synchronized,
                               unsigned long seconds, unsigned long microseconds)
{
    struct timeval utc_time;
    rt_bool_t notify = RT_FALSE;
    rt_enter_critical();
    if (time_sync_request_active)
    {
        if (synchronized)
        {
            utc_time.tv_sec = (time_t)seconds;
            utc_time.tv_usec = (suseconds_t)microseconds;

            /* The soft RTC setter is spinlock-protected and does not block. */
            if (settimeofday(&utc_time, RT_NULL) != 0)
            {
                result = -RT_ERROR;
                synchronized = RT_FALSE;
            }
        }

        if (synchronized)
        {
            time_sync_ever_succeeded = RT_TRUE;
            time_sync_last_success_tick = rt_tick_get();
            rt_strncpy(time_sync_last_success_server, time_sync_server,
                       sizeof(time_sync_last_success_server) - 1U);
            time_sync_last_success_server[sizeof(time_sync_last_success_server) - 1U] = '\0';
        }

        time_sync_callback_result = result;
        time_sync_callback_completed = RT_TRUE;
        time_sync_request_active = RT_FALSE;
        notify = RT_TRUE;
    }
    rt_exit_critical();

    if (notify)
    {
        rt_sem_release(&time_sync_result_sem);
    }
}

/* Called by lwIP from its TCP/IP thread after packet/source/originate checks. */
void bca_sntp_set_system_time(unsigned long seconds, unsigned long microseconds)
{
    if ((microseconds >= 1000000UL) ||
        (seconds < TIME_SYNC_MIN_UNIX_SECONDS) ||
        (seconds > TIME_SYNC_MAX_UNIX_SECONDS))
    {
        time_sync_complete(-RT_ERROR, RT_FALSE, seconds, microseconds);
        return;
    }

    time_sync_complete(RT_EOK, RT_TRUE, seconds, microseconds);
}

static void time_sync_start_on_tcpip_thread(void *parameter)
{
    LWIP_UNUSED_ARG(parameter);

    /* All raw SNTP API calls run in lwIP's required TCP/IP core context. */
    sntp_stop();
    sntp_setoperatingmode(SNTP_OPMODE_POLL);
    sntp_setservername(0, time_sync_server);
    sntp_init();

    if (!sntp_enabled())
    {
        time_sync_complete(-RT_ENOMEM, RT_FALSE, 0UL, 0UL);
    }
}

static void time_sync_stop_on_tcpip_thread(void *parameter)
{
    LWIP_UNUSED_ARG(parameter);
    sntp_stop();
}

static int time_sync_init(void)
{
    rt_err_t result;

    result = rt_mutex_init(&time_sync_mutex, "tsync", RT_IPC_FLAG_PRIO);
    if (result != RT_EOK)
    {
        return result;
    }

    result = rt_sem_init(&time_sync_result_sem, "tsevt", 0, RT_IPC_FLAG_FIFO);
    if (result != RT_EOK)
    {
        rt_mutex_detach(&time_sync_mutex);
        return result;
    }

    time_sync_initialized = RT_TRUE;
    return RT_EOK;
}
INIT_APP_EXPORT(time_sync_init);

static rt_bool_t time_sync_server_is_valid(const char *server, rt_size_t *length)
{
    rt_size_t i;
    rt_size_t size;

    if ((server == RT_NULL) || (length == RT_NULL))
    {
        return RT_FALSE;
    }

    size = rt_strlen(server);
    if ((size == 0U) || (size >= TIME_SYNC_SERVER_NAME_CAPACITY) ||
        (server[0] == '.') || (server[size - 1U] == '.'))
    {
        return RT_FALSE;
    }

    for (i = 0; i < size; i++)
    {
        char c = server[i];
        rt_bool_t alpha = ((c >= 'a') && (c <= 'z')) || ((c >= 'A') && (c <= 'Z'));
        rt_bool_t digit = (c >= '0') && (c <= '9');

        if (!alpha && !digit && (c != '-') && (c != '.'))
        {
            return RT_FALSE;
        }
        if ((c == '.') && (i > 0U) && (server[i - 1U] == '.'))
        {
            return RT_FALSE;
        }
    }

    *length = size;
    return RT_TRUE;
}

#ifdef RT_USING_FINSH
static void time_sync(int argc, char **argv)
{
    const char *requested_server = TIME_SYNC_DEFAULT_SERVER;
    rt_size_t server_length;
    rt_err_t result;
    rt_tick_t timeout_ticks;
    rt_bool_t callback_completed;
    rt_err_t callback_result;

    if ((argc < 1) || (argc > 2))
    {
        rt_kprintf("Usage: time_sync [ntp-server-hostname]\r\n");
        return;
    }
    if (argc == 2)
    {
        requested_server = argv[1];
    }
    if (!time_sync_initialized)
    {
        rt_kprintf("time_sync: time service initialization failed.\r\n");
        return;
    }
    if (!time_sync_server_is_valid(requested_server, &server_length))
    {
        rt_kprintf("time_sync: invalid server name (use 1-63 letters, digits, '-' or '.').\r\n");
        return;
    }
    if (rt_mutex_take(&time_sync_mutex, RT_WAITING_NO) != RT_EOK)
    {
        rt_kprintf("time_sync: another synchronization request is active.\r\n");
        return;
    }

    while (rt_sem_take(&time_sync_result_sem, RT_WAITING_NO) == RT_EOK)
    {
        /* Discard any stale completion token before starting a new request. */
    }

    rt_memcpy(time_sync_server, requested_server, server_length);
    time_sync_server[server_length] = '\0';
    rt_enter_critical();
    time_sync_request_active = RT_TRUE;
    time_sync_callback_completed = RT_FALSE;
    time_sync_callback_result = -RT_ERROR;
    rt_exit_critical();

    rt_kprintf("time_sync: querying %s (timeout %u ms)...\r\n",
               time_sync_server, (unsigned int)TIME_SYNC_WAIT_TIMEOUT_MS);
    result = tcpip_callback_with_block(time_sync_start_on_tcpip_thread, RT_NULL, 1);
    if (result != ERR_OK)
    {
        rt_enter_critical();
        time_sync_request_active = RT_FALSE;
        rt_exit_critical();
        rt_kprintf("time_sync: unable to schedule SNTP start (lwIP error %d).\r\n", result);
        rt_mutex_release(&time_sync_mutex);
        return;
    }

    timeout_ticks = rt_tick_from_millisecond((rt_int32_t)TIME_SYNC_WAIT_TIMEOUT_MS);
    result = rt_sem_take(&time_sync_result_sem, timeout_ticks);
    rt_enter_critical();
    callback_completed = time_sync_callback_completed;
    callback_result = time_sync_callback_result;
    if (!callback_completed)
    {
        time_sync_request_active = RT_FALSE;
    }
    rt_exit_critical();

    /* Stop retries on success, invalid time, or timeout. */
    if (tcpip_callback_with_block(time_sync_stop_on_tcpip_thread, RT_NULL, 1) != ERR_OK)
    {
        rt_kprintf("time_sync: warning: could not stop the SNTP client cleanly.\r\n");
    }

    if (callback_completed && (callback_result == RT_EOK))
    {
        rt_kprintf("time_sync: synchronized to UTC from %s.\r\n", time_sync_server);
    }
    else if (callback_completed)
    {
        if (callback_result == -RT_ENOMEM)
        {
            rt_kprintf("time_sync: unable to allocate the SNTP UDP control block.\r\n");
        }
        else
        {
            rt_kprintf("time_sync: server response had an invalid UTC date/time or RTC update failed.\r\n");
        }
    }
    else if (result == -RT_ETIMEOUT)
    {
        rt_kprintf("time_sync: timed out; no valid response within %u ms.\r\n",
                   (unsigned int)TIME_SYNC_WAIT_TIMEOUT_MS);
    }
    else
    {
        rt_kprintf("time_sync: synchronization failed (RT-Thread error %d).\r\n", result);
    }

    rt_mutex_release(&time_sync_mutex);
}
MSH_CMD_EXPORT(time_sync, synchronize UTC time using SNTP);

static void time_status(int argc, char **argv)
{
    struct timeval utc_time;
    struct tm utc_tm;
    rt_bool_t ever_succeeded;
    rt_bool_t valid;
    rt_tick_t last_success_tick;
    rt_tick_t age_ticks = 0;

    RT_UNUSED(argc);
    RT_UNUSED(argv);

    rt_enter_critical();
    ever_succeeded = time_sync_ever_succeeded;
    last_success_tick = time_sync_last_success_tick;
    if (ever_succeeded)
    {
        age_ticks = (rt_tick_t)(rt_tick_get() - last_success_tick);
    }
    valid = ever_succeeded && time_sync_age_is_valid(rt_tick_get(), last_success_tick);
    rt_exit_critical();

    if (!ever_succeeded)
    {
        rt_kprintf("UTC: unavailable; sync=NO (software RTC default is not trusted). Run time_sync.\r\n");
        return;
    }

    if (gettimeofday(&utc_time, RT_NULL) != 0 ||
        (gmtime_r(&utc_time.tv_sec, &utc_tm) == RT_NULL))
    {
        rt_kprintf("UTC: unavailable; RTC read failed.\r\n");
        return;
    }

    rt_kprintf("UTC: %04d-%02d-%02dT%02d:%02d:%02d.%06dZ (%s)\r\n",
               utc_tm.tm_year + 1900, utc_tm.tm_mon + 1, utc_tm.tm_mday,
               utc_tm.tm_hour, utc_tm.tm_min, utc_tm.tm_sec,
               (int)utc_time.tv_usec, valid ? "valid" : "stale");
    rt_kprintf("Sync: %s; age=%u s; server=%s\r\n",
               valid ? "valid" : "expired",
               (unsigned int)(age_ticks / RT_TICK_PER_SECOND),
               time_sync_last_success_server);
}
MSH_CMD_EXPORT(time_status, display synchronized UTC time and validity);
#endif /* RT_USING_FINSH */
