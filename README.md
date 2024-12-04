<div align="center">

<h1> 📊 QDash </h1>

</div>

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

QDash is a web application that provides a user-friendly interface to manage and monitor the execution of calibration workflows.

## Key Features

- **⚡ Workflows**: Centrally manage and track the progress of calibration workflows, from creation to completion.

- **📊 Observations**: Access and analyze the observational data utilized in calibration processes, ensuring transparency and insight.

- **⚙️ Settings**: Configure calibration parameters and adjust workflow settings to meet specific requirements seamlessly.

## Quick Start

### Initial Setup

Run the following commands to create the necessary directories and environment files.

```bash
chmod +x scripts/create_directory.sh scripts/create_env.sh scripts/init.sh
scripts/init.sh
```

### Start the Development Environment

```bash
docker compose up -d
```

### Initialize the Database

```bash
 docker compose -f compose.dev.yaml up -d
```

```bash
docker exec -it qdash-devcontainer /bin/bash -c "python init/setup.py init-all"
```

You can now access the application at [http://localhost:5714](http://localhost:5714).

### Delete the Database

```bash
docker exec -it qdash-devcontainer /bin/bash -c "python init/setup.py teardown-all"
```

## Documentation

- [Documentation Home](https://qdash.readthedocs.io/en/stable/)

## CITATION

You can use the DOI to cite QDash in your research.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.14277283.svg)](https://doi.org/10.5281/zenodo.14277283)

Citation information is also available in the [CITATION](https://github.com/oqtopus-team/qdash/blob/main/CITATION.cff) file.

## Contact

You can contact us by creating an issue in this repository,
or you can contact us by email:

- [oqtopus-team[at]googlegroups.com](mailto:oqtopus-team[at]googlegroups.com)

## LICENSE

OQTOPUS Cloud is released under the [Apache License 2.0](https://github.com/oqtopus-team/qdash/blob/main/LICENSE).
