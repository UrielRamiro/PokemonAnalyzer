# Replay Analyzer

The Replay Analyzer opens local battle artifacts from `runs/` and finds turns
where the agent likely made a poor decision.

## Review One Battle

```powershell
.\.venv\bin\python.exe -m pokebrain review-battle --battle runs\2026-07-20\battle-id
```

To create regression cases from the most suspicious turns:

```powershell
.\.venv\bin\python.exe -m pokebrain review-battle --battle runs\2026-07-20\battle-id --write-regressions
```

## Review A Benchmark Run

```powershell
.\.venv\bin\python.exe -m pokebrain review-benchmark --run benchmark-YYYYMMDDHHMMSS --top 20
```

Use `--only-losses` to focus on losses.

## What It Detects

The v1 analyzer uses deterministic rules and decision-regret from logged
alternatives. It can flag:

- missed guaranteed KO;
- attacked immunity;
- bad switch;
- failed to switch;
- unsafe setup;
- failed hazard removal;
- poor move selection.

## Current Limit

Counterfactual simulation is intentionally a stub for now. It requires a
forced-action Showdown continuation runner, which should be built after the
deterministic Replay Analyzer is stable.
