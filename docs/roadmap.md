# Roadmap

## Phase 0: Data Manager

- Define domain models.
- Define provider interface.
- Read normalized Showdown data.
- Create and update the SQLite database.
- Query local data through `DataManager`.
- Provide `python -m pokebrain.data update`.
- Provide `python -m pokebrain.data inspect charizard`.

## Phase 1: Real Showdown Import

- Export Pokemon Showdown data through its Dex engine.
- Write normalized JSON to `data/normalized/v1`.
- Import Pokemon, moves, abilities, items, learnsets and formats.
- Resolve Dex data by mod/generation.
- Validate complete teams by Showdown format.

## Phase 2: Competitive Knowledge

- Add TeamAnalyzer v1.
- Detect hazards, removal, recovery, priority and basic roles.
- Calculate neutral set stats.
- Build defensive type profile.
- Add usage stats.

## Phase 3: Battle Reasoning

- Add DamageEngine through `@smogon/calc`.
- Add MatchupAnalyzer v1 for two concrete sets.
- Add TeamMatchupAnalyzer matrix.
- Add type matchup evaluation.
- Add damage calculation.
- Add board-state evaluation.
- Add BattleState and MoveDecisionEngine v1.
