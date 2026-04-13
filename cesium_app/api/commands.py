"""REST endpoints for generic stack commands."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from cesium_app.models.command import CommandRequest
from cesium_app.models.command import CommandResponse
from cesium_app.sim.bridge import SimBridge

router = APIRouter(prefix="/api", tags=["commands"])


class CommandArgs(BaseModel):
    """Request body for /api/cmd/{name} endpoints.

    Attributes:
        args: Space-separated args, or a list of args.
    """

    args: str | list | None = None


def _bridge(request: Request) -> SimBridge:
    """Extract the SimBridge from app state."""
    return request.app.state.bridge


def _resolve_command(name: str) -> str | None:
    """Resolve a command name or alias to its canonical name.

    Args:
        name: Command name or alias (case-insensitive).

    Returns:
        Canonical command name, or None if unknown.
    """
    from bluesky.stack.cmdparser import Command

    upper = name.upper()
    if upper in Command.cmddict:
        # Exact match — could be canonical or alias.
        return upper
    # Fall back to scanning aliases.
    for cname, cmd in Command.cmddict.items():
        if cmd.aliases and upper in {
            a.upper() for a in cmd.aliases
        }:
            return upper
    return None


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


@router.post("/cmd/{name}", response_model=CommandResponse)
async def execute_named_command(
    request: Request,
    name: str,
    body: CommandArgs | None = None,
) -> CommandResponse:
    """Execute any BlueSky command by name or alias.

    Auto-generated endpoint that accepts any of the 316
    command names and aliases in BlueSky.  Args are
    appended to the command string and sent to the stack.

    Examples::

        POST /api/cmd/OP                  -> "OP"
        POST /api/cmd/Q                   -> "Q" (QUIT alias)
        POST /api/cmd/HDG + {"args":
          "KL204 270"}                    -> "HDG KL204 270"
        POST /api/cmd/BOX + {"args":
          ["A","51","3","53","6"]}        -> "BOX A 51 3 53 6"

    Args:
        name: Command name or alias.
        body: Optional args (string or list).

    Returns:
        CommandResponse with the submitted command string.

    Raises:
        HTTPException: 404 if name is not a known command.
    """
    canonical = _resolve_command(name)
    if canonical is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown command: {name}",
        )

    # Build the full command string.
    args = body.args if body else None
    if args is None or args == "":
        cmd = canonical
    elif isinstance(args, list):
        cmd = canonical + " " + " ".join(
            str(a) for a in args
        )
    else:
        cmd = f"{canonical} {args}"

    _bridge(request).stack_command(cmd)
    return CommandResponse(
        success=True,
        command=cmd,
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
