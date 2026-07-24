# Database

The local database is derived data. We can delete it and rebuild it from the
normalized snapshot.

Current database:

```text
data/database/pokemon.db
```

Current tables:

- `species`
- `species_types`
- `species_abilities`
- `base_stats`
- `moves`
- `abilities`
- `items`
- `types`
- `learnsets`
- `formats`
- `format_rules`
- `aliases`
- `metadata`

Important rule: code outside the data layer should avoid direct SQL queries.
Use `pokebrain.data.DataManager` instead.

