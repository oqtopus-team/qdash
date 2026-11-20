"""Pin qdash-sdk's qdash-client dependency to the version being built.

The release pipeline publishes qdash-client and qdash-sdk from one release record with
one version, X.Y.Z for a QDash tag or X.Y.ZbN for a develop beta, so a release build
requires exactly that qdash-client. Development versions from hatch-vcs change on every
commit and the 0.0.0 fallback names no release, so those builds depend on any
qdash-client; this also keeps the workspace lock independent of the commit.
"""

from __future__ import annotations

import re
from typing import Any

from hatchling.metadata.plugin.interface import MetadataHookInterface

# The PEP 440 versions .github/scripts/client-release.mjs publishes.
RELEASE_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(b[1-9]\d*)?")


def client_requirement(version: str) -> str:
    """Return the qdash-client requirement for a qdash-sdk build of ``version``."""
    if RELEASE_VERSION.fullmatch(version) and version != "0.0.0":
        return f"qdash-client=={version}"
    return "qdash-client"


class CustomMetadataHook(MetadataHookInterface):
    """Hatchling metadata hook selected by ``[tool.hatch.metadata.hooks.custom]``."""

    def update(self, metadata: dict[str, Any]) -> None:
        metadata["dependencies"] = [client_requirement(metadata["version"])]
