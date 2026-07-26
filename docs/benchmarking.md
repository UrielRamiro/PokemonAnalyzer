# Benchmarking

The benchmark suite runs many local Pokemon Showdown battles and stores the
results in SQLite.

For the current Champions VGC Reg M-B iteration loop, use
`docs/vgc_iteration_workflow.md`.

## Run

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark `
  --format gen9ou `
  --agent-a pokebrain-v1 `
  --agent-b max-damage `
  --battles 100 `
  --teams teams `
  --seed 12345
```

For a quick smoke test:

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark --format gen9ou --agent-a pokebrain-v1 --agent-b max-damage --battles 2 --teams teams --seed 123 --maximum-turns 2
```

With timeout and parallel workers:

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark --format gen9ou --agent-a pokebrain-v1 --agent-b max-damage --battles 100 --teams teams --seed 123 --maximum-turns 500 --timeout-seconds 120 --parallel-workers 4
```

## Agents

Current local agents:

- `pokebrain-v1`: the Python MoveDecisionEngine agent.
- `random`: picks a legal action with a seeded random generator.
- `max-damage`: uses the damage engine and picks the legal move with the
  highest expected damage.
- `previous-version`: a conservative PokeBrain baseline used as a stand-in for
  comparing against an older heuristic.
- `search-v1`: short deterministic maximin search.
- `search-v1-cache`: same search family with batched official damage
  calculations and L1/L2 cache.
- `search-v2-belief`: evaluates a small weighted set of opponent item,
  ability, move and Tera scenarios using observed opponent information.
- `search-v2-belief-shared`: belief search with a decision-wide damage cache,
  global root prefetch across scenarios and cross-scenario cache metrics.
- `search-v2-belief-layered`: iterative belief search with a single decision
  deadline, last-completed-depth fallback and layered scheduler metrics.
- `search-v3-policy`: layered belief search with a deterministic opponent
  policy model. It scores probable opponent actions, keeps rare tactical
  threats and combines expected value with worst-case value.
- `search-v3-policy-calibrated-shadow`: keeps `search-v3-policy` as the active
  decision maker while running the calibrated policy agent in parallel and
  logging what it would have done.
- `search-v4-policy-calibrated`: uses the calibrated policy profile from
  `data/policy_profiles/gen9ou.json` when that file exists, falling back to the
  default heuristic profile otherwise.

To connect a real frozen previous version, set:

```powershell
$env:POKEBRAIN_PREVIOUS_AGENT_COMMAND = "C:\path\to\old\.venv\Scripts\python.exe"
```

The process must implement the same line-delimited JSON protocol as
`pokebrain.local_agent`.

## What It Stores

Results are written to `data/database/benchmarks.db`:

- `benchmark_runs`: run metadata.
- `benchmark_pairs`: paired team/seed metadata.
- `benchmark_battles`: one row per battle.

Run metadata includes agent version, current git commit when available and a
configuration hash.

Each individual battle also writes protocol artifacts under `runs/<date>/<battle-id>/`.

## Pairing

The runner alternates team order and player side:

- Battle 1: agent A as p1, team 1 vs team 2.
- Battle 2: agent A as p1, team 2 vs team 1.
- Battle 3: agent A as p2.
- Battle 4: agent A as p2 with swapped teams.

This reduces bias from player side, Team Preview order and team strength.

`--parallel-workers` can run multiple battles at once. SQLite writes still
happen in the parent process.

## Metrics

The report includes:

- wins, losses and ties/no winner;
- adjusted win rate, where a tie counts as half a win;
- approximate 95% confidence interval;
- average and median turns;
- illegal action rate;
- agent crash rate;
- protocol error rate.
- average decision time;
- per-team adjusted win rate.
- per-lead adjusted win rate.
- per-opponent-species adjusted win rate.
- per-opponent-archetype adjusted win rate.

Self-play runs produce a warning when the adjusted win rate is far from 50%.

Current archetype labels are lightweight heuristics: `rain`, `sun`, `snow`,
`stall`, `hyper-offense`, `balance`, or `unknown`.

## Compare Runs

```powershell
.\.venv\bin\python.exe -m pokebrain compare-benchmarks --run-a benchmark-AAAA --run-b benchmark-BBBB
```

The comparison reports adjusted win-rate difference and whether the approximate
95% confidence intervals are separated.

## Review Losses

After a benchmark, inspect where the first agent is losing:

```powershell
.\.venv\bin\python.exe -m pokebrain review-benchmark --run benchmark-AAAA --only-losses --top 10 --min-battles 3
```

The replay analyzer still reports objective replay categories when it can find
them. The command also prints a benchmark loss report with the worst opponent
species, opponent archetypes, own leads, own teams, termination reasons and
example replay directories for the shortest and longest losses.

`--min-battles` filters noisy groups. Increase it for large benchmarks.

## Performance Benchmark

Use this before promoting a search agent:

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark-performance `
  --format gen9ou `
  --agents pokebrain-v1 search-v1 search-v1-cache `
  --pairs 50 `
  --teams teams `
  --seed 132 `
  --maximum-turns 100 `
  --timeout-seconds 120
