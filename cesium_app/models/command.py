"""Pydantic models for generic stack commands."""
from pydantic import BaseModel


class CommandRequest(BaseModel):
    """Request body for executing a BlueSky stack command.

    Attributes:
        command: The full command string (e.g. "CRE KL204 B738 ...").
    """

    command: str


class CommandResponse(BaseModel):
    """Response for a submitted stack command.

    Attributes:
        success: Whether the command was queued successfully.
        command: The command string that was submitted.
        message: Optional status or error message.
    """

    success: bool
    command: str
    message: str = ""
