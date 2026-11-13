# Qibocal Emulator Platform Provenance

The files under `platforms/qubit/` are copied without modification from the Qibocal repository.
QDash reads them only as Qibolab platform input for the `qibocal` backend; it never writes to
them. Each run copies the platform into its own artifact directory first.

| Item | Value |
| --- | --- |
| Repository | <https://github.com/qiboteam/qibocal> |
| Commit | `52450c1737ca811bc1a2facd4bc1bb24d6e53f3f` ("Declare acquisition channels for emulator platforms", 2026-07-06) |
| Source path | `platforms/qubit` |
| License | Apache License 2.0, copied from the same commit to `LICENSE` |

The Qibocal 0.2.6 release ships this platform without an acquisition channel, so the release
platform cannot run `rabi_amplitude`. The commit above adds the channel; the files are used as
published there.

| File | SHA-256 | Git blob |
| --- | --- | --- |
| `platforms/qubit/platform.py` | `56922cbe3e2a6adbad0fe83347450e72e70d4795b75a75680f5bd9818598d760` | `dc197b9a335c9a054a9fcf6e32c91f10a53da550` |
| `platforms/qubit/parameters.json` | `2bc867f724e731de28931dfc08393a62ea3386c0bdca7a8d6a6a8ad9fb89a645` | `711263cce27a9df89d765949040906823a7fae63` |
| `platforms/qubit/calibration.json` | `6fe0ab6257115217ae0bd399ee9dce17221deaac0f660f6bad0ba8bbdaa38a59` | `4f1396756a51059bc6cc6e46edcff8b23c062161` |
| `LICENSE` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` | |

`tests/qdash/workflow/engine/backend/test_qibocal_backend.py` fails when a file no longer
matches its SHA-256. To update the platform, copy the files from a new upstream commit and
update this table and the test together.
