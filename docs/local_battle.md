# Local Showdown Battle Runner

This runner connects the local Pokemon Showdown simulator to the Python
PokeBrain agent.

## Run

```powershell
npm run battle -- --format gen9ou --team-a teams\team-a.txt --team-b teams\team-b.txt
```

With a reproducible seed:

```powershell
npm run battle -- --format gen9ou --team-a teams\team-a.txt --team-b teams\team-b.txt --seed 1,2,3,4
```

## Flow

```text
BattleStream
  -> sideupdate |request|
  -> normalized legal actions
  -> persistent Python agent
  -> MoveDecisionEngine
  -> Showdown choice command
```

The runner treats Showdown's request as the authority for legal actions. The
Python agent can recommend a move or switch, but the runner only sends a choice
that exists in the current `|request|`.

## Run Artifacts

Each battle writes a folder under `runs/<date>/<battle-id>/`:

- `protocol.log`: raw Showdown protocol output.
- `states.jsonl`: normalized requests seen by the runner.
- `decisions.jsonl`: legal actions, selected action, score and reasons.
- `result.json`: winner, turn count, format and seed.
- `metadata.json`: run creation metadata.

## Current Limits

- The opponent is a simple seeded random agent.
- The Python agent reconstructs BattleState from local requests, so hidden
  information is available in local simulation but should be restricted before
  public-server play.
- Team Preview is currently implemented for singles as `team 1`.
