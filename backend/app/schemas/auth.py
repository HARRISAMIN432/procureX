from uuid import UUID

from pydantic import BaseModel

from app.schemas.identity import OrganizationWorkspaceRead


class BrowserSessionRead(BaseModel):
    authenticated: bool
    display_name: str
    organization_id: UUID | None
    csrf_token: str
    workspaces: list[OrganizationWorkspaceRead]


class WorkspaceSelection(BaseModel):
    organization_id: UUID
