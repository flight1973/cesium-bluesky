# Settings & Units

Global preferences live under the **gear icon ⚙** in
the top-right of the viewport. Click to open a dropdown
menu. Changes apply immediately across the whole
interface.

## Units

Pick one of three systems:

| System | Speed | Altitude | Distance |
|---|---|---|---|
| **Aviation** (default) | knots | feet / FL | NM |
| **SI** | m/s | meters | km |
| **Imperial** | mph | feet | mi |

Direction is always degrees true, and wind always uses
**METAR convention** (direction wind is *from*),
regardless of the unit system.

### Where it applies

Every UI element that shows a speed respects the
current unit system:

- Aircraft panel's IAS / CAS / GS rows.
- Aircraft panel's WIND row.
- Floating aircraft labels.
- Traffic list.
- WIND tab inputs and labels.
- Scale bar (distance unit).
- (Future) wind-vector layer labels.

Internal storage is **always SI** (m/s, meters).
Conversion happens once at the display boundary, so
the sim state is consistent regardless of what's
shown.

### Persistence

The choice is saved to `localStorage` under the key
`bluesky.unitSystem`. Reopening the app restores your
preferred system.

### Changing while aircraft are selected

Flipping units immediately re-renders every visible
panel. The aircraft panel subscribes to the
`units-changed` event and re-reads its cached detail
with the new formatters.

## Documentation link

Under the **Help** section:

**📖 Documentation ↗** — opens this documentation site
in a new tab.

## Cesium Ion token

Not part of the gear menu — the Ion token lives in the
**VIEW tab** of the main toolbar (**Set Ion Token**
button). See [Viewer & 3D Globe](/docs/interface/viewer)
for details.

## Under the hood

The unit system is managed by
`frontend/src/services/units.ts`:

```typescript
import { getUnits, setUnits, onUnitsChange, msToUser,
         speedUnitLabel, windVectorToFrom, formatWind }
  from './services/units';

// Read current system:
const u = getUnits();   // 'aviation' | 'si' | 'imperial'

// Change system (notifies subscribers):
setUnits('si');

// Subscribe to changes (returns unsubscribe fn):
const unsub = onUnitsChange((newUnits) => {
  // re-render
});

// Convert a speed (m/s → user units):
msToUser(154.33, u);    // → 300 (kt) / 154.33 (m/s) / 345.2 (mph)

// Format wind (north_ms, east_ms, optional units):
formatWind(0, 15.43);   // → "270°/30 kt"
```

Components that need to react to unit changes
implement `onUnitsChange` in their
`connectedCallback` and unsubscribe in
`disconnectedCallback`.

## Future settings

Room for growth in the gear menu:

- **Theme** — light vs. dark.
- **Label density** — how aggressively to thin
  aircraft labels at global zoom.
- **Color scheme** — alternate palettes for
  accessibility.
- **Wind barb style** — arrows vs. met barbs in the
  (future) wind-vector layer.

None of these exist yet — the current menu is
deliberately minimal. The pattern for adding any of
them: put the state in a service module, subscribe
from components that care, flip the setting in the
gear menu.
