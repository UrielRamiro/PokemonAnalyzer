# Ingestion

The importer uses Pokemon Showdown's own Dex engine through Node.js. We do not
parse Showdown TypeScript files ourselves.

```text
Pokemon Showdown Dex engine
        |
        v
scripts/export_showdown_with_node.js
        |
        v
data/normalized/v1/*.json
        |
        v
python -m pokebrain.data update
        |
        v
data/database/pokemon.db
```

Run the full update:

```bash
.\.venv\bin\python.exe -m pokebrain.data update
```

Inspect one species:

```bash
.\.venv\bin\python.exe -m pokebrain.data inspect charizard
```

Resolve data through a specific Showdown mod:

```bash
.\.venv\bin\python.exe -m pokebrain.data resolve species charizard --mod gen3
```

Validate a team with Showdown's format validator:

```bash
.\.venv\bin\python.exe -m pokebrain.data validate-team --format gen9ou --team-file team.txt
```

Or pass the team through stdin:

```bash
Get-Content team.txt | .\.venv\bin\python.exe -m pokebrain.data validate-team --format gen9ou
```

List Showdown formats:

```bash
.\.venv\bin\python.exe -m pokebrain.data list-formats --limit 10
```

Analyze a team:

```bash
.\.venv\bin\python.exe -m pokebrain analyze-team --format gen9ou --file teams/example.txt
```

Calculate one damage interaction:

```bash
.\.venv\bin\python.exe -m pokebrain calculate-damage --generation 9 --attacker examples/great-tusk.json --defender examples/kingambit.json --move "Headlong Rush"
```

Compare two concrete sets:

```bash
.\.venv\bin\python.exe -m pokebrain matchup --generation 9 --pokemon-a examples/great-tusk.json --pokemon-b examples/kingambit.json
```

Compare two teams:

```bash
.\.venv\bin\python.exe -m pokebrain team-matchup --generation 9 --team-a examples/team-a.txt --team-b examples/team-b.txt
```

The normalized snapshot is our stable contract. SQLite is derived from that
snapshot and can be rebuilt.
