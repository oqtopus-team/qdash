# Third-Party Licenses

QDash, licensed under Apache 2.0, uses the Quantum Machines packages below for its
[Quantum Machines backend](../user-guide/setup/qm-backend.md). They are installed only with the
workflow `qm` extra, or the `qm-cloud` extra that adds `qm-saas`; QDash includes no copy of their
source code.

| Package | Version | License | Copyright | Used for |
| --- | --- | --- | --- | --- |
| [`qm-qua`](https://github.com/qm-labs/qm-qua-sdk-public) | 1.5.0 | BSD-3-Clause | Copyright 2021 Q.M Technologies Ltd. | QOP server connection, QUA programs, simulator |
| [`qualang-tools`](https://github.com/qua-platform/py-qua-tools) | 0.23.0 | BSD-3-Clause | Copyright 2021 Q.M. Technologies Ltd. | Rabi experiment (`QUA_calibrations`) run by **QMAmplitudeRabi** |
| [`qm-saas`](https://pypi.org/project/qm-saas/) | 1.2.0 | BSD-3-Clause | Copyright 2024 Q.M Technologies Ltd. | QM cloud simulator instances (`qm-cloud` extra only) |

The extras also install these packages that QDash did not already depend on:

| Package | Version | License |
| --- | --- | --- |
| `datadog-api-client` | 2.62.0 | Apache-2.0 |
| `deprecation` (`qm-cloud` extra only) | 2.1.0 | Apache-2.0 |
| `grpcio` | 1.85.1 | Apache-2.0 |
| `marshmallow` | 3.26.2 | MIT |
| `marshmallow-polyfield` | 5.11 | Apache-2.0 |
| `tinydb` | 4.9.0 | MIT |
| `xarray` | 2024.11.0 | Apache-2.0 |

Each package ships its full license text in its installed distribution metadata. A distribution
of QDash that bundles these packages, such as a container image built with the `qm` extra, must
keep those license files.

## qm-saas License

The license of `qm-saas` 1.2.0, as shipped in its wheel (`qm_saas-1.2.0.dist-info/licenses/LICENSE`):

```text
Copyright 2024 Q.M Technologies Ltd.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
