# Architecture

The project is built around `pokebrain.data.DataManager`.

The AI, team builder and battle engine should not read SQLite directly. They
ask the `DataManager` repositories for species, moves, items and abilities.

```text
Pokemon Showdown Dex engine
        |
        v
Normalized snapshot
        |
        v
SQLite database
        |
        v
DataManager repositories
        |
        v
AI / team builder / battle reasoning
```

For generation-specific mechanics and legality, the project delegates to
Pokemon Showdown:

- `ShowdownEngine.resolve("gen3", "species", "charizard")`
- `ShowdownEngine.validate_team("gen9ou", team_text)`
- `ShowdownEngine.list_formats()`

The first competitive layer is `TeamAnalyzer`. It parses a Showdown-exported
team, validates it through Showdown, then produces structured facts such as
hazards, removal, recovery, speed, priority, defensive type profile and basic
roles.

The first matchup building block is `DamageEngine`. It delegates damage formulae
to `@smogon/calc` through the Showdown bridge, then returns stable Python
dataclasses with damage rolls, percentages and basic KO classification.

`MatchupAnalyzer v1` orchestrates the Damage Engine for two concrete sets. It
evaluates each offensive move in both directions, compares base priority and
calculated Speed, estimates KO ranges and returns a transparent verdict with
explicit limitations.

`TeamMatchupAnalyzer` runs `MatchupAnalyzer` across every pair of Pokemon in two
teams, producing a matchup matrix, summaries, threat assessments and structural
coverage scores. It does not predict match win probability.

Example:

```python
from pokebrain.data import DataManager

data = DataManager()
charizard = data.species.get_by_id("charizard")
earthquake = data.moves.get_by_id("earthquake")
```
