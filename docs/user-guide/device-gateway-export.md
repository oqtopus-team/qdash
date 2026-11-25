# Export Device Gateway Files

Use the Python SDK to generate device topology JSON and PNG files and download Qubex
configuration for a device gateway. These operations do not start measurements or update
server configuration.

## Prerequisites

Install an SDK build with `device_topology` and `qubex` helpers, then configure a `local`
profile with an API token and project ID using the [Python reference](../reference/clients/python.md).
For a source checkout, run `pip install -e sdks/python` from the repository root.
The project needs a master calibration note and its chip data; the server also needs its
Qubex configuration directory populated. Choose physical qubit IDs from that chip.

## Export Files

1. Create a client and generate the topology. Replace the labels and qubit IDs below.
   The server uses the chip associated with the project's latest master calibration note.
   `device_id` labels the output; it does not select a chip.

   ```python
   from qdash.sdk import QDash

   qdash = QDash.from_profile("local")
   topology = qdash.device_topology.create(
       name="anemone",
       device_id="anemone",
       qubits=["0", "2", "3"],
   )
   ```

   Omit `name` or `device_id` to use the selected profile name for that label. For example,
   `QDash()` with `default_profile = "anemone"` defaults both labels to `anemone`.
   Explicit labels override these defaults independently. With `QDash.from_env()` or
   `QDash(config)`, supply both labels; there is no profile name to use.

   To reuse a gateway request file, pass `**json.load(file)` to `create()` instead.
   `exclude_couplings` and `condition` accept the request's filters. Omitted filters use
   server defaults, including freshness filtering and the largest connected component.
   Inspect `topology.qubits` and `topology.couplings` to confirm which passed the filters.

2. Save the JSON and PNG in the current directory.

   ```python
   topology.save("device_topology.json")
   plot = topology.plot()
   plot.save("device_topology.png")
   ```

   A notebook displays `plot` directly. Files are written only by `save()`; parent
   directories must exist. Existing files raise `FileExistsError`. Use `overwrite=True`
   only when you intend to replace them.

3. Download the configuration.

   ```python
   qdash.qubex.download_config("./qubex-config")
   ```

   The directory contains the server's configuration tree, including any `.git` metadata,
   plus `calib_note.json` containing the latest note's `note` field. The note replaces any
   archive file of the same name. Use `include_calibration_note=False` to download only the
   configuration archive, or `qdash.qubex.calibration_note()` to inspect the note separately.
   Configuration and note are separate reads, not a single consistent snapshot.

Confirm that the JSON has the expected device label and physical qubits, the PNG opens,
and `qubex-config` contains the configuration files and calibration note. Point the gateway
at these local paths using its configuration; the SDK does not configure or restart it.

## Repeat or Recover an Export

A missing destination directory is created if its parent exists. Existing files are kept
unless `overwrite=True`; unrelated files are never removed. Prefer a new directory when
comparing exports. Updating an existing directory is not atomic across all files, so an
operating-system failure may leave a partial update; retry into a new directory to recover.
With `overwrite=False`, a file created by another export during the download is also kept,
and the download raises `FileExistsError`. Writing into an existing directory with this
setting requires filesystem support for hard links; otherwise, export into a new directory.

A missing calibration note fails the download before writing files. Check the selected
project and calibration history, or omit the note explicitly. A topology request without
the required note or chip data currently returns `QDashApiError`; verify those prerequisites.
Malformed archives, path traversal, symlink members, and paths that differ only in case
are rejected before extraction, including on case-sensitive filesystems.

How this works: [Python SDK](../developer-guide/architecture/python-sdk.md).
