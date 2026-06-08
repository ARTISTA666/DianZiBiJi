from pydantic import BaseModel


class DashboardSummary(BaseModel):
    projects: int = 0
    experiments: int = 0
    attachments: int = 0
    audit_events: int = 0
    users: int = 0
    pending_approvals: int = 0
