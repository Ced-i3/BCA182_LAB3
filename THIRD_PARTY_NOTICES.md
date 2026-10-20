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
`94df57f856bc2e8661022a379aa1c3d6a3bc5149`. The two patches apply to that
clean upstream revision and target only:

- `patches/0002-rw007-stm32-port-startup.patch` changes
  `example/rw007_stm32_port.c`. The file has no file-level license header at
  this revision. The repository-level `LICENSE` and `README_ZH.md` identify
  the package as Apache-2.0. The English `README.md` has a license sentence
  naming `at_device`, inconsistent with the repository and Chinese README;
  it is not relied on alone for RW007's license.
- `overlays/rt-thread/bsp/stm32/stm32f407-rt-spark/local-patches/rw007-secure-credential-entry.patch`
  changes `src/spi_wifi_rw007.c`, whose upstream header retains Real-Thread's
  copyright notice and explicitly declares Apache-2.0. The patch does not
  alter or remove that header.

Both patches include upstream source excerpts in their unified-diff context
and removed/changed lines. On the inspected file-specific and repository-level
evidence, Apache-2.0 is the applicable upstream license for those excerpts.
The GPLv3 annotation is present in the separate `SConscript` header and points
to the buildpkg license. The `SConscript` is not included in either patch, and
the RW007 `README_ZH.md` and LICENSE identify the package as Apache-2.0. No
inspected upstream documentation describes the SConscript annotation as
applying to `src/` or `example/`. This supports not extending the GPLv3
annotation to the two patched files. The upstream maintainer is needed to
conclusively clarify the intended scope if the annotation was meant as
package-wide metadata.

The pinned RW007 repository has no `NOTICE` file. The exact upstream Apache
license text is included at
[`firmware/project-source/licenses/rw007-Apache-2.0.txt`](firmware/project-source/licenses/rw007-Apache-2.0.txt)
to accompany redistribution of these patch excerpts. For Apache-2.0
redistribution, preserve applicable upstream copyright and attribution
notices, provide a copy of the license, and make modified files carry
prominent notices stating that they were changed ([Apache-2.0 section 4](https://www.apache.org/licenses/LICENSE-2.0#redistribution)).
The existing driver copyright/SPDX header is retained by the patch. The
current patches do not add an explicit changed-file notice to the resulting C
files, so this review does not certify that the modified-file notice
condition is met if the patches are distributed/applied as source. Resolve
that condition by adding suitable notices through the patches or obtaining a
documented licensing review of the patch-only distribution before publishing.

The Apache-2.0 conditions do not turn on whether the GitHub repository is
private or public. A private upload is therefore not treated here as an
exception to the license conditions. The RW007 file-specific evidence narrows
the GPLv3 concern but does not by itself clear the current patch form for
private upload or public redistribution while the changed-file notice
condition remains unresolved.
