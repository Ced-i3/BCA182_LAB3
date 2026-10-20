# Third-party notices

This inventory covers the pinned firmware sources in
[`firmware/project-source/dependency-manifest.json`](firmware/project-source/dependency-manifest.json)
and lwIP included by the pinned RT-Thread tree. It records license files and
source notices inspected in the corresponding local source trees. The
reconstruction package fetches upstream sources and applies project patches;
it does not include complete copies of these vendor repositories.

This is a source inventory, not a legal opinion or a declaration that every
combination is cleared for redistribution. Keep each upstream license,
copyright notice, file header, and applicable attribution intact. The
project has not declared an overall license.

## Components

| Component | Upstream source and pinned revision | Inspected license information | Attribution and redistribution notes |
| --- | --- | --- | --- |
| RT-Thread | [RT-Thread repository](https://github.com/RT-Thread/rt-thread/tree/99428a1e7f7447955aa860f7c969273a12095b8f), manifest revision `99428a1e7f7447955aa860f7c969273a12095b8f` | [`LICENSE`](https://github.com/RT-Thread/rt-thread/blob/99428a1e7f7447955aa860f7c969273a12095b8f/LICENSE), Apache-2.0 | Keep the license and applicable copyright and attribution notices. Preserve upstream file headers and mark modified files as required by the license. |
| CMSIS-Core package | [RT-Thread-packages/CMSIS-Core](https://github.com/RT-Thread-packages/CMSIS-Core/tree/39d8e01f0be84b83a8f11d33756e82ce1ef07a84), manifest revision `39d8e01f0be84b83a8f11d33756e82ce1ef07a84` | [`LICENSE.txt`](https://github.com/RT-Thread-packages/CMSIS-Core/blob/39d8e01f0be84b83a8f11d33756e82ce1ef07a84/LICENSE.txt), Apache-2.0 | Retain the license and applicable notices; preserve notices in source files. |
| STM32F4 CMSIS driver package | [RT-Thread-packages/stm32f4_cmsis_driver](https://github.com/RT-Thread-packages/stm32f4_cmsis_driver/tree/cf5edeedf133cffd3cf6e71432b0e6480b0a089c), manifest revision `cf5edeedf133cffd3cf6e71432b0e6480b0a089c` | [`LICENSE.md`](https://github.com/RT-Thread-packages/stm32f4_cmsis_driver/blob/cf5edeedf133cffd3cf6e71432b0e6480b0a089c/LICENSE.md), Apache-2.0 | Retain the license and applicable notices; preserve notices in source files. |
| STM32F4 HAL driver package | [RT-Thread-packages/stm32f4_hal_driver](https://github.com/RT-Thread-packages/stm32f4_hal_driver/tree/0993af03b227b20db0fda04950e17ffb465a1eac), manifest revision `0993af03b227b20db0fda04950e17ffb465a1eac` | [`LICENSE.md`](https://github.com/RT-Thread-packages/stm32f4_hal_driver/blob/0993af03b227b20db0fda04950e17ffb465a1eac/LICENSE.md), BSD-3-Clause; the inspected file identifies STMicroelectronics copyright | Retain the copyright, conditions, and disclaimer in source redistributions; reproduce them in documentation or other materials for binary redistributions. Do not use contributor names to endorse derived products without permission. |
| ICM20608 driver package | [RT-Thread-packages/icm20608](https://github.com/RT-Thread-packages/icm20608/tree/66e0b0971bda6dd934752ceadb0afeaeda7477ad), manifest revision `66e0b0971bda6dd934752ceadb0afeaeda7477ad` | [`LICENSE`](https://github.com/RT-Thread-packages/icm20608/blob/66e0b0971bda6dd934752ceadb0afeaeda7477ad/LICENSE), Apache-2.0 | Retain the license and applicable notices; preserve notices in source files. The upstream datasheet PDF is not included because redistribution rights have not been verified. |
| RW007 Wi-Fi driver package | [RT-Thread-packages/rw007](https://github.com/RT-Thread-packages/rw007/tree/94df57f856bc2e8661022a379aa1c3d6a3bc5149), manifest revision `94df57f856bc2e8661022a379aa1c3d6a3bc5149` | The pinned repository [`LICENSE`](https://github.com/RT-Thread-packages/rw007/blob/94df57f856bc2e8661022a379aa1c3d6a3bc5149/LICENSE) is Apache-2.0. Its [`README_ZH.md`](https://github.com/RT-Thread-packages/rw007/blob/94df57f856bc2e8661022a379aa1c3d6a3bc5149/README_ZH.md) explicitly says the RW007 package follows Apache 2.0. The English [`README.md`](https://github.com/RT-Thread-packages/rw007/blob/94df57f856bc2e8661022a379aa1c3d6a3bc5149/README.md) has a license sentence naming `at_device`, so it is not relied on alone. `src/spi_wifi_rw007.c` declares `SPDX-License-Identifier: Apache-2.0`. The pinned `SConscript` contains a header comment `@LICENSE: GPLv3` linking to the [buildpkg GPLv3 license](https://github.com/rtpkgs/buildpkg/blob/master/LICENSE). | The two project patches reproduce excerpts from `example/rw007_stm32_port.c` and `src/spi_wifi_rw007.c`; neither patch targets `SConscript`. The example has no file-level license header, so the root LICENSE and Chinese README are the inspected package-level evidence for it. No upstream text inspected says the SConscript annotation applies to the other source files. See the patch-specific review below; the annotation's intended scope has not been confirmed by the upstream maintainer. |

### lwIP included with RT-Thread

The pinned RT-Thread tree contains lwIP 2.0.3 at
[`components/net/lwip/lwip-2.0.3`](https://github.com/RT-Thread/rt-thread/tree/99428a1e7f7447955aa860f7c969273a12095b8f/components/net/lwip/lwip-2.0.3).
Its [`COPYING`](https://github.com/RT-Thread/rt-thread/blob/99428a1e7f7447955aa860f7c969273a12095b8f/components/net/lwip/lwip-2.0.3/COPYING)
file contains the Swedish Institute of Computer Science three-clause
BSD-style notice and disclaimer. Preserve the notice and terms in source
redistributions and reproduce them in documentation or other materials for
binary redistributions.

## Other publication exclusions

- The Run-or-Walk CSV is excluded while its redistribution terms remain
  unverified. The project owner's authorization for the corrected model
  artifact is not an independent determination of the dataset's rights.
- The laboratory PDF and ICM20608 datasheet PDF are excluded because
  redistribution permission has not been established.
- No project-wide license is declared. The redistribution rights for the
  original dataset, the intended scope of the RW007 SConscript annotation,
  and any additional third-party notices discovered in a future source audit
  remain separate questions.

## RW007 patch review at the pinned revision

The publication manifest pins RW007 to
`94df57f856bc2e8661022a379aa1c3d6a3bc5149`. The patches apply in manifest
order to that clean upstream revision and affect only these two C files:

- `patches/0002-rw007-stm32-port-startup.patch` modifies
  `example/rw007_stm32_port.c`. It adds a bounded five-second ready wait and
  propagates SPI attach, driver initialization, station-mode, serial-number,
  and firmware-version query errors. The reconstructed file now begins with a
  prominent comment naming the BCA182_LAB3 RT-Spark activity-recognition
  project and summarizing these changes. The upstream example had no
  file-level copyright or license header at the pinned revision; the package
  `LICENSE` and Chinese README are the inspected Apache-2.0 evidence.
- `overlays/rt-thread/bsp/stm32/stm32f407-rt-spark/local-patches/rw007-secure-credential-entry.patch`
  modifies `src/spi_wifi_rw007.c`. It validates join/SoftAP credentials,
  clears temporary and queued credential copies, and handles failed packet
  allocation or delivery. Its new prominent modification comment is placed
  after the existing Real-Thread copyright and Apache-2.0 SPDX header; neither
  upstream notice is removed or replaced.

The inserted comments identify the project changes and state that upstream
copyright and Apache-2.0 notices remain applicable. They do not claim that the
project authored the upstream files, add a competing license, or invent an
author or date. Comparison of the C files immediately before and after
comment insertion confirmed their functional content was otherwise
byte-for-byte unchanged.

The pinned RW007 repository has no `NOTICE` file. The exact upstream Apache
license text is included at
[`firmware/project-source/licenses/rw007-Apache-2.0.txt`](firmware/project-source/licenses/rw007-Apache-2.0.txt)
to accompany redistribution of these patch excerpts. Apache-2.0 section 4
requires providing the license to recipients, keeping applicable upstream
copyright, patent, trademark, and attribution notices in distributed source,
and making modified files carry prominent change notices
([Apache-2.0 section 4](https://www.apache.org/licenses/LICENSE-2.0#redistribution)).
The reconstructed files now meet the identified notice conditions on the
inspected evidence; this is not a legal opinion or a complete audit of every
possible distribution.

The GPLv3 annotation is in the separate upstream `SConscript`, which neither
patch targets nor changes. It is included when the reconstruction fetches the
full upstream tree, but this project repository distributes the patch package
rather than a bundled RW007 checkout. No inspected upstream README or license
text extends the SConscript annotation to `src/spi_wifi_rw007.c` or
`example/rw007_stm32_port.c`. The annotation remains present and has not been
withdrawn; its intended scope beyond `SConscript` itself has not been
confirmed by the upstream maintainer. Clarification would be needed before
making a broader claim about redistributing a full RW007 source checkout.

Apache-2.0 conditions do not depend on whether a repository upload is private
or public. For these two patch targets, the available file-level and
repository-level evidence supports retaining the patches with the included
license and embedded notices. That finding does not itself clear unrelated
project materials or establish rights for a full reconstructed vendor-source
bundle.
