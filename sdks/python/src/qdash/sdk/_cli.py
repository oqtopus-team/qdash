"""The ``qdash`` command of qdash-sdk: ``qdash config init`` writes a starting ``config.toml``.

``python -m qdash.sdk`` runs the same command. It makes no network request and never asks for an API token:
the file holds an empty ``api_token`` to fill in, or, with ``--api-token-env``, names the
environment variable that holds the token. The ``qdash`` command of the TypeScript SDK writes
the same file for the same options.
"""

from __future__ import annotations

import argparse
import errno
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from qdash.sdk._config import RESERVED_PROFILE_NAMES, default_config_path

if TYPE_CHECKING:
    from collections.abc import Sequence

PROG = "qdash"
DEFAULT_INIT_PROFILE = "local"
DEFAULT_INIT_BASE_URL = "http://localhost:5714/api"
DEFAULT_INIT_TOKEN_ENV = "QDASH_LOCAL_TOKEN"  # noqa: S105 - a variable name, not a token

EXIT_FAILURE = 1
EXIT_USAGE = 2

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TOML_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f"}
_TOML_ESCAPES["\r"] = "\\r"


class _UsageError(Exception):
    """An invalid option value; the message never carries the value itself."""


def toml_string(value: str) -> str:
    """``value`` as a TOML basic string."""
    out = []
    for char in value:
        if char in _TOML_ESCAPES:
            out.append(_TOML_ESCAPES[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def toml_key(name: str) -> str:
    """``name`` as a TOML key: bare when it may be, else quoted (a dot never nests tables)."""
    return name if _BARE_KEY.fullmatch(name) else toml_string(name)


def render_config(
    profile: str,
    base_url: str,
    api_token_env: str | None = None,
    project_id: str | None = None,
) -> str:
    """The text of a new config file holding one profile, which is the default profile.

    Every profile key appears: the common ones set, the rest commented out with their use.
    Without ``api_token_env`` the profile holds an empty ``api_token`` to fill in; with it,
    the profile reads the token from that environment variable instead.
    """
    lines = [
        "# QDash SDK configuration, created by `qdash config init`.",
        "# Each [<name>] table is a profile; default_profile selects one when none is given.",
        f"default_profile = {toml_string(profile)}",
        "",
        f"[{toml_key(profile)}]",
        f"base_url = {toml_string(base_url)}",
        "",
        "# Authentication: set one of api_token, api_token_env, or username with password_env.",
    ]
    if api_token_env is None:
        lines += [
            "# Paste the token from Settings > API Token in QDash; empty means no token.",
            'api_token = ""',
            "# To keep the token out of this file, delete api_token and name the environment",
            "# variable that holds it:",
            f"# api_token_env = {toml_string(DEFAULT_INIT_TOKEN_ENV)}",
            "# To sign in with a password instead, leave api_token empty and set:",
        ]
    else:
        lines += [
            "# The API token is read from this environment variable, not stored in this file.",
            f"api_token_env = {toml_string(api_token_env)}",
            "# To store the token here instead, delete api_token_env and paste the token from",
            "# Settings > API Token in QDash:",
            '# api_token = "<token>"',
            "# To sign in with a password instead, delete api_token_env and set:",
        ]
    lines += [
        '# username = "<username>"',
        '# password_env = "QDASH_PASSWORD"  # environment variable holding the password',
        "",
        "# Project sent as X-Project-Id; running tasks from the Python SDK needs it. Without it",
        "# the server uses your default project.",
    ]
    if project_id is None:
        lines.append('# project_id = "<project-id>"')
    else:
        lines.append(f"project_id = {toml_string(project_id)}")
    lines += [
        "",
        "timeout_sec = 30  # seconds per request",
        "verify_tls = true",
        "read_attempts = 3  # tries of a read (GET) on a transient failure; writes are sent once",
        "# Proxy for API requests. In the TypeScript SDK, proxy and verify_tls = false need a",
        "# custom fetch (session option).",
        '# proxy = "http://proxy.example:8080"',
        "# User-Agent header for API requests:",
        '# user_agent = "my-tool/1.0"',
        "# Cloudflare Access service token, for a server behind Cloudflare Access:",
        '# cf_access_client_id = "<client-id>.access"',
        '# cf_access_client_secret = "<client-secret>"',
    ]
    return "\n".join(lines) + "\n"


def _text(option: str, value: str) -> str:
    if not value:
        raise _UsageError(f"{option} must not be empty.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _UsageError(f"{option} must be valid Unicode text.") from None
    return value


def _validate(args: argparse.Namespace) -> None:
    profile = _text("--profile", args.profile)
    if profile in RESERVED_PROFILE_NAMES:
        reserved = ", ".join(sorted(RESERVED_PROFILE_NAMES))
        raise _UsageError(f"--profile must not be a reserved name ({reserved}).")
    _text("--base-url", args.base_url)
    if args.project_id is not None:
        _text("--project-id", args.project_id)
    # A token pasted here by mistake would be written and printed, so only names pass.
    if args.api_token_env is not None and not _ENV_NAME.fullmatch(args.api_token_env):
        raise _UsageError(
            "--api-token-env must be an environment variable name "
            "(letters, digits and underscores, not starting with a digit)."
        )
    if args.path is not None:
        path = _text("--path", args.path)
        if Path(path).suffix.lower() != ".toml":
            raise _UsageError("--path must name a .toml file.")


def write_new_file(path: Path, text: str) -> None:
    """Create ``path`` with ``text``; fail when anything, a symlink included, is there.

    ``O_EXCL`` makes the existence check and the creation one step, and does not follow a
    symlink at ``path``. On POSIX the new file is readable by its owner only.
    """
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except FileExistsError:
        # A file where a parent directory belongs; the config file itself does not exist.
        raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR)) from None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _init(args: argparse.Namespace) -> int:
    _validate(args)
    path = Path(args.path).expanduser() if args.path is not None else default_config_path()
    text = render_config(args.profile, args.base_url, args.api_token_env, args.project_id)
    try:
        write_new_file(path, text)
    except FileExistsError:
        _error(f"{path} already exists; it was left unchanged. Edit it, or pass --path.")
        return EXIT_FAILURE
    except OSError as exc:
        _error(f"cannot create {path}: {exc.strerror or type(exc).__name__}")
        return EXIT_FAILURE

    print(f"Created {path} with profile {toml_key(args.profile)} as default_profile.")
    if path.absolute() != default_config_path().absolute():
        print("This is not the default config path; pass this path when loading the profile.")
    if args.api_token_env is None:
        print(
            f"Next: paste your QDash API token (Settings > API Token) into api_token in {path}, "
            "or switch to api_token_env as the file describes."
        )
    else:
        print(
            f"Next: set {args.api_token_env} to your QDash API token, "
            f"for example: export {args.api_token_env}=<token>"
        )
    return 0


def _error(message: str) -> None:
    print(f"{PROG}: error: {message}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, description="QDash SDK utilities (qdash-sdk).")
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    config = commands.add_parser("config", help="manage the QDash SDK config file")
    actions = config.add_subparsers(dest="action", required=True, metavar="<action>")
    init = actions.add_parser(
        "init",
        help="create a new config.toml with one profile",
        description=(
            "Create a new config.toml holding one profile, which becomes default_profile. "
            "An existing file is never changed. No token is asked for: fill in api_token in "
            "the new file, or pass --api-token-env to read the token from an environment "
            "variable. Every other profile key is listed, commented out."
        ),
    )
    init.add_argument(
        "--profile", default=DEFAULT_INIT_PROFILE, help=f"default: {DEFAULT_INIT_PROFILE}"
    )
    init.add_argument(
        "--base-url", default=DEFAULT_INIT_BASE_URL, help=f"default: {DEFAULT_INIT_BASE_URL}"
    )
    init.add_argument("--project-id", help="sent as X-Project-Id (default: none, commented out)")
    init.add_argument(
        "--api-token-env",
        metavar="NAME",
        help="read the API token from this environment variable instead of storing it "
        "(default: an empty api_token to fill in)",
    )
    init.add_argument("--path", help="file to create (default: $XDG_CONFIG_HOME/qdash/config.toml)")
    init.set_defaults(handler=_init)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``qdash``; return the exit status (0 success, 1 failure, 2 usage error)."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        status: int = args.handler(args)
    except _UsageError as exc:
        _error(str(exc))
        return EXIT_USAGE
    return status


def entrypoint() -> None:
    """The console script: exit with :func:`main`'s status."""
    sys.exit(main())
