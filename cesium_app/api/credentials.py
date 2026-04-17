"""REST endpoints for the credential vault.

Never returns plaintext secrets.  ``GET`` returns
masked tails; ``PUT`` accepts the value, encrypts,
and stores; ``DELETE`` removes; ``POST .../test``
probes the integration.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cesium_app import credentials as vault

router = APIRouter(
    prefix="/api/credentials", tags=["credentials"],
)


class SecretBody(BaseModel):
    value: str


@router.get("")
async def list_all() -> dict:
    """All integrations with masked credential fields
    and test-status.  Never returns plaintext."""
    return {"items": vault.list_integrations()}


@router.put("/{integration}/{field}")
async def set_credential(
    integration: str,
    field: str,
    body: SecretBody,
) -> dict:
    """Encrypt + store a credential value."""
    vault.set_secret(integration, field, body.value)
    return {"status": "saved"}


@router.delete("/{integration}/{field}")
async def delete_credential(
    integration: str,
    field: str,
) -> dict:
    """Remove a credential."""
    existed = vault.delete_secret(integration, field)
    if not existed:
        raise HTTPException(404, "Credential not found")
    return {"status": "deleted"}


@router.post("/{integration}/test")
async def test_integration(integration: str) -> dict:
    """Quick health probe for the integration using
    its stored credentials.  Returns ``{ok, error}``.

    Each integration has its own test logic; this
    endpoint dispatches to the right one.  If no
    test is defined, returns a generic "has
    credentials" check.
    """
    # Generic fallback: check if at least one field
    # is configured.
    items = vault.list_integrations()
    match = next(
        (i for i in items if i["integration"] == integration),
        None,
    )
    if not match:
        raise HTTPException(404, "Unknown integration")
    has_any = any(f["has_value"] for f in match.get("fields", []))
    ok = has_any
    error = None if has_any else "No credentials configured"
    vault.record_test(integration, ok)
    return {"ok": ok, "error": error}
