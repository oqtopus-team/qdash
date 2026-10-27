# qubex-config Layout

A qubex-config tree declares its layout version in `<root>/qubex-config.json`. QDash reads that
file to resolve paths and validates each configuration file against the JSON Schema for its
version. The schemas are published under
`https://oqtopus-team.github.io/qdash/schemas/qubex-config/` and kept in
`config/domain/qubex-config-schemas/` in the repository.

## Versions

| Version | qubex | Shape | QDash name |
| --- | --- | --- | --- |
| `1.0` | before 1.5 | `<chip_id>/{config,params,calibration}`; shared files duplicated per chip | `legacy` |
| `2.0` | 1.5 and later | `config/*.yaml` shared by every chip; `params/<system_id>/`, `calibration/<system_id>/` per System | `shared` |

Every qubex-config repository carries the manifest. A tree that has not been updated yet is read
as `2.0` when `config/chip.yaml` exists at the root and `1.0` otherwise; the Config page then shows
a **no manifest** warning, and chip provisioning adds a warning asking for the file. This
inference is transitional and goes away once every tree declares its version.
`QUBEX_LAYOUT=shared` or `QUBEX_LAYOUT=legacy` overrides the manifest.

## Manifest

`qubex-config.json` at the root, validated by `manifest.schema.json`:

| Field | Required | Value |
| --- | --- | --- |
| `$schema` | no | `https://oqtopus-team.github.io/qdash/schemas/qubex-config/manifest.schema.json` |
| `layout_version` | yes | `"1.0"` or `"2.0"` |
| `description` | no | Free text |
| `converted_from` | no | `"1.0"` when a script converted the tree |
| `converted_at` | no | RFC 3339 timestamp of the conversion |
| `generated_by` | no | Tool that wrote the file, such as `scripts/convert_layout.py` |

```json
{
  "$schema": "https://oqtopus-team.github.io/qdash/schemas/qubex-config/manifest.schema.json",
  "layout_version": "2.0",
  "converted_from": "1.0",
  "converted_at": "2026-10-27T09:00:00+00:00",
  "generated_by": "scripts/convert_layout.py"
}
```

## Schema Copy in the Tree

A tree keeps a copy of its version's schemas in `<root>/schemas/`, next to the manifest, so the
repository states which schemas it is managed with and can validate itself without QDash
(`scripts/validate_layout.py` in qubex-config). `convert_layout.py` copies `schemas/` into the
converted tree and starts each generated `config/*.yaml` with
`# yaml-language-server: $schema=../schemas/<name>` for editor support. QDash validates with the
schemas it ships; `GET /config-repository/status` reports `schemas_status` as `match`, `differs`
or `absent`, and the Config page shows a warning badge on `differs`.

## Files and Schemas

| File (`2.0` path) | File (`1.0` path) | Schema | Keyed by |
| --- | --- | --- | --- |
| `config/chip.yaml` | `<chip_id>/config/chip.yaml` | `chip.schema.json` | chip ID |
| `config/system.yaml` | `<chip_id>/config/system.yaml` | `system.v2.schema.json` / `system.v1.schema.json` | system ID (`1.0` also accepts one top-level entry) |
| `config/wiring.yaml` | `<chip_id>/config/wiring.yaml` | `wiring.schema.json` | system ID (`2.0`) or chip ID (`1.0`) |
| `config/box.yaml` | `<chip_id>/config/box.yaml` | `box.schema.json` | box ID |
| `config/skew.yaml` | `<chip_id>/config/skew.yaml` | `skew.schema.json` | `box_setting.<box ID>` |
| `params/<system_id>/<parameter>.yaml` | `<chip_id>/params/<parameter>.yaml` | `params-file.schema.json` | `meta` + `data` label |
| `params/<system_id>/measurement_defaults.yaml` | `<chip_id>/params/measurement_defaults.yaml` | none (settings file) | |
| `calibration/<system_id>/calib_note.json` | `<chip_id>/calibration/calib_note.json` | none (written by qubex) | |
| `config/cable_delay.yaml`, `config/external_devices.yaml` | same under `<chip_id>/` | none | |

Every schema is JSON Schema draft 2020-12. Unknown keys are allowed inside entries so qubex can
add fields without a QDash release; the schemas reject missing required keys, wrong types and
malformed IDs. Consistency between files (boxes referenced by wiring exist, one System per MUX) is
checked by `SystemCatalog`, not by the schemas.

## Where QDash validates

| Place | What |
| --- | --- |
| `POST /config/files/validate` with `path` | The file being edited on the **Config** page |
| `POST /calibration-pipelines/validate` | Shared files of the target chip, reported under `chip_id` |
| `POST /chips`, `POST /chips/{id}/systems` | Generated shared entries and params before qubex loads them |
| `GET /config-repository/status` | `layout_version`, `manifest_present` and `schemas_status` for the Config page badges |

[Chips and Systems](../developer-guide/architecture/qubex-systems.md) explains the resolution
rules; [Qubex Backend Setup](../user-guide/setup/qubex-backend.md) shows both trees.
