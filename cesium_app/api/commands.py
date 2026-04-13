"""REST endpoints for generic stack commands."""
from fastapi import APIRouter, Request

from cesium_app.models.command import CommandRequest
from cesium_app.models.command import CommandResponse
from cesium_app.sim.bridge import SimBridge

router = APIRouter(prefix="/api", tags=["commands"])


def _bridge(request: Request) -> SimBridge:
    """Extract the SimBridge from app state."""
    return request.app.state.bridge


@router.post("/commands", response_model=CommandResponse)
async def execute_command(
    request: Request,
    body: CommandRequest,
) -> CommandResponse:
    """Execute any BlueSky stack command.

    The command is queued and processed on the next sim cycle.
    Echo text is delivered asynchronously via WebSocket.
    """
    _bridge(request).stack_command(body.command)
    return CommandResponse(
        success=True,
        command=body.command,
        message="Command queued",
    )


@router.get("/commands/list")
async def list_commands(request: Request) -> list[dict]:
    """List all available BlueSky stack commands.

    Returns command names, briefs, help text, and aliases.
    Used by the frontend for command autocomplete.
    """
    from bluesky.stack.cmdparser import Command

    result = []
    for name, cmd in sorted(Command.cmddict.items()):
        aliases = cmd.aliases
        result.append({
            "name": name,
            "brief": cmd.brief,
            "help": cmd.help or "",
            "aliases": list(aliases) if aliases else [],
        })
    return result