```

`--pairs 50` runs 100 battles for each pair of agents. The report includes
decision p50/p95/p99, explored nodes, reached depth, damage cache metrics,
bridge batches/time, fallbacks, timeouts, illegal actions, crashes and protocol
errors.

For a smoke test:

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark-performance --format gen9ou --agents search-v1 search-v1-cache --pairs 1 --teams teams --seed 132 --maximum-turns 2 --timeout-seconds 90
```

To compare the first belief-aware agent:

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark-performance --format gen9ou --agents search-v1-cache search-v2-belief --pairs 50 --teams teams --seed 132 --maximum-turns 100 --timeout-seconds 120
```

To compare the scenario-aware damage pipeline:

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark-performance --format gen9ou --agents search-v2-belief search-v2-belief-shared --pairs 50 --teams teams --seed 132 --maximum-turns 100 --timeout-seconds 120
```

To compare the layered scheduler:

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark-performance --format gen9ou --agents search-v2-belief-shared search-v2-belief-layered --pairs 50 --teams teams --seed 132 --maximum-turns 100 --timeout-seconds 120
```

To compare the opponent policy model:

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark-performance --format gen9ou --agents search-v2-belief-layered search-v3-policy --pairs 50 --teams teams --seed 132 --maximum-turns 100 --timeout-seconds 120
```

To shadow-test a calibrated profile before promotion:

```powershell
.\.venv\bin\python.exe -m pokebrain benchmark-performance --format gen9ou --agents search-v3-policy search-v3-policy-calibrated-shadow --pairs 50 --teams teams --seed 132 --maximum-turns 100 --timeout-seconds 120
```

For belief agents, the report includes same-scenario and cross-scenario cache
hits. A rising cross-scenario hit count means damage results are being reused
across opponent hypotheses instead of recalculated per scenario.

For layered agents, the report also includes completed/attempted depth,
incomplete layers, timeout-before-batch, timeout-after-batch, batches by depth
and requests by depth.

For `search-v3-policy`, decision artifacts also include the opponent policy
distribution and the average number of weighted opponent actions expanded.

## Policy Calibration

Evaluate the current opponent policy on replay directories:

```powershell
.\.venv\bin\python.exe -m pokebrain evaluate-policy --format gen9ou --replays runs\2026-07-20\policy-smoke-3
```

Fit a profile offline and save it for `search-v4-policy-calibrated`:

```powershell
.\.venv\bin\python.exe -m pokebrain calibrate-policy --format gen9ou --replays runs\2026-07-20\policy-smoke-3 --output data\policy_profiles\gen9ou.json
```

The calibration report includes Top-1, Top-3, Top-4, assigned probability for
the real action, log loss, Brier score, entropy and out-of-search rate. The
first tuning pass keeps the architecture heuristic and adjusts softmax
temperature plus interpretable weights offline.

## Decision Cases

Fixed decision regression cases live in:

```text
benchmarks/decision_cases/
```

They are covered by the Python test suite and catch tactical regressions such
as missing a guaranteed KO or clicking into an immunity.
