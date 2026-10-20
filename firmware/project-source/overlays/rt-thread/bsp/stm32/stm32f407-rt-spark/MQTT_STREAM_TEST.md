# Continuous sensor MQTT hardware test

The motion publisher is disabled after boot. It sends genuine ICM20608 samples
to the configured broker on `lab3/sensors/motion`; it does not connect Wi-Fi or
perform SNTP automatically. The Phase 4A RAM-only MQTT configuration firmware
was flashed and its configuration behavior and streaming regression were
physically tested. The local broker and device continue to use the development
network configuration described below.

## Before starting

1. Start the local aMQTT broker and Flask backend using the existing commands
   in `backend/README.md`. Confirm `/health` reports `mqtt_connected=true`.
2. Run `mqtt_config show`. The development defaults are
   `192.168.1.11:1883` and device ID `rt-spark-001`. If needed, set the broker
   host or IPv4 address, port, and a unique device ID using the commands below.
   Confirm the configured broker is reachable on the private LAN, and leave the
   Flask subscriber connected to `lab3/sensors/motion`.
3. Open the board UART at 115200 baud, 8-N-1. Check `wifi status`; connect using
   the existing private credential-entry procedure if needed.
4. Run `time_status`. It must show a valid recent UTC time. If it does not, run
   `time_sync` manually and check `time_status` again.

## Start and observe

```text
mqtt_stream status
mqtt_stream start
mqtt_stream status
```

`start` defaults to 5 Hz. An optional integer rate from 1 to 25 can be given,
for example `mqtt_stream start 10`. The 25 Hz acquisition is decimated with a
phase accumulator; samples are not averaged. At 5 Hz, every fifth valid sensor
sample is timestamped immediately after acquisition and put into a static
10-sample FIFO. The publisher thread converts and publishes queued samples
outside the acquisition path. If the clock is invalid, the selected sample is
dropped; if the queue is full, the newest selected sample is dropped.

At 5 Hz, each JSON message uses the backend schema:

```json
{"device_id":"rt-spark-001","timestamp":"2026-10-18T12:34:56.789Z","accel_m_s2":{"x":0.123,"y":-0.456,"z":9.807},"gyro_rad_s":{"x":0.010,"y":-0.020,"z":0.030}}
```

Verify the actual message in the Flask/backend history or a temporary MQTT
subscriber, and check the `mqtt_stream status` counters and one-second sensor
diagnostics. Do not use simulated publisher output as proof of board streaming.

## Stop

```text
mqtt_stream stop
mqtt_stream status
```

The stop command waits up to eight seconds for bounded socket operations to
finish. Queued but unsent samples are counted as stop drops. Streaming remains
off after reset; run `mqtt_stream start` manually after Wi-Fi and UTC are ready.

The development defaults use anonymous MQTT against `192.168.1.11:1883`; keep
the broker restricted to the private LAN. The broker must permit outbound board
TCP connections and the backend subscriber must be online. MQTT QoS 1 requires
PUBACK; if the connection fails while a publish is in flight, the board counts
the sample as a failed publish and does not retry that ambiguous sample, so a
message may have reached the broker even if the board did not observe PUBACK.

## MQTT connection configuration

Settings are held in RAM. After reset they return to the development defaults
(`192.168.1.11:1883`, device ID `rt-spark-001`). Use:

```text
mqtt_config show
mqtt_config set broker <IPv4-address-or-hostname>
mqtt_config set port <1-65535>
mqtt_config set device_id <unique-device-id>
```

The device ID accepts 1–32 ASCII letters, digits, dots, underscores, or
hyphens; its first and last characters must be letters or digits. Choose a
different ID for each board. The derived MQTT client IDs are
`bca152-<device-id>-test` for `mqtt_test` and
`bca152-<device-id>-stream` for `mqtt_stream`.

The broker host accepts an IPv4 literal or DNS hostname. Hostname lookup uses
the enabled lwIP resolver and the DNS server supplied by the network
configuration. Run configuration commands before starting the publisher;
updates are rejected while it is starting, streaming, or stopping. `tcp_test`
and both MQTT connection paths use the same configured host and port. Settings
are not written to Flash, and `mqtt_config show` does not display Wi-Fi
credentials.

## Phase 4A configuration and streaming regression (verified)

The Phase 4A firmware's broker/device settings were verified on the RT-Spark.
The regression delivered 106 genuine messages at approximately 5.01 messages
per second. SQLite increased from 146 to 252 raw rows, all associated with
`rt-spark-001`. Acquisition remained approximately 25 Hz with zero missed
deadlines, I²C errors, publisher failures, or sample drops. Configuration
changes while streaming were rejected, settings could be changed while
stopped, and the stream returned to stopped state. These observations verify
the configuration and transport regression, not activity-recognition
accuracy.

For a future repeat test, use COM4 at 115200 baud, 8-N-1 and:

1. Check `wifi status` and `time_status`; associate manually and synchronize
   UTC if needed.
2. Run `mqtt_config show`, set the broker host/port and a unique device ID,
   then run `mqtt_config show` again to confirm the values.
3. To test DNS, configure a hostname that the Wi-Fi network's DNS server is
   known to resolve to the laptop. Run `tcp_test`; if local DNS does not resolve
   the laptop name, repeat with its private IPv4 address and record hostname
   resolution as unverified.
4. Run `mqtt_test` and confirm its test-topic message at the broker. Start a
   temporary observer and Flask subscriber before `mqtt_stream start`.
5. During streaming, try setting the device ID to its current value. The
   command should reject the update while the stream is active. Check that the
   configured ID remains in published messages, then run `mqtt_stream stop`
   and `mqtt_stream status`.
6. Verify observer receipt, backend API results, new SQLite rows, and sensor
   timing/publisher counters. Do not treat the earlier baseline as evidence
   that this new image has passed these checks.

## Verified physical run (2026-10-18)

The RT-Spark STM32F407ZGT6 was associated with Wi-Fi and reported valid
SNTP-synchronized UTC. The laptop broker remained reachable at
`192.168.1.11:1883`; the board's `tcp_test` passed and Flask `/health` reported
`mqtt_connected=true` for `lab3/sensors/motion`.

The board ran `mqtt_stream start` for about 28 seconds, then `mqtt_stream stop`.
An independent temporary MQTT subscriber received 140 messages in 27.8
seconds (about 5.0 messages/s). The payloads used the expected fields and
`device_id` `rt-spark-001`; the observer's first and last messages contained
UTC timestamps and six-axis values converted to m/s² and rad/s.

SQLite had 6 rows before the run and 146 afterward. All 140 added records
belonged to `rt-spark-001`. Flask `/api/latest` returned row 146 and
`/api/history?limit=5` returned the newest records. During the run, UART
diagnostics reported 25.0 Hz acquisition, 25.0 Hz valid samples, zero missed
deadlines, and zero I²C errors. Final publisher status reported 140 queued and
140 sent, with zero invalid-time drops, unsynchronized drops, queue-full
drops, stop drops, publish failures, connection failures, reconnects,
Wi-Fi disconnects, or connection drops. After stopping, status showed the
publisher stopped with an empty queue; no additional messages appeared in the
observer before it was closed. COM4 and the temporary observer were closed
after the test.

This verifies stationary end-to-end sensor transport and storage for this
configuration. It does not verify walking/running classifier performance,
long-duration reliability, or portable setup on another network. The new
configurable firmware has compiled, but its shell commands, hostname lookup,
and active-stream change protection still require physical verification.
