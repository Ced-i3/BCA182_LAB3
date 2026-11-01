# RT-Spark STM32 setup and streaming

This procedure assumes the project firmware is already installed on the
RT-Spark, the laptop and board use the same trusted private network, and the
broker and Flask backend are configured and running. For cloud monitoring,
also start the sync worker as described in [Phase 12](PHASE12_REMOTE_MONITORING.md).
For firmware reconstruction, see [the project-source guide](firmware/project-source/README.md).

## Connect and open the console

1. Connect the RT-Spark to the laptop using its serial connection and power it.
2. Open Microsoft Serial Monitor in VS Code. Select the board's actual COM port
   as shown by Windows Device Manager; the number can differ between machines.
3. Set **115200 baud, 8 data bits, no parity, 1 stop bit (8-N-1)** and **CR**
   as the line ending. Connect and press Enter to see the shell prompt.

## Connect to Wi-Fi and synchronize UTC

At the board shell, replace `YOUR_SSID` with the network name:

```text
wifi join YOUR_SSID
wifi status
```

The firmware prompts for the Wi-Fi password without echo. Enter it at that
hidden prompt and press Enter; do not put it in the command, source, or a
shared file. Check `wifi status` for association and a DHCP IPv4 address.

```text
time_sync
time_status
```

Confirm `time_status` reports valid UTC. The default `time_sync` server requires
working DNS and outbound NTP (UDP port 123). Time validity expires after 24
hours without another successful synchronization.

## Configure the laptop broker

Run `ipconfig` in a laptop PowerShell or Command Prompt window. Find the
**IPv4 Address** of the Wi-Fi adapter on the same private network as the
board. Configure the LAN listener in the local `backend/broker.yaml` to use
that address and start aMQTT and Flask in separate terminals as described in
[backend setup](backend/README.md). Keep the broker on the trusted private
LAN; the board's MQTT connection is anonymous plaintext.

At the board shell, replace `YOUR_LAPTOP_IPV4` with the current address:

```text
mqtt_stream status
mqtt_stream stop
mqtt_config set broker YOUR_LAPTOP_IPV4
mqtt_config set port 1883
mqtt_config set device_id rt-spark-001
mqtt_config show
```

Wait for stopped status before changing configuration. These settings are
RAM-only and revert to firmware defaults after reboot; check and set them again
when needed. Use the configured cloud device ID for the intended cloud demo.

## Start and stop

```text
mqtt_stream start 5
mqtt_stream status
```

The IMU acquisition loop runs at approximately 25 Hz. At this setting the
publisher selects samples for MQTT at 5 Hz; it does not average them. Check
the status counters and the [dashboard](https://bca182-lab3.vercel.app) for
fresh data. Predictions are experimental, not validated activity labels.

When finished:

```text
mqtt_stream stop
mqtt_stream status
```

Streaming is off after reboot and must be started manually after Wi-Fi and UTC
are ready.

## Troubleshooting

- **No board IPv4:** run `wifi status`, check the correct network and DHCP,
  and reconnect through the hidden prompt. Check that the laptop has an IPv4
  address on the same reachable network too.
- **Wi-Fi disconnected:** rejoin with `wifi join YOUR_SSID`, enter the password
  at the hidden prompt, and check `wifi status`. Avoid guest/client-isolated
  networks that block access to the laptop.
- **UTC invalid:** check Wi-Fi, DNS, and outbound UDP 123, then rerun
  `time_sync` and `time_status`. See the [time test guide](firmware/project-source/overlays/rt-thread/bsp/stm32/stm32f407-rt-spark/TIME_SYNC_TEST.md).
- **Broker IP changed:** check `ipconfig`, update the local broker listener,
  restart the broker, stop the board stream, and set the current laptop IPv4
  with `mqtt_config set broker YOUR_LAPTOP_IPV4`.
- **Configuration rejected while active:** run `mqtt_stream stop` and wait
  until `mqtt_stream status` reports stopped, then set the values and restart.
- **COM port unavailable:** close other serial monitors using the port, check
  the cable and Device Manager, then select the board's current COM port.
- **Dashboard stale:** check `mqtt_stream status`, Wi-Fi, valid UTC, broker and
  Flask health, and the cloud-sync worker's output and connectivity. Check the
  device ID and timestamps; existing cloud rows can be historical. See
  [remote monitoring](PHASE12_REMOTE_MONITORING.md) for backlog behavior.
