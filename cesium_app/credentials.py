"""Credential vault — encrypted server-side storage.

Every integration that requires auth (FAA SWIM,
EUROCONTROL, FlightAware, Cesium Ion, LLM
providers, voice providers, etc.) reads
credentials through :func:`get_secret`.  If a
credential isn't configured, the function returns
``None`` and the caller degrades gracefully — per
the modular-data-feeds directive.

Storage: per-value Fernet encryption in the
``credential`` table of the SQLite cache.  The
master key comes from (in priority order):

1. ``CESIUM_VAULT_KEY`` env var (base64 32-byte).
2. Auto-generated on first use and printed to
   stderr with instructions to persist it.

The master key is NEVER stored in the DB.
"""
from __future__ import annotations

import base64
import logging
import os
import time

from cryptography.fernet import Fernet, InvalidToken

from cesium_app.store.db import connect

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Lazy master-key init."""
    global _fernet
    if _fernet is not None:
        return _fernet
    key = os.environ.get("CESIUM_VAULT_KEY")
    if key:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        return _fernet
    # Auto-generate — print to stderr so the user
    # can persist it.  This is a dev convenience;
    # production should set the env var.
    new_key = Fernet.generate_key()
    logger.warning(
        "No CESIUM_VAULT_KEY set — auto-generated. "
        "Set this env var to persist credentials "
        "across restarts:\n"
        "  export CESIUM_VAULT_KEY=%s",
        new_key.decode(),
    )
    _fernet = Fernet(new_key)
    return _fernet


def _ensure_table() -> None:
    """Idempotent credential table creation."""
    conn = connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS credential (
                integration  TEXT NOT NULL,
                field        TEXT NOT NULL,
                encrypted    BLOB NOT NULL,
                created_at   REAL NOT NULL,
                updated_at   REAL NOT NULL,
                PRIMARY KEY (integration, field)
            );
            CREATE TABLE IF NOT EXISTS credential_meta (
                integration  TEXT PRIMARY KEY,
                label        TEXT NOT NULL,
                description  TEXT,
                last_tested  REAL,
                last_ok      INTEGER
            );
        """)
    finally:
        conn.close()


# ─── Public API ──────────────────────────────────────

def get_secret(
    integration: str,
    field: str,
) -> str | None:
    """Read a decrypted credential value.

    Returns ``None`` if not configured — callers
    MUST degrade gracefully per the modular-feeds
    directive.
    """
    _ensure_table()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT encrypted FROM credential "
            "WHERE integration = ? AND field = ?",
            (integration, field),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        return _get_fernet().decrypt(row[0]).decode("utf-8")
    except (InvalidToken, Exception) as exc:
        logger.warning(
            "Failed to decrypt %s.%s: %s",
            integration, field, exc,
        )
        return None


def set_secret(
    integration: str,
    field: str,
    value: str,
) -> None:
    """Encrypt + store a credential value."""
    _ensure_table()
    encrypted = _get_fernet().encrypt(
        value.encode("utf-8"),
    )
    now = time.time()
    conn = connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO credential("
                "integration, field, encrypted,"
                " created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(integration, field) DO UPDATE SET"
                " encrypted = excluded.encrypted,"
                " updated_at = excluded.updated_at",
                (integration, field, encrypted, now, now),
            )
    finally:
        conn.close()


