from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

WORKSPACE_DIRNAME = ".jira"
CONFIG_FILENAME = "config.json"


class ConfigNotFoundError(RuntimeError):
    """Raised when no .jira/config.json can be located."""


class Config(BaseModel):
    """User credentials and per-workspace state. Serialized as camelCase JSON to match the spec."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    base_url: str = Field(alias="baseUrl")
    email: str = Field(alias="email")
    api_token: str = Field(alias="apiToken")
    board_id: Optional[int] = Field(default=None, alias="boardId")
    project_key: Optional[str] = Field(default=None, alias="projectKey")
    last_pull_at: Optional[str] = Field(default=None, alias="lastPullAt")
    status_map: dict[str, str] = Field(default_factory=dict, alias="statusMap")
    next_local_id: int = Field(default=1, alias="nextLocalId")


def find_workspace_root(start: Optional[Path] = None) -> Path:
    """Walk up from `start` (or cwd) looking for a `.jira/` directory.

    Returns the directory that contains `.jira/`. If none is found, returns `start`
    (so `pm config init` from a fresh repo creates `.jira/` in the current directory).
    """
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / WORKSPACE_DIRNAME).is_dir():
            return candidate
    return cur


def workspace_dir(start: Optional[Path] = None) -> Path:
    return find_workspace_root(start) / WORKSPACE_DIRNAME


def config_path(start: Optional[Path] = None) -> Path:
    return workspace_dir(start) / CONFIG_FILENAME


def load_config(start: Optional[Path] = None) -> Config:
    path = config_path(start)
    if not path.exists():
        raise ConfigNotFoundError(
            f"No pm-shell config found. Expected {path}. Run `pm config init --from <secrets.json>`."
        )
    data = json.loads(path.read_text())
    return Config.model_validate(data)


def save_config(cfg: Config, start: Optional[Path] = None) -> Path:
    path = config_path(start)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = cfg.model_dump(by_alias=True, exclude_none=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    os.chmod(path, 0o600)
    return path


def secrets_to_config(secrets_path: Path) -> Config:
    """Load a JSON secrets file and validate it into a Config.

    Accepts both camelCase (baseUrl, apiToken, boardId) and snake_case keys.
    """
    data = json.loads(secrets_path.read_text())
    return Config.model_validate(data)
