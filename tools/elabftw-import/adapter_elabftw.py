import asyncio
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

import httpx

from app.adapters.base import ElnAdapter
from app.models import Attachment, AttachmentContent, AuditEvent, Experiment, ExperimentStatus, Project, User


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


class ElabftwAdapter(ElnAdapter):
    """HTTP API adapter for real eLabFTW instances."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        scope: str = "team",
        page_size: int = 100,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.scope = scope
        self.page_size = page_size
        self._attachment_cache: dict[str, Attachment] = {}
        self._current_team: Project | None = None
        self.client = client or httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": api_key, "Accept": "application/json"},
            timeout=timeout_seconds,
        )

    async def list_projects(self) -> list[Project]:
        try:
            teams = await self._request_json("GET", "/api/v2/teams")
            if isinstance(teams, list) and teams:
                projects = [self._normalize_team(item) for item in teams]
                self._current_team = projects[0]
                return projects
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {401, 403, 404}:
                raise

        current = await self._request_json("GET", "/api/v2/teams/current")
        project = self._normalize_team(current)
        self._current_team = project
        return [project]

    async def list_experiments(self, project_id: str | None = None) -> list[Experiment]:
        await self._ensure_current_team()
        params: dict[str, Any] = {"extended": "1", "scope": self.scope}
        experiments = [self._normalize_experiment(item) for item in await self._paged("GET", "/api/v2/experiments", params)]
        if project_id is None:
            return experiments
        return [experiment for experiment in experiments if experiment.project_id == project_id]

    async def get_experiment(self, experiment_id: str) -> Experiment:
        try:
            item = await self._request_json("GET", f"/api/v2/experiments/{experiment_id}", params={"extended": "1"})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise KeyError(experiment_id) from exc
            raise
        await self._ensure_current_team()
        return self._normalize_experiment(item)

    async def list_attachments(self, experiment_id: str | None = None) -> list[Attachment]:
        if experiment_id is None:
            attachments: list[Attachment] = []
            for experiment in await self.list_experiments():
                attachments.extend(await self.list_attachments(experiment_id=experiment.id))
            return attachments

        items = await self._paged("GET", f"/api/v2/experiments/{experiment_id}/uploads", {})
        attachments = [self._normalize_upload(item, experiment_id) for item in items]
        self._attachment_cache.update({attachment.id: attachment for attachment in attachments})
        return attachments

    async def get_attachment(self, attachment_id: str) -> Attachment:
        if attachment_id in self._attachment_cache:
            return self._attachment_cache[attachment_id]

        for attachment in await self.list_attachments():
            if attachment.id == attachment_id:
                return attachment
        raise KeyError(attachment_id)

    async def download_attachment(self, attachment_id: str) -> AttachmentContent:
        attachment = await self.get_attachment(attachment_id)
        path = f"/api/v2/experiments/{attachment.experiment_id}/uploads/{attachment.id}"
        try:
            content = await self._request_bytes("GET", path, params={"format": "binary"})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise KeyError(attachment_id) from exc
            raise
        return AttachmentContent(attachment=attachment, content=content)

    async def list_users(self) -> list[User]:
        users = await self._paged("GET", "/api/v2/users", {})
        return [self._normalize_user(item) for item in users]

    async def list_audit_events(self) -> list[AuditEvent]:
        events: list[AuditEvent] = []
        for experiment in await self.list_experiments():
            try:
                items = await self._paged("GET", f"/api/v2/experiments/{experiment.id}/revisions", {})
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {403, 404}:
                    continue
                raise
            for item in items:
                event_id = item.get("id") or item.get("revision_id") or f"{experiment.id}:{item.get('created_at', 'revision')}"
                events.append(
                    AuditEvent(
                        id=str(event_id),
                        actor_id=str(item.get("userid") or item.get("user_id") or item.get("fullname") or "unknown"),
                        action="revision",
                        target_type="experiment",
                        target_id=experiment.id,
                        source_url=self._api_url(f"/api/v2/experiments/{experiment.id}/revisions/{event_id}"),
                        created_at=self._parse_datetime(item.get("created_at") or item.get("modified_at")),
                    )
                )
        return events

    async def _paged(self, method: str, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        offset = 0
        while True:
            page_params = {**params, "limit": self.page_size, "offset": offset}
            payload = await self._request_json(method, path, params=page_params)
            items = self._as_items(payload)
            results.extend(items)
            if len(items) < self.page_size:
                return results
            offset += self.page_size

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        last_error: httpx.HTTPError | None = None
        for attempt in range(3):
            try:
                response = await self.client.request(method, path, **kwargs)
                response.raise_for_status()
                if not response.content:
                    return {}
                return response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise
                last_error = exc
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_error = exc
            await asyncio.sleep(0.25 * (2**attempt))
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected eLabFTW request failure")

    async def _request_bytes(self, method: str, path: str, **kwargs: Any) -> bytes:
        last_error: httpx.HTTPError | None = None
        for attempt in range(3):
            try:
                response = await self.client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.content
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise
                last_error = exc
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_error = exc
            await asyncio.sleep(0.25 * (2**attempt))
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected eLabFTW download failure")

    async def _ensure_current_team(self) -> None:
        if self._current_team is not None:
            return
        try:
            current = await self._request_json("GET", "/api/v2/teams/current")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403, 404}:
                return
            raise
        if isinstance(current, dict) and current:
            self._current_team = self._normalize_team(current)

    @staticmethod
    def _as_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "data", "experiments", "uploads", "users"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def _normalize_team(self, item: dict[str, Any]) -> Project:
        team_id = str(item.get("id") or item.get("team_id") or "current")
        project = Project(
            id=team_id,
            name=str(item.get("title") or item.get("name") or item.get("team_name") or "Current eLabFTW team"),
            owner_id=str(item.get("userid") or item.get("owner") or item.get("owner_id") or "elabftw"),
            source_url=self._api_url(f"/api/v2/teams/{team_id}") if team_id != "current" else self._api_url("/api/v2/teams/current"),
        )
        return project

    def _normalize_experiment(self, item: dict[str, Any]) -> Experiment:
        experiment_id = str(item.get("id"))
        team_id = item.get("team") or item.get("team_id")
        if not team_id and self._current_team is not None:
            team_id = self._current_team.id
        return Experiment(
            id=experiment_id,
            project_id=str(team_id or "current"),
            title=str(item.get("title") or item.get("name") or f"Experiment {item.get('id')}"),
            body_text=self._html_to_text(str(item.get("body") or item.get("content") or "")),
            source_url=self._api_url(f"/api/v2/experiments/{experiment_id}"),
            status=self._normalize_status(item),
            updated_at=self._parse_datetime(item.get("modified_at") or item.get("updated_at") or item.get("created_at")),
        )

    def _normalize_upload(self, item: dict[str, Any], experiment_id: str) -> Attachment:
        attachment_id = item.get("id") or item.get("long_name") or item.get("real_name")
        return Attachment(
            id=str(attachment_id),
            experiment_id=experiment_id,
            filename=str(item.get("real_name") or item.get("filename") or item.get("name") or f"attachment-{attachment_id}"),
            content_type=str(item.get("type") or item.get("content_type") or "application/octet-stream"),
            text_hint=item.get("comment") or item.get("description"),
            source_url=self._api_url(f"/api/v2/experiments/{experiment_id}/uploads/{attachment_id}"),
        )

    def _normalize_user(self, item: dict[str, Any]) -> User:
        user_id = item.get("id") or item.get("userid")
        return User(
            id=str(user_id),
            display_name=str(item.get("fullname") or item.get("email") or item.get("username") or f"User {user_id}"),
            role=str(item.get("role") or item.get("usergroup") or "user"),
            source_url=self._api_url(f"/api/v2/users/{user_id}"),
        )

    @staticmethod
    def _normalize_status(item: dict[str, Any]) -> ExperimentStatus:
        raw = str(item.get("status") or item.get("status_title") or item.get("state") or "").lower()
        if "draft" in raw:
            return ExperimentStatus.draft
        if "archiv" in raw or raw in {"2", "archived"}:
            return ExperimentStatus.archived
        return ExperimentStatus.active

    @staticmethod
    def _html_to_text(value: str) -> str:
        if "<" not in value or ">" not in value:
            return re.sub(r"\s+", " ", value).strip()
        parser = _HtmlTextExtractor()
        parser.feed(value)
        return parser.text()

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if not value:
            return datetime.now(timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)

    def _api_url(self, path: str) -> str:
        return f"{self.base_url}{path}"
