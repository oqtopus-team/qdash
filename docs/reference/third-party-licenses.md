# Third-Party Licenses

QDash is licensed under Apache 2.0. The optional workflow `qm` extra, used by the `qm` and
`qm-fake` backends of the [Quantum Machines backend](../user-guide/setup/qm-backend.md), installs
the Quantum Machines packages below; each package stays under its own license. The QDash
adapter and the `qm-fake` device include no copied Quantum Machines source code; they call the
installed packages, which retain their own source and notices. The workflow Docker images do not
install the extra, so a deployment that runs either backend installs it itself and takes on the
redistribution terms below when it distributes the result.

## Quantum Machines Packages

| Package | Version | License | Copyright | Used for |
| --- | --- | --- | --- | --- |
| [`qm-qua`](https://github.com/qm-labs/qm-qua-sdk-public) | 1.5.0 | BSD-3-Clause | Copyright 2021 Q.M Technologies Ltd. | QOP server connection, QUA programs, simulator requests; offline configuration validation and program decoding on `qm-fake` |
| [`qualang-tools`](https://github.com/qua-platform/py-qua-tools) | 0.23.0 | BSD-3-Clause | Copyright 2021 Q.M. Technologies Ltd. | Rabi experiment (`QUA_calibrations`) and `demod2volts`, run by **QMAmplitudeRabi** on `qm` and `qm-fake` |

These facts come from the distributions that `uv.lock` pins, identified by their SHA-256 hashes.
Each wheel and its source distribution ship the same `LICENSE` file, with no other license or
notice file, and that file is the BSD-3-Clause text with the copyright line above.

| Distribution | SHA-256 |
| --- | --- |
| `qm_qua-1.5.0-py3-none-any.whl` | `d2eb0ecd7f5e9124692f7f7c24f79e2adc5895a1dfe2539ad6658370b0c12135` |
| `qm_qua-1.5.0.tar.gz` | `76f5a844c38fadd281f77bf7090403e51809fdb809d601eb4ea44d6dd447a667` |
| `qualang_tools-0.23.0-py3-none-any.whl` | `f4de9702509cb2944fa0ac91367dadcdad092cc8e7d3d9c83f7fec4ad2171fe6` |
| `qualang_tools-0.23.0.tar.gz` | `6d10fd6da3ac9fe191bc59edc42bcc54839885e7bd25646269fd870a8cc75b2c` |

The licenses cover the software packages only. Use of an OPX, a QOP server, and other Quantum
Machines products or services is governed by your agreements with Quantum Machines.

## Packages the qm Extra Adds

The `qm` extra also installs these packages, which the workflow environment does not otherwise
include. Each installed distribution keeps the listed files in its `.dist-info` directory.

| Package | Version | Declared license | License files | Other notices in the distribution |
| --- | --- | --- | --- | --- |
| `datadog-api-client` | 2.62.0 | Apache-2.0 | `LICENSE`, `NOTICE`, `LICENSE-3rdparty.csv` | None |
| `grpcio` | 1.85.1 | Apache-2.0 | `LICENSE` | `LICENSE` also holds BSD-3-Clause and MPL-2.0 texts for parts of the gRPC project; the bundled `grpc/_cython/_credentials/roots.pem` is MPL-2.0 |
| `marshmallow` | 3.26.2 | MIT | `LICENSE` | None |
| `marshmallow-polyfield` | 5.11 | Apache-2.0 | `LICENSE` | Published as a source distribution only; uv builds the wheel |
| `tinydb` | 4.9.0 | MIT | `LICENSE` | None |
| `xarray` | 2024.11.0 | Apache-2.0 | `LICENSE` | Some modules carry the notice of code they adapt, such as the pandas BSD-3-Clause notice in `xarray/core/resample_cftime.py` |

The compiled `grpcio` extension also contains third-party libraries, such as BoringSSL, c-ares,
RE2, Abseil, and zlib, whose sources are under `third_party/` in the `grpcio` source
distribution. Neither the wheel nor the source distribution includes a separate license file for
them; their licenses are published by those projects. Verify the bundled-library notices before
externally distributing an image with the `qm` extra. This review covers the additions from that
extra, not the full QDash dependency graph or the complete grpcio static-link tree. Every other package that the `qm` extra
uses was already a workflow dependency.

## Redistribute an Image with the qm Extra

A container image or other distribution built with the `qm` extra redistributes these packages.
BSD-3-Clause requires such a distribution to keep the copyright notice, the conditions, and the
disclaimer of `qm-qua` and `qualang-tools`, and forbids using the names of Q.M Technologies or
its contributors to endorse a derived product without permission. Apache-2.0 and MIT likewise
require their license texts, and Apache-2.0 requires `NOTICE` files, to stay with the
packages.

The workflow Dockerfiles copy the whole `.venv`, including every `.dist-info` directory, so
these files stay in an image built with the extra. A build that removes `.dist-info`
directories, or a distribution that does not ship them, must provide the license texts another
way. The full texts of the two Quantum Machines licenses, verbatim from the pinned
distributions, follow.

### qm-qua License

`qm_qua-1.5.0.dist-info/licenses/LICENSE`:

```text
Copyright 2021 Q.M Technologies Ltd.
Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### qualang-tools License

`qualang_tools-0.23.0.dist-info/licenses/LICENSE`:

```text
Copyright 2021 Q.M. Technologies Ltd.

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
