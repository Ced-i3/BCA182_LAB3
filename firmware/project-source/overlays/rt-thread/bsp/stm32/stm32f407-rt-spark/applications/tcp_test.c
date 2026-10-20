/*
 * One-shot TCP reachability check for the local MQTT broker.
 * This command only tests the TCP handshake; it does not send MQTT data.
 */

#include <rtthread.h>
#include <string.h>

#ifdef RT_USING_FINSH
#include <finsh.h>
#include <lwip/inet.h>
#include <lwip/sockets.h>

#include "mqtt_config.h"

#define TCP_TEST_TIMEOUT_SECONDS 3

static void tcp_test(int argc, char **argv)
{
    int sock = -1;
    int result;
    int error_code;
    int resolve_result;
    int socket_error = 0;
    rt_uint32_t nonblocking = 1;
    rt_uint32_t broker_address;
    socklen_t option_length;
    struct sockaddr_in server_address;
    struct timeval timeout;
    fd_set write_set;
    fd_set exception_set;
    struct mqtt_config_values config;

    if (argc != 1)
    {
        rt_kprintf("Usage: tcp_test\r\n");
        return;
    }

    mqtt_config_get(&config);
    rt_kprintf("TCP test: connecting to %s:%u (timeout %u s)...\r\n",
               config.broker_host, (unsigned int)config.broker_port,
               TCP_TEST_TIMEOUT_SECONDS);

    resolve_result = mqtt_config_resolve_ipv4(config.broker_host, &broker_address);
    if (resolve_result != 0)
    {
        rt_kprintf("TCP test FAIL: resolving broker host %s failed (lwIP error=%d).\r\n",
                   config.broker_host, resolve_result);
        return;
    }

    sock = lwip_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock < 0)
    {
        rt_kprintf("TCP test FAIL: socket() errno=%d\r\n", (int)rt_get_errno());
        return;
    }

    if (lwip_ioctl(sock, FIONBIO, &nonblocking) < 0)
    {
        error_code = (int)rt_get_errno();
        rt_kprintf("TCP test FAIL: setting nonblocking mode errno=%d\r\n", error_code);
        goto close_socket;
    }

    rt_memset(&server_address, 0, sizeof(server_address));
    server_address.sin_family = AF_INET;
    server_address.sin_port = lwip_htons(config.broker_port);
    server_address.sin_addr.s_addr = broker_address;

    result = lwip_connect(sock, (const struct sockaddr *)&server_address,
                          sizeof(server_address));
    if (result == 0)
    {
        rt_kprintf("TCP test PASS: connected to %s:%u\r\n",
                   config.broker_host, (unsigned int)config.broker_port);
        goto close_socket;
    }

    error_code = (int)rt_get_errno();
    if (error_code != EINPROGRESS)
    {
        rt_kprintf("TCP test FAIL: connect() errno=%d\r\n", error_code);
        goto close_socket;
    }

    FD_ZERO(&write_set);
    FD_ZERO(&exception_set);
    FD_SET(sock, &write_set);
    FD_SET(sock, &exception_set);
    timeout.tv_sec = TCP_TEST_TIMEOUT_SECONDS;
    timeout.tv_usec = 0;

    result = lwip_select(sock + 1, RT_NULL, &write_set, &exception_set, &timeout);
    if (result == 0)
    {
        rt_kprintf("TCP test FAIL: connection timed out after %u s\r\n",
                   TCP_TEST_TIMEOUT_SECONDS);
        goto close_socket;
    }
    if (result < 0)
    {
        rt_kprintf("TCP test FAIL: select() errno=%d\r\n", (int)rt_get_errno());
        goto close_socket;
    }
    if (!FD_ISSET(sock, &write_set) && !FD_ISSET(sock, &exception_set))
    {
        rt_kprintf("TCP test FAIL: select() returned without socket readiness\r\n");
        goto close_socket;
    }

    option_length = sizeof(socket_error);
    if (lwip_getsockopt(sock, SOL_SOCKET, SO_ERROR, &socket_error,
                        &option_length) < 0)
    {
        rt_kprintf("TCP test FAIL: getsockopt(SO_ERROR) errno=%d\r\n",
                   (int)rt_get_errno());
        goto close_socket;
    }
    if (socket_error != 0)
    {
        rt_kprintf("TCP test FAIL: connect completion errno=%d\r\n", socket_error);
        goto close_socket;
    }

    rt_kprintf("TCP test PASS: connected to %s:%u\r\n",
               config.broker_host, (unsigned int)config.broker_port);

close_socket:
    if (lwip_close(sock) < 0)
    {
        rt_kprintf("TCP test WARNING: close() errno=%d\r\n", (int)rt_get_errno());
    }
}

MSH_CMD_EXPORT(tcp_test, test TCP connection to the local MQTT broker);
#endif /* RT_USING_FINSH */
