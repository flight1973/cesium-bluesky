"""Formation / platoon manager.

Manages groups of aircraft flying in coordinated
formation with reduced separation, shared intent,
and cooperative maneuvering.

A formation has:
  - A leader (sets speed/heading/altitude)
  - Followers with assigned slots (geometry offset)
  - Formation-specific PZ (tighter than standard)
  - Join/leave protocol

Formation geometries:
  - TRAIL: single file behind leader
  - ECHELON_R/L: diagonal line right/left
  - DIAMOND: diamond pattern
  - OFFSET: wake-surfing optimal offset
  - LINE_ABREAST: side by side
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class FormationType(str, Enum):
    TRAIL = 'trail'
    ECHELON_R = 'echelon_r'
    ECHELON_L = 'echelon_l'
    DIAMOND = 'diamond'
    OFFSET = 'offset'
    LINE_ABREAST = 'line_abreast'


@dataclass
class FormationSlot:
    """Position offset from leader in the formation frame.

    forward_m: positive = behind leader (trail distance)
    right_m: positive = right of leader
    up_m: positive = above leader
    """
    forward_m: float = 0.0
    right_m: float = 0.0
    up_m: float = 0.0


@dataclass
class Formation:
    id: str
    formation_type: FormationType
    leader: str
    followers: list[str] = field(default_factory=list)
    slots: dict[str, FormationSlot] = field(default_factory=dict)
    separation_nm: float = 1.0
    lateral_offset_m: float = 0.0
    vertical_offset_ft: float = 0.0
    created_at: float = field(default_factory=time.time)

    @property
    def members(self) -> list[str]:
        return [self.leader] + self.followers

    @property
    def size(self) -> int:
        return 1 + len(self.followers)


# Default slot generators per formation type

def _trail_slots(
    n_followers: int, spacing_m: float = 1852.0,
) -> list[FormationSlot]:
    """Single file, each follower spacing_m behind the previous."""
    return [
        FormationSlot(forward_m=spacing_m * (i + 1))
        for i in range(n_followers)
    ]


def _echelon_slots(
    n_followers: int, spacing_m: float = 1852.0,
    right: bool = True,
) -> list[FormationSlot]:
    """Diagonal line at 45° behind and to the side."""
    sign = 1.0 if right else -1.0
    return [
        FormationSlot(
            forward_m=spacing_m * (i + 1) * 0.707,
            right_m=sign * spacing_m * (i + 1) * 0.707,
        )
        for i in range(n_followers)
    ]


def _diamond_slots(spacing_m: float = 1852.0) -> list[FormationSlot]:
    """Diamond: 2=right, 3=left, 4=tail."""
    return [
        FormationSlot(forward_m=spacing_m * 0.5, right_m=spacing_m * 0.5),
        FormationSlot(forward_m=spacing_m * 0.5, right_m=-spacing_m * 0.5),
        FormationSlot(forward_m=spacing_m),
    ]


def _offset_slots(
    n_followers: int,
    longitudinal_m: float = 3704.0,
    lateral_m: float = 40.0,
    vertical_m: float = 0.0,
) -> list[FormationSlot]:
    """Wake-surfing offset: behind + slightly lateral.

    Default: 2 NM behind, ~1 wingspan lateral offset,
    same altitude. The lateral offset places the follower
    in the upwash region of the leader's wake vortex.
    """
    return [
        FormationSlot(
            forward_m=longitudinal_m * (i + 1),
            right_m=lateral_m * (1 if i % 2 == 0 else -1),
            up_m=vertical_m,
        )
        for i in range(n_followers)
    ]


def _line_abreast_slots(
    n_followers: int, spacing_m: float = 1852.0,
) -> list[FormationSlot]:
    """Side by side, no longitudinal offset."""
    slots = []
    for i in range(n_followers):
        idx = i + 1
        sign = 1.0 if idx % 2 == 1 else -1.0
        rank = (idx + 1) // 2
        slots.append(FormationSlot(right_m=sign * spacing_m * rank))
    return slots


def generate_slots(
    formation_type: FormationType,
    n_followers: int,
    spacing_m: float = 1852.0,
) -> list[FormationSlot]:
    """Generate default slots for a formation type."""
    if formation_type == FormationType.TRAIL:
        return _trail_slots(n_followers, spacing_m)
    elif formation_type == FormationType.ECHELON_R:
        return _echelon_slots(n_followers, spacing_m, right=True)
    elif formation_type == FormationType.ECHELON_L:
        return _echelon_slots(n_followers, spacing_m, right=False)
    elif formation_type == FormationType.DIAMOND:
        return _diamond_slots(spacing_m)[:n_followers]
    elif formation_type == FormationType.OFFSET:
        return _offset_slots(n_followers, spacing_m)
    elif formation_type == FormationType.LINE_ABREAST:
        return _line_abreast_slots(n_followers, spacing_m)
    return _trail_slots(n_followers, spacing_m)


class FormationManager:
    """Manages all active formations."""

    def __init__(self):
        self._formations: dict[str, Formation] = {}

    def create(
        self,
        formation_id: str,
        leader: str,
        followers: list[str],
        formation_type: FormationType = FormationType.TRAIL,
        spacing_nm: float = 1.0,
    ) -> Formation:
        spacing_m = spacing_nm * 1852.0
        slots = generate_slots(
            formation_type, len(followers), spacing_m,
        )
        slot_map = {}
        for i, follower in enumerate(followers):
            if i < len(slots):
                slot_map[follower] = slots[i]

        f = Formation(
            id=formation_id,
            formation_type=formation_type,
            leader=leader,
            followers=list(followers),
            slots=slot_map,
            separation_nm=spacing_nm,
        )
        self._formations[formation_id] = f
        logger.info(
            "Formation '%s' created: leader=%s, %d followers, type=%s",
            formation_id, leader, len(followers), formation_type.value,
        )
        return f

    def dissolve(self, formation_id: str) -> bool:
        if formation_id in self._formations:
            del self._formations[formation_id]
            return True
        return False

    def join(self, formation_id: str, callsign: str) -> bool:
        f = self._formations.get(formation_id)
        if not f:
            return False
        if callsign in f.followers or callsign == f.leader:
            return False
        f.followers.append(callsign)
        # Assign next slot
        slots = generate_slots(
            f.formation_type, len(f.followers),
            f.separation_nm * 1852.0,
        )
        f.slots[callsign] = slots[-1]
        return True

    def leave(self, formation_id: str, callsign: str) -> bool:
        f = self._formations.get(formation_id)
        if not f or callsign not in f.followers:
            return False
        f.followers.remove(callsign)
        f.slots.pop(callsign, None)
        return True

    def get(self, formation_id: str) -> Formation | None:
        return self._formations.get(formation_id)

    def find_by_member(self, callsign: str) -> Formation | None:
        for f in self._formations.values():
            if callsign == f.leader or callsign in f.followers:
                return f
        return None

    def list_all(self) -> list[dict]:
        return [
            {
                'id': f.id,
                'type': f.formation_type.value,
                'leader': f.leader,
                'followers': f.followers,
                'size': f.size,
                'separation_nm': f.separation_nm,
            }
            for f in self._formations.values()
        ]

    @property
    def formations(self) -> dict[str, Formation]:
        return self._formations
