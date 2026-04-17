"""Aviation weather decoder — plain-English translations.

Shared module that decodes the coded tokens used in
METARs, TAFs, SIGMETs, and AIRMETs into readable
narrative.  All decode functions accept a ``units``
parameter (``aviation`` / ``si`` / ``imperial``)
that controls how values are formatted:

| Unit system | Speed | Temp  | Altitude | Vis  |
|-------------|-------|-------|----------|------|
| aviation    | kt    | °C/°F | ft / FL  | SM   |
| si          | m/s   | °C    | m        | km   |
| imperial    | mph   | °F    | ft       | SM   |
"""
from __future__ import annotations

import re
from typing import Literal

UnitSystem = Literal['aviation', 'si', 'imperial']


# ─── Unit conversion helpers ─────────────────────────

def _speed(kt: float | None, units: UnitSystem) -> str:
    """Convert knots to the target unit + label."""
    if kt is None:
        return '?'
    if units == 'si':
        return f'{kt * 0.514444:.0f} m/s'
    if units == 'imperial':
        return f'{kt * 1.15078:.0f} mph'
    return f'{int(kt)} kt'


def _temp(c: float | None, units: UnitSystem) -> str:
    """Format temperature.  Aviation shows both."""
    if c is None:
        return '?'
    if units == 'si':
        return f'{c:.1f}°C'
    if units == 'imperial':
        return f'{c * 9 / 5 + 32:.0f}°F'
    # aviation: show both
    return f'{c:.1f}°C ({c * 9 / 5 + 32:.0f}°F)'


def _alt(ft: float | int | None, units: UnitSystem) -> str:
    """Format altitude from feet."""
    if ft is None:
        return '?'
    if units == 'si':
        return f'{ft * 0.3048:.0f} m'
    return f'{int(ft)} ft'


def _pressure(hpa: float | None, units: UnitSystem) -> str:
    """Format pressure in all useful units.

    Aviation shows inHg (US) + hPa (ICAO).
    SI shows hPa.
    Imperial shows inHg.
    All include atm for reference when requested.
    """
    if hpa is None:
        return '?'
    inhg = hpa * 0.02953
    atm = hpa / 1013.25
    if units == 'si':
        return f'{hpa:.1f} hPa ({atm:.4f} atm)'
    if units == 'imperial':
        return f'{inhg:.2f} inHg ({hpa:.0f} hPa)'
    # Aviation: show both primary formats
    return f'{inhg:.2f} inHg / {hpa:.1f} hPa ({atm:.4f} atm)'

# ─── Wind ────────────────────────────────────────────

_COMPASS = [
    'N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
    'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW',
]


def _compass(deg: int | float | None) -> str:
    if deg is None:
        return 'variable'
    if deg == 0:
        return 'calm'
    return _COMPASS[int((deg + 11.25) / 22.5) % 16]


def decode_wind(
    wdir: int | float | None,
    wspd: int | float | None,
    wgst: int | float | None = None,
    units: UnitSystem = 'aviation',
) -> str:
    if wspd is None or wspd == 0:
        return 'Calm'
    direction = _compass(wdir)
    base = f'{direction} at {_speed(wspd, units)}'
    if wgst and wgst > (wspd or 0):
        base += f' gusting {_speed(wgst, units)}'
    return base


# ─── Visibility ──────────────────────────────────────

def decode_visibility(vis: str | int | float | None) -> str:
    if vis is None:
        return 'not reported'
    v = str(vis).strip()
    if v.startswith('P') or v.startswith('>'):
        return f'greater than {v[1:]} SM'
    if v.startswith('M') or v.startswith('<'):
        return f'less than {v[1:]} SM'
    try:
        n = float(v)
        if n >= 6.0:
            return 'unrestricted (6+ SM)'
        return f'{v} SM'
    except ValueError:
        return f'{v} SM'


# ─── Sky condition ───────────────────────────────────

_SKY_COVER = {
    'SKC': 'sky clear',
    'CLR': 'clear below 12,000',
    'FEW': 'few',
    'SCT': 'scattered',
    'BKN': 'broken',
    'OVC': 'overcast',
    'VV': 'vertical visibility',
}


def decode_sky(
    clouds: list[dict] | None,
    ceiling_ft: int | float | str | None = None,
    units: UnitSystem = 'aviation',
) -> str:
    if not clouds:
        if ceiling_ft is not None:
            try:
                return f'ceiling {_alt(float(ceiling_ft), units)}'
            except (ValueError, TypeError):
                return str(ceiling_ft)
        return 'sky clear'
    parts = []
    for c in clouds:
        cover = c.get('cover', '')
        base = c.get('base')
        label = _SKY_COVER.get(cover, cover)
        if base is not None:
            parts.append(f'{label} at {_alt(base, units)}')
        else:
            parts.append(label)
    return '; '.join(parts) if parts else 'sky clear'


# ─── Weather phenomena ───────────────────────────────

_WX_CODES: dict[str, str] = {
    # Qualifiers
    '+': 'heavy', '-': 'light', 'VC': 'vicinity',
    # Descriptors
    'MI': 'shallow', 'PR': 'partial', 'BC': 'patches',
    'DR': 'drifting', 'BL': 'blowing', 'SH': 'showers',
    'TS': 'thunderstorm', 'FZ': 'freezing',
    # Precipitation
    'DZ': 'drizzle', 'RA': 'rain', 'SN': 'snow',
    'SG': 'snow grains', 'IC': 'ice crystals',
    'PL': 'ice pellets', 'GR': 'hail',
    'GS': 'small hail', 'UP': 'unknown precipitation',
    # Obscuration
    'BR': 'mist', 'FG': 'fog', 'FU': 'smoke',
    'VA': 'volcanic ash', 'DU': 'dust', 'SA': 'sand',
    'HZ': 'haze', 'PY': 'spray',
    # Other
    'PO': 'dust whirls', 'SQ': 'squall',
    'FC': 'funnel cloud', 'SS': 'sandstorm',
    'DS': 'duststorm',
}

