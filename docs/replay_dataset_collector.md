# Replay Dataset Collector

The replay dataset collector stores public Pokemon Showdown replay JSON before
any parsing or policy training happens.

## Flow

```text
Showdown replay search API
-> replay ids
-> raw JSON download
-> quality validation
-> raw storage
-> SQLite catalog
-> separate extraction job
-> policy examples
```

The collector is intentionally independent from the parser. Raw replays can be
reprocessed later when the parser, `BeliefState` or policy features change.

## Commands

Collect public Gen 9 OU replays:

```powershell
.\.venv\bin\python.exe -m pokebrain.replays collect --format gen9ou --limit 1000
```

Equivalent top-level command:

```powershell
.\.venv\bin\python.exe -m pokebrain collect-replays --format gen9ou --limit 1000
```

Parse pending catalog entries into policy examples:

```powershell
.\.venv\bin\python.exe -m pokebrain.replays parse --format gen9ou --status pending
```

Equivalent top-level command:

```powershell
.\.venv\bin\python.exe -m pokebrain parse-replays --format gen9ou --status pending
```

## Storage

Raw JSON is stored under:

```text
data/replays/raw/<format>/<year>/<month>/<replay-id>.json
```

The SQLite catalog is stored at:

```text
data/database/replays.db
```

The catalog records replay id, format, upload time, optional rating, player
names, raw path, content hash, download status, parse status, parser version and
failure reason.

## Notes

Public Showdown replay JSON does not include every battle played on the ladder.
It only includes uploaded public replays. The official API returns up to 51
search results, and pagination advances by using the `uploadtime` of the last
processed item from the first 50 results.

Replay parsing into battle states is deliberately a separate job. Public replay
logs are parsed into typed events, public-state snapshots and partial policy
examples. They become full `PolicyTrainingExample` records only when legal
actions can be generated from trusted team/request data.
