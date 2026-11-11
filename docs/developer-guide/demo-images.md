# QDash Demo Images

The QDash Demo (sample data) codespace runs prebuilt `qdash-demo-*` images from the GitHub
Container Registry (GHCR) and never builds an image during startup. This page covers how those
images are named, built, and published, and the one-time setup a maintainer does before the
first codespace can pull them. The user procedure is
[QDash Demo in Codespaces](../user-guide/setup/codespaces-demo.md).

## Images and Tags

`.devcontainer/codespaces-demo/images.sh` is the single list of demo images. The
`QDash Demo Images` workflow reads it to build the images, and `demo.sh` reads it to pull them,
so both always agree on the references.

| Image | Dockerfile | Compose services |
| --- | --- | --- |
| `qdash-demo-api` | `src/qdash/api/Dockerfile` | `api`, `calibration-migration`, `agent-runtime-auth` |
| `qdash-demo-deployment-service` | `src/qdash/workflow/Dockerfile.deployment` | `deployment-service` |
| `qdash-demo-workflow` | `src/qdash/workflow/Dockerfile` | `user-flow-worker` |
| `qdash-demo-ui` | `ui/Dockerfile`, with `NEXT_PUBLIC_ENV=codespaces-demo` | `ui` |

A tag is `src-` followed by a hash of the image's build inputs at the checked-out commit: the
Git object IDs of its Dockerfile, the dependency files it copies (`pyproject.toml`, `uv.lock`,
and the package manifests, or the whole `ui/` directory), `.dockerignore`, and its build
arguments. A tag never moves to different inputs, and every commit with the same inputs uses the
same image. This matters because `compose.yaml` mounts the checkout's Python source into the
containers: the image supplies only the dependencies, so it must match the checkout's lock file,
and a floating `latest` tag would drift from it.

`ghcr.io/astral-sh/uv:latest` and the base images in the Dockerfiles are not part of the hash.
The publish job skips a tag that already exists, so the first image published for a tag stays.
To force new images, change `tag_scheme` in `images.sh`.

`.devcontainer/codespaces-demo/compose.yaml` removes the `build` section of every service the demo
starts with `build: !reset null` (Compose 2.24 or later) and sets its `image` from the
`QDASH_DEMO_*_IMAGE` variables that `demo.sh` writes to `.env`. `demo.sh start` pulls the
missing images, then runs `docker compose up --no-build`. When a pull fails, it stops and
prints the next steps instead of building. `demo.sh build-local` is a separate command that
builds the same tags in the codespace. The default development container and `compose.yaml`
alone still build every image.

## Workflow Triggers

`.github/workflows/demo-images.yml` builds every image for `linux/amd64`, the Codespaces
platform, with the Buildx GitHub Actions cache.

| Event | Result | Token permissions |
| --- | --- | --- |
| Pull request to `develop` or `main` that changes an image input | Builds the images without pushing | `contents: read` |
| Push to `develop`, `main`, or trusted bootstrap branch `t3/github-pages-demo-hosting` | Publishes any image whose tag does not exist yet | `contents: read`, `packages: write` |
| **Run workflow** with **publish** selected | Publishes the images of the selected branch | `contents: read`, `packages: write` |
| **Run workflow** without **publish** | Builds without pushing | `contents: read` |

The explicit bootstrap branch permits publication before merge; remove that branch from the
push trigger after the workflow is merged. Pull requests remain read-only builds.

GitHub offers **Run workflow** only after the workflow file is on the default branch. Published
images carry the `org.opencontainers.image.source` label of the repository, which links each
package to it, and `org.opencontainers.image.revision` with the commit they were built from.

## Publish for the First Time

The workflow publishes with the `GITHUB_TOKEN` and needs no personal access token. GHCR creates
each package as private on its first publication, and a codespace pulls without signing in, so a
maintainer makes the packages public once:

1. An organization owner checks **Organization settings → Packages → Package creation** and
   allows public packages. Without it, a package cannot be made public.
2. Publish the images by pushing the trusted bootstrap branch `t3/github-pages-demo-hosting`, or, once it is on the default branch,
   open **Actions → QDash Demo Images → Run workflow**, select the branch, select **publish**,
   and run it.
3. For each of `qdash-demo-api`, `qdash-demo-deployment-service`, `qdash-demo-workflow`, and
   `qdash-demo-ui`: open the organization's **Packages** tab, open the package, select
   **Package settings**, and under **Danger Zone** select **Change visibility → Public**.
   A public package cannot be made private again.
4. If a package already existed before this workflow first published it, add the repository
   under **Package settings → Manage Actions access** with the **Write** role. Otherwise the
   publish job cannot push to it.
5. Check that the images pull without credentials:

   ```bash
   demo_docker_config="$(mktemp -d)"
   for ref in $(bash .devcontainer/codespaces-demo/images.sh refs); do
     DOCKER_CONFIG="$demo_docker_config" docker pull "$ref" || break
   done
   rm -rf "$demo_docker_config"
   ```

GitHub documents the visibility settings in
[Configuring a package's access control and visibility](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility).
After this setup, every push to `develop` or `main` publishes new tags as public packages without
further steps.

## Launch Button

The README **Launch QDash Demo** button links to
`https://codespaces.new/<owner>/<repository>/tree/<branch>?devcontainer_path=.devcontainer%2Fcodespaces-demo%2Fdevcontainer.json`,
which selects the branch and the demo configuration. GitHub's **Code → Codespaces → ... → Share
a deep link** dialog, with **Configuration file** selected, generates the same link; see
[Facilitating quick creation and resumption of codespaces](https://docs.github.com/en/codespaces/setting-up-your-project-for-codespaces/setting-up-your-repository/facilitating-quick-creation-and-resumption-of-codespaces).
A codespace on any branch pulls the published tags of its build inputs, so it starts without a
build as long as those inputs match a commit that was published.

## Change and Test

When a Dockerfile starts copying another file, add the file to its entry in `images.sh` and to
the `pull_request` paths of the workflow. Then run:

```bash
uv run pytest tests/infra/test_codespaces_demo.py
```

The tests render the demo Compose files and check that no started service, setup jobs
included, needs a build, that the tags change only with their inputs, that the workflow
permissions and path filters match `images.sh`, and that `demo.sh` pulls but never builds.
