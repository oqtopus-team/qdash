# Chip Provisioning

Creating a chip in the shared Qubex configuration layout writes the configuration tree next to the
database records. This page describes the services involved, the files they produce, and the
checks that keep a broken tree from being written.

## Flow

```text
POST /chips
  └─ ChipProvisioningService.create_chip        api/services/chip/provisioner.py
       ├─ plan            system.yaml / wiring.yaml / chip.yaml entries, SystemFiles per System
       ├─ validate_staged qubex ConfigLoader on a staged copy  api/services/chip/system_files.py
       ├─ TreeWriter      write shared entries and System directories (rollback on failure)
       ├─ ChipInitializer database records                    api/services/chip/initializer.py
       ├─ CooldownService optional cool-down assignment
       └─ publish_changes ConfigRepository.upsert_shared / publish_owned
```

`ChipInitializer` still owns the database side. The provisioner wraps it: files are written first
so a database failure rolls the files back, and a publish failure leaves both in place with
`publish.status == "failed"` in the response.

## Endpoints

| Method and path | Operation ID | Role | Purpose |
| --- | --- | --- | --- |
| `POST /chips` | `createChip` | editor | Create the record and, in the shared layout, the configuration files |
| `GET /chips/{chip_id}/systems` | `listChipSystems` | member | Systems, backends, MUXes, boxes, and which files exist |
| `POST /chips/{chip_id}/systems` | `addChipSystem` | editor | Move MUXes to a new `<chip_id>-<backend>` System |
| `GET /config/boxes` | `listConfigBoxes` | admin | `box.yaml` entries and the box types qubex accepts |
| `POST /config/boxes` | `upsertConfigBox` | admin | Register or update one box |

`CreateChipRequest` fields: `chip_id`, `size`, `topology_id`, `display_name`, `provision_config`
(`null` means "when the layout is shared"), `backend`, `inherit_wiring_from`, `cooldown_id`.
`ChipResponse.provisioning` carries `ChipProvisioningResult`: `provisioned`, `layout`,
`system_ids`, `inherited_from`, `files`, `publish`, `warnings`. Warnings cover a missing source chip,
template defaults written for a chip without values, a cool-down that could not be assigned, and
a repository without `qubex-config.json` (the manifest the tree is expected to carry).

Validation failures are HTTP 400 with the reason in `detail`. The legacy layout returns 400 for
an explicit `provision_config: true` and for `addChipSystem` and `upsertConfigBox`.

## Planning a Chip

`ChipProvisioningService.plan` builds a `ProvisionPlan`:

1. The chip entry (`chip_entry`) carries `name`, `n_qubits`, and `topology` with `type`,
   `mux_size` from the topology template, and `qdash_topology_id`.
2. The source chip is `inherit_wiring_from`, else the previous chip on the cool-down's cryostat
   (`previous_chip_on_cryostat`), else nothing. With a source, each of its Systems becomes
   `<new chip>` or `<new chip>-<backend>` with the same settings and wiring rows. Without one, a
   single System with empty wiring is created and a warning is returned.
3. `request.backend` overrides the inherited backend of the default System.
4. Each System gets `SystemFiles`: params rendered from the templates and the chip values
   (`render_params_files`), and an empty calibration note.

`validate_staged` copies the shared files plus the staged entries into a temporary tree, checks
them against the layout schemas (`qubex_config_schema.validate_tree`), and loads every new System
with qubex's `ConfigLoader`. The error message names the file and location a schema rejected, or
the System and the file qubex rejected.

## Parameter Templates

`config/domain/qubex-params/` holds one YAML file per parameter with `meta` (`description`,
`unit`, `default`, `scope`) and an empty `data` section. `qubex_params_templates.py` reads them:

| Directory | Files | Written to |
| --- | --- | --- |
| `common/` | physics values such as `qubit_frequency.yaml`, `t1.yaml`, and `measurement_defaults.yaml` | every System of the chip |
| `quel1/` | `capture_delay.yaml` (ndelay), `capture_delay_word.yaml`, `control_fsc.yaml`, `control_vatt.yaml`, `readout_fsc.yaml`, `readout_vatt.yaml` | QuEL-1 Systems only |
| `quel3/` | `capture_delay.yaml` (ns) | QuEL-3 Systems only |

`scope` decides the labels: `qubit` writes one key per qubit label, `mux` one per MUX the System
wires, `coupling` one per coupling. A file without `scope` is copied verbatim. A value from the
database is used only when its unit matches the template; otherwise the template default applies,
and a label with neither is omitted.

The workflow's `_QubexParamsUpdater` (`workflow/engine/params_updater.py`) uses the same split at
run time: a common file updated for one System is projected to the other Systems of the chip,
while backend files stay in the session's System directory.

Every file named in `workflow.params_updater.parameter_file_map` has a template, so a chip created
here holds every file a task can write; `test_every_mapped_params_file_has_a_template` enforces
this. Adding a task output is described in
[Add a calibration task](../workflow/engine-architecture.md#add-a-calibration-task).

## Adding a System

`ChipSystemsService.add_system` (`api/services/chip/systems.py`) refuses the request before
writing when the layout is legacy, the chip has no explicit `system.yaml` entry, the backend
already has a System on the chip, a MUX is not wired, the supplied wiring rows do not cover the
requested MUXes, or a referenced box is missing from `box.yaml`. It then builds the new
`system.yaml` entry and the moved wiring rows, renders the System's params from the chip's
database values, copies the master calibration note, validates with qubex, writes, and publishes.
Existing System directories are not touched.

## Preflight Checks

`configuration_problems` in `api/services/calibration_pipeline_preflight.py` adds configuration
problems to pipeline validation: targets spanning Systems (`targets`), targets on unwired MUXes
(`targets`), boxes missing from `box.yaml` (`chip_id`), shared files that violate their layout
schema (`chip_id`), and an unreadable tree (`chip_id`).
`default_system_catalog` returns `None` when the tree has nothing for the chip, so the fake
backend and CI are unaffected. The catalog factory is a constructor argument of
`CalibrationPipelineService`, so tests inject a catalog built on a temporary tree.

## Tests

| Behavior | Test |
| --- | --- |
| Template classification and rendering | `tests/qdash/common/config/test_qubex_params_templates.py` |
| Provisioning, inheritance, rollback, legacy layout | `tests/qdash/api/services/chip/test_provisioner.py` |
| Listing and adding Systems | `tests/qdash/api/services/chip/test_systems.py` |
| Box catalog | `tests/qdash/api/services/test_config_boxes_service.py` |
| Preflight configuration problems | `tests/qdash/api/services/test_calibration_pipeline_preflight.py` |
| Run-time projection to other Systems | `tests/qdash/workflow/engine/test_params_projection.py` |

`tests/qdash/api/services/chip/_trees.py` builds a shared-layout tree with a QuEL-1 and a QuEL-3
System; the provisioning tests load the generated files with qubex, so qubex must be installed.
