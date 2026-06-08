from abc import ABC, abstractmethod

from app.models import Attachment, AttachmentContent, AuditEvent, Experiment, Project, User


class ElnAdapter(ABC):
    @abstractmethod
    async def list_projects(self) -> list[Project]:
        raise NotImplementedError

    @abstractmethod
    async def list_experiments(self, project_id: str | None = None) -> list[Experiment]:
        raise NotImplementedError

    @abstractmethod
    async def get_experiment(self, experiment_id: str) -> Experiment:
        raise NotImplementedError

    @abstractmethod
    async def list_attachments(self, experiment_id: str | None = None) -> list[Attachment]:
        raise NotImplementedError

    @abstractmethod
    async def get_attachment(self, attachment_id: str) -> Attachment:
        raise NotImplementedError

    @abstractmethod
    async def download_attachment(self, attachment_id: str) -> AttachmentContent:
        raise NotImplementedError

    @abstractmethod
    async def list_users(self) -> list[User]:
        raise NotImplementedError

    @abstractmethod
    async def list_audit_events(self) -> list[AuditEvent]:
        raise NotImplementedError
