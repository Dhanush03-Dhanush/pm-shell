"""Machine-global pm-shell state at ~/.config/pm-shell/.
`secrets.json` holds shared Jira creds; `spaces.json` maps display names to
projectKey+boardId. Kept separate from per-workspace `.jira/config.json` so
`pm clone --space NAME` can write it on demand."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRETS_FILE = "secrets.json"
SPACES_FILE = "spaces.json"
_REQUIRED_SECRETS = ("baseUrl", "email", "apiToken")


class GlobalConfigError(RuntimeError):
    """Raised when the global secrets/spaces state is missing or malformed."""


def global_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "pm-shell"


def secrets_path() -> Path:
    return global_dir() / SECRETS_FILE


def spaces_path() -> Path:
    return global_dir() / SPACES_FILE


def load_secrets() -> dict[str, Any]:
    p = secrets_path()
    if not p.exists():
        raise GlobalConfigError(
            f"No credentials found at {p}.\n"
            "Create the file with baseUrl, email, apiToken — see README §Install."
        )
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise GlobalConfigError(f"{p}: invalid JSON ({exc})") from exc
    missing = [k for k in _REQUIRED_SECRETS if not data.get(k)]
    if missing:
        raise GlobalConfigError(f"{p}: missing required field(s) {', '.join(missing)}")
    return data


def load_spaces() -> dict[str, dict[str, Any]]:
    p = spaces_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise GlobalConfigError(f"{p}: invalid JSON ({exc})") from exc


def save_spaces(spaces: dict[str, dict[str, Any]]) -> None:
    p = spaces_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(spaces, indent=2, sort_keys=True) + "\n")
    tmp.replace(p)
    os.chmod(p, 0o600)


def register_space(name: str, *, project_key: str, board_id: int) -> None:
    spaces = load_spaces()
    spaces[name] = {
        "projectKey": project_key,
        "boardId": board_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    save_spaces(spaces)


def resolve_space(name: str) -> dict[str, Any]:
    # Exact match wins; case-insensitive fallback when unambiguous.
    spaces = load_spaces()
    if name in spaces:
        return spaces[name]
    matches = [n for n in spaces if n.lower() == name.lower()]
    if len(matches) == 1:
        return spaces[matches[0]]
    if len(matches) > 1:
        raise GlobalConfigError(
            f"Ambiguous space name {name!r} — multiple registered spaces match "
            f"case-insensitively: {', '.join(matches)}. Use the exact name."
        )
    available = ", ".join(sorted(spaces)) or "(none — run `pm create` first)"
    raise GlobalConfigError(f"No space named {name!r}. Registered: {available}")
