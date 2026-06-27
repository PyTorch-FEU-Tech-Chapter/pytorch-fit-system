# `src/org_ops/points` — Points · Leaderboard · Growth engine (Python port)

> **Tested Python port of `platform/org-ops/points/` (TypeScript).** Logic is identical; field
> names follow Python snake_case convention. See the original TS source for the authoritative
> specification and the Supabase migration notes.

## The two tracks (confirmed)

| Track | What it is | Module |
|---|---|---|
| **Merit leaderboard** | Cut-throat ranking. Raw weighted points, deterministic tiebreaker. No handouts. | `leaderboard.py` |
| **Growth diagnostic** | NOT a ranking. Finds the low-point bracket and recommends reachable lessons/events/hackathons by pretest→posttest gain. | `growth.py` |

## Data flow

```
point_events (ledger)
  └─► aggregate_standings()   [scoring.py]
        └─► build_leaderboard()  [leaderboard.py — uses PriorityQueue from heap.py]
              ├─► LeaderboardEntry (rank 1..N)
              └─► recommend_growth()  [growth.py — diagnostic only]
                    ◄── activity_assessments (pretest/posttest)
                    ◄── clusters + cluster_items
```

## Files

| File | Responsibility |
|---|---|
| `types.py` | Pydantic models + `PointSource` enum mirroring the TS domain contracts. |
| `heap.py` | Generic `PriorityQueue` — the heap the leaderboard ranks on. |
| `scoring.py` | Source weights (achievement/grade/project highest) + ledger → standings. |
| `leaderboard.py` | `outranks` comparator + `build_leaderboard` (merit, tiebroken). |
| `growth.py` | `gain`, `low_point_bracket`, `recommend_growth`, `difficulty_ceiling` (diagnostic). |
| `__init__.py` | Barrel — re-exports the full public API. |

## Design rules (inherited from TS)

- **Append-only is sacred.** Standings are always re-derived from the ledger; nothing here
  mutates history.
- **No PII.** Standings/leaderboard carry only `nickname` — never email/phone/raw data
  (SPECIFICATION §6). The engine falls back to `member_id`, never invents identity.
- **No clock, no network.** Timestamps are passed in as ISO strings so every function is pure
  and unit-testable. Weights are defaults; the SQL `weight` column can override per event.
- **Growth ≠ equity.** `growth.py` only *recommends*; it never edits rank or moves points.

## Tiebreaker sentinel values

The leaderboard tiebreaker uses ISO string comparisons. Null timestamps are replaced with
sentinels that sort outside the real-timestamp space:

- `first_earned_at = None` → `"￿"` (U+FFFF, sorts last — "latest possible")
- `last_active_at  = None` → `""` (empty string, sorts first — "earliest possible")

This matches the TypeScript original exactly.

## Tests

```
tests/unit/org_ops/test_heap.py
tests/unit/org_ops/test_scoring.py
tests/unit/org_ops/test_leaderboard.py
tests/unit/org_ops/test_growth.py
```

Run with: `python -m pytest tests/unit/org_ops -q`