def delete_secret(integration: str, field: str) -> bool:
    """Remove a credential. Returns True if it existed."""
    _ensure_table()
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                "DELETE FROM credential "
                "WHERE integration = ? AND field = ?",
                (integration, field),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def has_secret(integration: str, field: str) -> bool:
    """Check if a credential exists without decrypting."""
    _ensure_table()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM credential "
            "WHERE integration = ? AND field = ?",
            (integration, field),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def list_integrations() -> list[dict]:
    """All configured integrations with their fields
    (masked) + test status.  Never returns plaintext."""
    _ensure_table()
    conn = connect()
    try:
        creds = conn.execute(
            "SELECT integration, field, updated_at "
            "FROM credential ORDER BY integration, field"
        ).fetchall()
        metas = conn.execute(
            "SELECT * FROM credential_meta "
            "ORDER BY integration"
        ).fetchall()
    finally:
        conn.close()
    meta_map = {r["integration"]: dict(r) for r in metas}
    by_int: dict[str, list[dict]] = {}
    for r in creds:
        integ = r["integration"]
        # Decrypt just to get the last 4 chars for masking.
        val = get_secret(integ, r["field"])
        masked = (
            "●" * 8 + val[-4:]
            if val and len(val) > 4
            else "●" * 4
        )
        by_int.setdefault(integ, []).append({
            "field": r["field"],
            "has_value": True,
            "masked_tail": masked,
            "updated_at": r["updated_at"],
        })
    result = []
    # Include all known integrations from meta +
    # any that have credentials but no meta.
    all_ints = set(meta_map.keys()) | set(by_int.keys())
    for integ in sorted(all_ints):
        meta = meta_map.get(integ, {})
        result.append({
            "integration": integ,
            "label": meta.get("label", integ),
            "description": meta.get("description"),
            "last_tested": meta.get("last_tested"),
            "last_ok": meta.get("last_ok"),
            "fields": by_int.get(integ, []),
        })
    return result


def register_integration(
    integration: str,
    *,
    label: str,
    description: str | None = None,
) -> None:
    """Declare an integration so the UI shows it even
    before any credentials are entered."""
    _ensure_table()
    conn = connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO credential_meta("
                "integration, label, description) "
                "VALUES(?, ?, ?) "
                "ON CONFLICT(integration) DO UPDATE SET"
                " label = excluded.label,"
                " description = excluded.description",
                (integration, label, description),
            )
    finally:
        conn.close()


def record_test(
    integration: str,
    ok: bool,
) -> None:
    """Stamp the last connection-test result."""
    _ensure_table()
    now = time.time()
    conn = connect()
    try:
        with conn:
            conn.execute(
                "UPDATE credential_meta SET "
                "last_tested = ?, last_ok = ? "
                "WHERE integration = ?",
                (now, 1 if ok else 0, integration),
            )
    finally:
        conn.close()


# ─── Known integrations registry ────────────────────
# Each adapter calls register_integration() on import
# so the credentials panel shows the full list even
# before any secrets are entered.  This block
# registers the integrations we know about today;
# future adapters add their own.

def register_known_integrations() -> None:
    """Register all currently-known integrations.

    Each integration's description documents expected
    field names + auth type so the credentials UI can
    render the right input form:

    - **token**: single API key / access token
    - **userpass**: username + password
    - **oauth**: client_id + client_secret
    - **broker**: username + password + broker_url
    """
    _known = [
        ("cesium_ion", "Cesium Ion",
         "Auth: token. "
         "Fields: token. "
         "Get one at cesium.com/ion/tokens."),
        ("faa_swim", "FAA SWIM",
         "Auth: broker (Solace JMS). "
         "Fields: username, password, broker_url."),
        ("eurocontrol_ddr2", "EUROCONTROL DDR2",
         "Auth: userpass. "
         "Fields: username, password "
         "(OneSky portal login)."),
        ("navigraph", "Navigraph",
         "Auth: oauth. "
         "Fields: client_id, client_secret."),
        ("flightaware", "FlightAware AeroAPI",
         "Auth: token. "
         "Fields: token "
         "(from flightaware.com/aeroapi)."),
        ("opensky", "OpenSky Network",
         "Auth: userpass (optional). "
         "Fields: username, password."),
        ("openaip", "OpenAIP",
         "Auth: token (optional). "
         "Fields: token."),
        ("openweathermap", "OpenWeatherMap",
         "Auth: token. "
         "Fields: token "
         "(free at openweathermap.org/appid)."),
        ("anthropic", "Anthropic (Claude)",
         "Auth: token. "
         "Fields: token "
         "(from console.anthropic.com)."),
        ("openai", "OpenAI",
         "Auth: token. "
         "Fields: token "
         "(from platform.openai.com)."),
        ("elevenlabs", "ElevenLabs",
         "Auth: token. "
         "Fields: token "
         "(from elevenlabs.io)."),
    ]
    for integ, label, desc in _known:
        register_integration(
            integ, label=label, description=desc,
        )
