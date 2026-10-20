# SNTP time synchronization hardware test

The SNTP client is manual. It does not associate with Wi-Fi automatically and
does not affect the ICM20608 sampling loop.

1. Open the RT-Spark UART console at 115200 baud, 8-N-1.
2. Check Wi-Fi association using the existing command `wifi status`. If needed,
   connect with the existing private credential prompt; do not put a password
   in a FinSH command.
3. Run `time_status`. Before the first successful sync it must report UTC as
   unavailable; the software RTC's default 2018 value is not trusted.
4. Run `time_sync` to use `pool.ntp.org`, or `time_sync <hostname>` to use a
   different NTP server. The command waits up to 15 seconds and stops SNTP
   retries after success, invalid time, or timeout.
5. Run `time_status`. Confirm a UTC `...Z` timestamp marked valid and compare
   it with the laptop clock. The firmware accepts dates from 2024 through the
   signed 32-bit `time_t` limit (2038-01-19); synchronization validity expires
   after 24 hours without another successful manual sync.
6. Repeat `time_sync` while Wi-Fi is disconnected to verify a bounded failure.
   Confirm `main.c` continues reporting the sensor sampling diagnostics during
   the wait. No hardware test result is implied by this document.

The network must provide DNS resolution for a hostname and allow outbound UDP
to port 123 with its response. A router-local or laptop-local NTP server can be
used by passing its DNS name; the laptop MQTT broker is not itself an NTP
server.
