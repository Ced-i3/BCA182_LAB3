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
| RW007 Wi-Fi driver package | [RT-Thread-packages/rw007](https://github.com/RT-Thread-packages/rw007/tree/94df57f856bc2e8661022a379aa1c3d6a3bc5149), manifest revision `94df57f856bc2e8661022a379aa1c3d6a3bc5149` | [`LICENSE`](https://github.com/RT-Thread-packages/rw007/blob/94df57f856bc2e8661022a379aa1c3d6a3bc5149/LICENSE) and the repository README identify Apache-2.0. The pinned [`SConscript`](https://github.com/RT-Thread-packages/rw007/blob/94df57f856bc2e8661022a379aa1c3d6a3bc5149/SConscript) separately contains a `GPLv3` annotation linking to the build-package license. | The Apache repository license and the GPLv3 file annotation have not been reconciled. Their scope and effect on the package and project patches remain unresolved. Do not treat RW007 source or dependent patches as publication-cleared until the upstream project clarifies the annotation and the applicable terms are reviewed. |

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
- No project-wide license is declared. The license of the original dataset,
  the RW007 annotation, and any additional third-party notices discovered in
  a future source audit remain separate questions.
