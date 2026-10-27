# Adding a Chip

Create a chip record when a new device is installed. In the shared Qubex configuration layout,
QDash also writes the configuration files the device needs, so the first calibration can run
without editing YAML by hand.

## Before You Start

- You need the editor role in the project.
- Know the chip ID, the qubit count, and the topology template.
- If the control hardware is new, ask an administrator to register its boxes first (see
  [Register Control Boxes](#register-control-boxes)).

## Create the Chip

1. Open **Chip** and select **Create Chip**.
2. Enter the **Chip ID**. Letters, digits, `-`, and `_` are allowed. A **Display name** is
   optional and becomes the chip's name in the shared chip catalog.
3. Select the **Topology Template** that matches the device. The qubit count follows the
   template.
4. Choose the **Cool-down** the chip is loaded into, or leave **Not assigned**. The cool-down
   selected on the page is preselected.
5. Choose **Inherit wiring from**: the chip the new one replaces. When the cool-down is set, the
   previous chip on the same cryostat is preselected. **None (empty wiring)** starts without
   wiring rows.
6. The **Backend** follows the inherited chip's default System; pick `quel1` or `quel3` to
   override it.
7. Review **Measurement configuration**. QDash automatically creates the measurement settings
   when supported. If the environment cannot create them, the message explains that you need to
   prepare them separately before calibration. To skip automatic creation, open **Advanced
   settings** and select **Register chip information only**.
8. Select **Create Chip**.

The dialog then shows the Systems created, where the wiring came from, the repository outcome
(**Published**, **Recorded locally**, **Publish failed**, or **Nothing to publish**), the
warnings, and the files written. A warning means the chip was created but something was skipped,
such as an empty wiring when there was no chip to inherit from; fix the warning before the first
run. **Publish failed** means the files and the database record exist but the remote rejected the
push; the **Config** page lists them as unpublished changes.

## What Gets Written

In the shared layout, creating a chip adds:

| Item | Content |
| --- | --- |
| Chip entry | Name, qubit count, and topology in the shared chip catalog. |
| Systems | One entry per backend the inherited chip used, named `<chip ID>` for the default and `<chip ID>-<backend>` for others. |
| Wiring | The inherited chip's wiring rows, grouped by System. |
| Parameters | A parameter directory per System: physics values copied from the inherited chip's database records, hardware defaults per backend. |
| Calibration note | An empty note per System. |

In the legacy layout (one directory per chip) QDash only creates the database record. Copy the
configuration directory yourself; the **Boxes** tab and **Add System** are read-only there.

## Add a System on Another Backend

A chip can be driven by more than one backend when its multiplexers are split between them, for
example QuEL-1 on some and QuEL-3 on the rest. Each partition is a System.

1. Open the chip. The **Systems** card under the filters lists each System with its backend, MUX
   numbers, boxes, and whether its parameter directory and calibration note exist. The card is
   hidden for a legacy-layout chip with a single System.
2. Select **Add System**.
3. Choose the **Backend**. Only backends without a System on this chip are offered.
4. Enter the **MUX numbers** to move, separated by commas.
5. Optionally enter **Backend settings** as a JSON object for the new `system.yaml` entry.
6. Select **Add**.

The dialog shows the files written, the repository outcome, and any warnings.

QDash refuses the change when a MUX is not wired, when the backend already has a System on the
chip, when a wiring row names a box that is not registered, or when the generated files do not
load. Nothing is written in that case.

A run always drives one System. A pipeline whose targets fall into two Systems is reported as a
problem when you validate it; run the two groups as separate pipelines.

## Register Control Boxes

Administrators keep the catalog of control boxes shared by every chip.

1. Open **Admin** and select the **Boxes** tab.
2. Select **Register box** and enter the **Box ID**, **Name**, and **Type** (a Qubex box type
   such as `quel1-a` or `quel3`).
3. For QuEL-1 and QuBE types, also enter the **Address** and **Adapter**.
4. Add **Options** one per line when the box needs them.
5. Select **Save**.

A box can be edited later with **Edit** in its row; the box ID cannot change. Wiring that references a box QDash does not know
is reported when you add a System or validate a pipeline.