_WX_RE = re.compile(
    r'([+-]|VC)?'
    r'(MI|PR|BC|DR|BL|SH|TS|FZ)?'
    r'(DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)',
)


def decode_wx_string(raw: str | None) -> str:
    """Decode a single wx-phenomena group like '+TSRA'
    into 'heavy thunderstorm rain'."""
    if not raw:
        return ''
    parts = []
    for m in _WX_RE.finditer(raw):
        tokens = []
        for g in m.groups():
            if g and g in _WX_CODES:
                tokens.append(_WX_CODES[g])
        if tokens:
            parts.append(' '.join(tokens))
    return ', '.join(parts) if parts else raw


# ─── Flight category ─────────────────────────────────

_CAT_DESC = {
    'VFR': 'VFR (ceiling > 3000 ft, vis > 5 SM)',
    'MVFR': 'Marginal VFR (ceiling 1000-3000 ft or vis 3-5 SM)',
    'IFR': 'IFR (ceiling 500-999 ft or vis 1-3 SM)',
    'LIFR': 'Low IFR (ceiling < 500 ft or vis < 1 SM)',
}


def decode_flight_category(cat: str | None) -> str:
    if not cat:
        return ''
    return _CAT_DESC.get(cat.upper(), cat)


# ─── TAF change indicators ──────────────────────────

_CHANGE_TYPE = {
    'PREVAIL': 'Base forecast',
    'FROM': 'From (permanent change)',
    'BECMG': 'Becoming (gradual transition)',
    'TEMPO': 'Temporary (fluctuations)',
    'PROB30': '30% probability',
    'PROB40': '40% probability',
}


def decode_change_type(raw: str | None) -> str:
    if not raw:
        return ''
    return _CHANGE_TYPE.get(raw.upper(), raw)


# ─── Top-level product decoders ──────────────────────

def decode_metar(
    obs: dict,
    units: UnitSystem = 'aviation',
) -> str:
    """Full plain-English decode of a normalized METAR."""
    parts = []
    parts.append(f'Station: {obs.get("icao", "?")}')
    parts.append(f'Observed: {obs.get("obs_time", "?")}')
    parts.append(
        f'Wind: {decode_wind(obs.get("wdir_deg"), obs.get("wspd_kt"), obs.get("wgst_kt"), units)}'
    )
    parts.append(f'Visibility: {decode_visibility(obs.get("visib"))}')
    parts.append(
        f'Sky: {decode_sky(obs.get("clouds"), obs.get("cover"), units)}'
    )
    temp = obs.get('temp_c')
    dewp = obs.get('dewp_c')
    if temp is not None:
        parts.append(
            f'Temperature: {_temp(temp, units)}'
            + (f', dewpoint {_temp(dewp, units)}' if dewp is not None else '')
        )
    altim = obs.get('altim_hpa')
    if altim is not None:
        parts.append(f'Altimeter: {_pressure(altim, units)}')
    cat = obs.get('flt_cat')
    if cat:
        parts.append(f'Category: {decode_flight_category(cat)}')
    return '\n'.join(parts)


def decode_taf_block(
    block: dict,
    units: UnitSystem = 'aviation',
) -> str:
    """Plain-English decode of one TAF forecast block."""
    parts = []
    change = decode_change_type(block.get('fcst_type'))
    if change:
        parts.append(change)
    vf = block.get('valid_from', '')
    vt = block.get('valid_to', '')
    if vf or vt:
        parts.append(f'Valid: {vf} → {vt}')
    parts.append(
        f'Wind: {decode_wind(block.get("wdir_deg"), block.get("wspd_kt"), block.get("wgst_kt"), units)}'
    )
    parts.append(f'Visibility: {decode_visibility(block.get("visib"))}')
    ceil = block.get('ceil_ft')
    clouds = block.get('clouds')
    parts.append(f'Sky: {decode_sky(clouds, ceil, units)}')
    cat = block.get('flt_cat')
    if cat:
        parts.append(f'Category: {decode_flight_category(cat)}')
    return '\n'.join(parts)


def decode_sigmet(
    adv: dict,
    units: UnitSystem = 'aviation',
) -> str:
    """Plain-English decode of a SIGMET / AIRMET /
    CWA / ISIGMET advisory dict."""
    parts = []
    atype = adv.get('type', '?')
    hazard = adv.get('hazard', '?')
    parts.append(f'{atype}: {hazard}')
    sev = adv.get('severity') or adv.get('qualifier')
    if sev:
        parts.append(f'Severity: {sev}')
    vf = adv.get('valid_from') or adv.get('validTimeFrom')
    vt = adv.get('valid_to') or adv.get('validTimeTo')
    if vf:
        parts.append(f'Valid: {vf} → {vt or "?"}')
    bot = adv.get('bottom_ft')
    top = adv.get('top_ft')
    if bot is not None and top is not None:
        parts.append(
            f'Altitude: {_alt(bot, units)} – {_alt(top, units)}'
        )
    raw = adv.get('raw')
    if raw:
        parts.append(f'Raw: {raw[:200]}')
    return '\n'.join(parts)
