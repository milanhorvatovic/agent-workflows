"""Driver configuration: load and validate the JSON config file.

The config carries what the driver needs before any run exists: the
consuming project's artifact root (`artifacts_dir` — `{artifacts}` in
protocol/spec.md §8.1, which names resolving it as project configuration),
the harness command lines the driver can invoke (`backends`), and which
backend — optionally which model — each protocol role executes on
(`roles`). Validation is strict and happens entirely at load time, so a
typo fails the invocation instead of the fifth step of a run.
`driver/config.example.json` shows the full shape; `driver/README.md`
documents each field.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

# The six protocol roles (protocol/spec.md §3). The driver consumes the
# protocol's vocabulary, never defines its own.
ROLES = ("analyst", "planner", "implementer", "reviewer", "validator", "arbiter")

DEFAULT_ARTIFACTS_DIR = "."

TOP_LEVEL_KEYS = frozenset({"artifacts_dir", "backends", "roles"})
BACKEND_KEYS = frozenset({"command"})
ROLE_KEYS = frozenset({"backend", "model"})


class ConfigError(Exception):
    """The config file is missing, unreadable, or fails validation."""


@dataclass(frozen=True)
class Backend:
    """One invocable harness: the argv of a CLI that takes a prompt and returns text."""

    command: tuple[str, ...]


@dataclass(frozen=True)
class RoleRoute:
    """Where one protocol role executes: a configured backend, optionally a model.

    The model is validated and carried, not yet consumed — per-step model
    routing is scheduled for a later release, and the config format holds
    its place now so configs stay stable across driver versions.
    """

    backend: str
    model: str | None = None


@dataclass(frozen=True)
class Config:
    artifacts_dir: Path
    backends: dict[str, Backend]
    roles: dict[str, RoleRoute]

    @property
    def runs_dir(self) -> Path:
        # Runs live at {artifacts}/runs/<run-id>/ (protocol/spec.md §8.1);
        # the runs segment is the spec's, not configuration, so the driver
        # derives it rather than letting a config contradict the layout.
        return self.artifacts_dir / "runs"


def load_config(path: Path) -> Config:
    """Parse and validate the config at `path`; raise ConfigError on any defect."""
    # UnicodeDecodeError is a ValueError, not an OSError: without it here,
    # a config that is not valid UTF-8 escapes as a traceback instead of
    # the config-defect exit the CLI documents.
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(f"cannot read config: {error}") from error
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ConfigError(f"invalid JSON: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError("top level must be an object")
    unknown = sorted(set(data) - TOP_LEVEL_KEYS)
    if unknown:
        raise ConfigError(f"unknown keys: {', '.join(unknown)}")
    backends = _parse_backends(data)
    return Config(
        artifacts_dir=_parse_artifacts_dir(data, path),
        backends=backends,
        roles=_parse_roles(data, backends),
    )


def _parse_artifacts_dir(data: dict, config_path: Path) -> Path:
    value = data.get("artifacts_dir", DEFAULT_ARTIFACTS_DIR)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("artifacts_dir must be a non-empty string")
    # JSON strings may carry NUL, but no filesystem call accepts one — it
    # raises ValueError at use, far from the config that caused it.
    if "\x00" in value:
        raise ConfigError("artifacts_dir must not contain NUL")
    # JSON has no shell, so a leading ~ arrives literally; expand it rather
    # than creating a directory named `~` under the project.
    try:
        expanded = Path(value).expanduser()
    except RuntimeError as error:
        raise ConfigError(f"artifacts_dir: {error}") from error
    # A partially anchored Windows form — drive-relative "D:artifacts" or
    # root-relative "\artifacts" — is not absolute, yet joining it on a
    # Windows host discards the config-file anchor. Rejected on every
    # platform: a config is project configuration and must mean one thing
    # everywhere.
    windows_form = PureWindowsPath(expanded)
    if not expanded.is_absolute() and (windows_form.drive or windows_form.root):
        raise ConfigError("artifacts_dir must be fully absolute or fully relative")
    # A relative artifacts_dir anchors at the config file's directory, not
    # the process working directory: the config sits in the consuming
    # project, and artifacts must land there no matter where the driver is
    # invoked from. The `/` operator keeps an absolute value as-is.
    return config_path.resolve().parent / expanded


def _parse_backends(data: dict) -> dict[str, Backend]:
    value = data.get("backends")
    if not isinstance(value, dict) or not value:
        raise ConfigError("backends must be a non-empty object")
    backends: dict[str, Backend] = {}
    for name, entry in value.items():
        if not name.strip():
            raise ConfigError("backend names must be non-empty")
        if not isinstance(entry, dict):
            raise ConfigError(f"backend {name!r} must be an object")
        unknown = sorted(set(entry) - BACKEND_KEYS)
        if unknown:
            raise ConfigError(f"backend {name!r} has unknown keys: {', '.join(unknown)}")
        command = entry.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) and part.strip() for part in command)
        ):
            raise ConfigError(
                f"backend {name!r} command must be a non-empty list of non-empty strings"
            )
        # No OS can pass a NUL inside an argv element; without this check
        # the config only fails when the backend is invoked, not at load.
        if any("\x00" in part for part in command):
            raise ConfigError(f"backend {name!r} command must not contain NUL")
        backends[name] = Backend(command=tuple(command))
    return backends


def _parse_roles(data: dict, backends: dict[str, Backend]) -> dict[str, RoleRoute]:
    value = data.get("roles")
    if not isinstance(value, dict):
        raise ConfigError("roles must be an object")
    unknown = sorted(set(value) - set(ROLES))
    if unknown:
        raise ConfigError(f"unknown roles: {', '.join(unknown)}")
    # Every role must be routed: which roles a run needs depends on the risk
    # class decided at intake, so the config cannot know a subset suffices.
    missing = sorted(set(ROLES) - set(value))
    if missing:
        raise ConfigError(f"roles missing: {', '.join(missing)}")
    roles: dict[str, RoleRoute] = {}
    for role in ROLES:
        entry = value[role]
        if not isinstance(entry, dict):
            raise ConfigError(f"role {role!r} must be an object")
        unknown_keys = sorted(set(entry) - ROLE_KEYS)
        if unknown_keys:
            raise ConfigError(f"role {role!r} has unknown keys: {', '.join(unknown_keys)}")
        backend = entry.get("backend")
        if not isinstance(backend, str) or not backend.strip():
            raise ConfigError(f"role {role!r} backend must be a non-empty string")
        if backend not in backends:
            raise ConfigError(f"role {role!r} references undefined backend {backend!r}")
        model = entry.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise ConfigError(f"role {role!r} model must be a non-empty string")
        roles[role] = RoleRoute(backend=backend, model=model)
    return roles
