from __future__ import annotations

from collections.abc import Iterator
from types import TracebackType
from typing import Any, Optional

import httpx

from pm_shell.config import Config

DEFAULT_ISSUE_FIELDS = (
    "summary",
    "status",
    "priority",
    "labels",
    "description",
    "assignee",
    "reporter",
    "issuetype",
    "parent",
    "subtasks",
    "created",
    "updated",
)


class JiraHTTPError(RuntimeError):
    """Raised when Jira returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, body: Any = None) -> None:
        super().__init__(f"{status_code} {message}")
        self.status_code = status_code
        self.body = body


class JiraClient:
    """Thin httpx wrapper for the Jira Cloud REST v3 API (basic auth: email + API token)."""

    def __init__(self, config: Config, *, timeout: float = 30.0) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            auth=(config.email, config.api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
        )

    def __enter__(self) -> JiraClient:
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise JiraHTTPError(response.status_code, response.reason_phrase, body)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: Optional[dict[str, Any]] = None) -> Any:
        return self._request("POST", path, json=json)

    def put(self, path: str, json: Optional[dict[str, Any]] = None) -> Any:
        return self._request("PUT", path, json=json)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    def myself(self) -> dict[str, Any]:
        return self.get("/rest/api/3/myself")

    def get_board(self, board_id: int) -> dict[str, Any]:
        return self.get(f"/rest/agile/1.0/board/{board_id}")

    def get_project_statuses(self, project_key: str) -> list[dict[str, Any]]:
        return self.get(f"/rest/api/3/project/{project_key}/statuses")

    def search_jql(
        self,
        jql: str,
        *,
        fields: Optional[tuple[str, ...]] = None,
        page_size: int = 100,
    ) -> Iterator[dict[str, Any]]:
        # /search/jql with nextPageToken — the legacy startAt /search API is deprecated.
        params: dict[str, Any] = {
            "jql": jql,
            "maxResults": page_size,
            "fields": ",".join(fields) if fields else "*all",
        }
        while True:
            page = self.get("/rest/api/3/search/jql", params=params)
            for issue in page.get("issues", []):
                yield issue
            token = page.get("nextPageToken")
            if not token or page.get("isLast"):
                return
            params["nextPageToken"] = token

    def get_issue(self, key: str, *, fields: Optional[tuple[str, ...]] = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if fields:
            params["fields"] = ",".join(fields)
        return self.get(f"/rest/api/3/issue/{key}", params=params or None)

    def get_comments(self, key: str) -> list[dict[str, Any]]:
        params = {"startAt": 0, "maxResults": 100}
        results: list[dict[str, Any]] = []
        while True:
            page = self.get(f"/rest/api/3/issue/{key}/comment", params=params)
            results.extend(page.get("comments", []))
            total = page.get("total", 0)
            params["startAt"] += len(page.get("comments", []))
            if params["startAt"] >= total or not page.get("comments"):
                return results
