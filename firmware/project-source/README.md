# RT-Spark firmware source reconstruction

This directory contains this project's RT-Spark firmware changes, not a copy of
RT-Thread. `dependency-manifest.json` pins six upstream Git commits. The
`reconstruct.py` script fetches those commits, applies the patches once in
manifest order, then copies the BSP overlays. It refuses to overwrite a
destination. `inventory.csv` records every exported local change, its original
path, representation, purpose, upstream dependency, sensitive-configuration
assessment, and source hashes.

## Requirements

- Python 3.13 and Git; access to the pinned upstream repositories, or local
  clones of those repositories at the manifest commits.
- ARM GCC 12.3.1 and SCons 4.11.1 for the verified build. The BSP's
  `rtconfig.py` reads `RTT_EXEC_PATH`, so a global toolchain setting is not
  required.
- Sufficient storage for a separate RT-Thread checkout and build output.

From the project root, reconstruct into a **new** destination:

```powershell
python firmware/project-source/reconstruct.py --destination firmware/reconstruction-work/rt-thread
```

The script downloads from the URLs in the manifest by default. If the six
upstream repositories already exist locally, use `--source NAME=PATH` once per
dependency. Names are exactly those in the manifest. This was the method used
for the local verification; it used committed upstream trees, never the
uncommitted contents of the working firmware checkout. For example:

```powershell
python firmware/project-source/reconstruct.py `
  --destination firmware/reconstruction-work/rt-thread `
  --source RT-Thread=firmware/rt-thread `
  --source CMSIS-Core=firmware/rt-thread/bsp/stm32/stm32f407-rt-spark/packages/CMSIS-Core-latest `
  --source stm32f4_cmsis_driver=firmware/rt-thread/bsp/stm32/stm32f407-rt-spark/packages/stm32f4_cmsis_driver-latest `
  --source stm32f4_hal_driver=firmware/rt-thread/bsp/stm32/stm32f407-rt-spark/packages/stm32f4_hal_driver-latest `
  --source icm20608=firmware/rt-thread/bsp/stm32/stm32f407-rt-spark/packages/icm20608-latest `
  --source rw007=rw007-download
```

The local-source option is useful when GitHub is unreachable. It does not
prove that remote downloads are currently available. The script compares
the reconstructed files with the hashes recorded in `inventory.csv`. The
working `applications/main.c` uses LF while Git patch application produces
CRLF; the verified content is identical after line-ending normalization.

## Patch and overlay order

1. Patch the RT-Thread v5.3.0 checkout with
   `patches/0001-rt-thread-project-changes.patch`. This contains the BSP
   configuration, sensor acquisition, WLAN, and lwIP/SNTP changes.
2. Fetch the four STM32/CMSIS and sensor packages and RW007 at the manifest
   revisions into the BSP `packages/` paths.
3. Apply the ICM20608 safety, range-readback, then startup-reliability
   patches listed in the manifest to that package.
4. Apply the RW007 secure-credential patch and then
   `patches/0002-rw007-stm32-port-startup.patch` to RW007.
5. Copy `overlays/rt-thread/` into the reconstructed checkout. These are
   project application sources, local engineering notes, and the required
   ignored `packages/Kconfig` file.

The historical `local-patches/lwip-sntp-allocation-failure.patch` is kept in
the overlay for provenance. **Do not apply it separately:** its change is
already in the RT-Thread patch at step 1. Similarly, the other historical
patch files copied into the BSP are applied only via the manifest entries.

## Build and local operation

From the reconstructed BSP directory in PowerShell:

```powershell
Set-Location firmware/reconstruction-work/rt-thread/bsp/stm32/stm32f407-rt-spark
$env:RTT_EXEC_PATH = '<path to existing ARM GCC bin directory>'
python '<path to SCons 4.11.1 scons.py>' -j1
```

A successful build creates `rt-thread.elf`, `rtthread.bin`, and `rtthread.hex`
inside that BSP directory. This source package was verified with ARM GCC
12.3.1 and SCons 4.11.1 in a separate reconstruction on Windows using `-j1`.
An initial `-j4` attempt stopped at an object compile without a diagnostic;
the serial retry completed. Build success
does not verify sensor behavior, Wi-Fi, or MQTT on another board. Check the
target MCU and obtain authorization before flashing hardware.

The UART shell is at 115200 baud on the board's enumerated COM port. Connect
to Wi-Fi manually using the existing private credential prompt; do not place
the password in a shell command, file, or firmware constant. Run `time_sync`
and confirm `time_status` reports valid UTC. Use `mqtt_config show` and, if
necessary, `mqtt_config set broker HOST`, `mqtt_config set port PORT`, and
`mqtt_config set device_id ID` for a private-LAN broker. Run
`mqtt_stream start` only after Wi-Fi and UTC are valid; `mqtt_stream status`
and `mqtt_stream stop` provide diagnostics and shutdown. Settings are RAM-only.
See the root README and `MQTT_STREAM_TEST.md` in the overlay for the tested
local pipeline.

## Licenses and publication limits

This package distributes project patches and original application files;
the reconstruction obtains third-party sources from their own repositories.
Keep all upstream license files and notices in reconstructed sources. The
audited RT-Thread, CMSIS-Core, STM32F4 CMSIS, and ICM20608 repositories carry
Apache-2.0 licenses; the STM32F4 HAL package carries BSD-3-Clause terms.
The pinned RW007 repository `LICENSE` and Chinese README identify the package
as Apache-2.0, and `src/spi_wifi_rw007.c` carries an Apache-2.0 SPDX header.
The two project patches add prominent changed-file notices to
`example/rw007_stm32_port.c` and `src/spi_wifi_rw007.c`; the latter keeps its
upstream Real-Thread copyright and SPDX header. The separate `SConscript`
contains a GPLv3 annotation, but no inspected upstream text says it applies to
either patched C file. Its intended wider scope remains unconfirmed. See the
[third-party notices](../../THIRD_PARTY_NOTICES.md) for evidence and limits.
lwIP source contains its own BSD-style headers; do not replace or remove them.

The original working tree also contains a third-party ICM20608 datasheet PDF.
It is **not** included here because redistribution rights are unverified.
The course PDF, Run-or-Walk CSV, runtime SQLite database, private broker
configuration, and credentials remain outside the proposed public staging set.
The project owner authorized inclusion of the existing corrected `.joblib`
model in `backend/models/`; this does not establish permission to redistribute
the original dataset. The model remains experimental on RT-Spark hardware.
