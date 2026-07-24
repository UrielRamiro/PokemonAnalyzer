# Multi-Turn Search

`search-v1` adds a short maximin search above the existing one-turn heuristic.
`search-v1-cache` keeps the same official Showdown damage source, but batches
and caches repeated damage calculations during the search.

## Run Regression Cases

```powershell
.\.venv\bin\python.exe -m pokebrain test-regressions --agent search-v1 --cases benchmarks\decision_cases
.\.venv\bin\python.exe -m pokebrain test-regressions --agent search-v1-cache --cases benchmarks\decision_cases
```

## Benchmark Against The One-Turn Agent

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark --format gen9ou --agent-a search-v1 --agent-b pokebrain-v1 --battles 20 --teams teams --seed 130 --maximum-turns 100 --timeout-seconds 120
.\.venv\bin\python.exe -m pokebrain benchmark --format gen9ou --agent-a search-v1-cache --agent-b search-v1 --battles 20 --teams teams --seed 130 --maximum-turns 100 --timeout-seconds 120
```

## Architecture

- `HeuristicStateEvaluator`: scores final states by material, HP, active matchup,
  hazards, status and speed.
- `DeterministicBattleTransitionModel`: resolves simplified Singles turns.
- `ActionPruner`: limits the branching factor using the one-turn evaluator.
- `MaximinSearch`: assumes the opponent chooses the worst response.
- `SearchDamagePrefetcher`: collects official damage calculations for pruned
  move branches before expansion.
- `SearchDecisionEngine`: wraps search and falls back to `MoveDecisionEngine`.

## Damage Optimization

The cached search path uses two cache layers:

- L1: per-decision `SearchDamageCache`, cleared when a search starts.
- L2: shared in-memory `LruDamageCache`, reused across decisions in the same
  agent process.

`ShowdownDamageEngine.calculate_many()` sends missing calculations to
`scripts/showdown_bridge.js` in one batch. The cache key includes generation,
format, attacker, defender, move, field and engine version data. Defender
current HP is intentionally excluded from the raw damage key so the same damage
rolls can be reused while KO assessment changes separately.

## Current Limits

- Singles only.
- Default depth is 2 plies.
- Uses average damage.
- Assumes moves hit.
- Ignores critical hits, secondary effects and many special mechanics.
- Search is opt-in because damage calculations are still relatively expensive.
- `search-v1-cache` is still opt-in and should be benchmarked before promotion.

The current implementation passes the fixed decision/regression cases, but it
should replace the one-turn agent only after paired benchmarks show better or
equal win rate without unacceptable decision latency.

Current smoke performance indicates the next optimization target is the
one-turn `ActionPruner`: it can spend the decision budget on individual damage
calculations before the cached search prefetch expands nodes.
