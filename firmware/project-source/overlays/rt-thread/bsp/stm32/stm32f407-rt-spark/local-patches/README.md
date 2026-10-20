# Local ICM20608 package patch

The checked-out upstream package is `RT-Thread-packages/icm20608` at commit
`66e0b0971bda6dd934752ceadb0afeaeda7477ad`. Its source under `packages/icm20608-latest`
contains the locally applied changes represented by `icm20608-local-safety.patch`.

The patch is kept separately so the vendor-source delta is auditable and can be reapplied
from the package directory after restoring that exact upstream revision (`git apply
../../local-patches/icm20608-local-safety.patch`, adjusting the relative path if run
from elsewhere). It corrects mutex ownership and cleanup, rejects zero calibration
samples, and verifies WHO_AM_I (`0x75 == 0xAF`) over I2C before device configuration.
The additional `icm20608-range-readback.patch` makes the range getter preserve its
output argument when the I2C read fails; apply it after the safety patch. Apply
`icm20608-startup-reliability.patch` afterward for bounded WHO_AM_I retries and a
mutex name that fits this BSP's `RT_NAME_MAX`.

The integrated RW007 package is copied from `rw007-download` at commit
`94df57f856bc2e8661022a379aa1c3d6a3bc5149`. Its local credential-handling
changes are recorded in `rw007-secure-credential-entry.patch`. The patch clears
temporary join/SoftAP command payloads before releasing their SPI packets and
fixes the password terminator boundary. The RW007 packet reserves 32 bytes for
its password string, so the hidden prompt accepts at most 31 characters to
leave room for the NUL terminator. The integrated package copy contains the
applied patch; the original clone remains unchanged.

The RT-Thread lwIP 2.0.3 SNTP client has one BSP-local safety adjustment in
`components/net/lwip/lwip-2.0.3/src/apps/sntp/sntp.c`, recorded in
`lwip-sntp-allocation-failure.patch`: failure to allocate its UDP PCB is
reported through the existing SNTP debug channel and leaves the client
disabled, instead of tripping a fatal `LWIP_ASSERT`. The `time_sync` command
detects the disabled client and reports the allocation failure. This change is
limited to the SNTP initialization error path.
