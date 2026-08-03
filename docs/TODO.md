# TODO

## Competitive Information Model

- Replace benchmark-only opponent full-moveset assumptions with partial-information play.
- Treat observed opponent moves, items and abilities as facts.
- Use `BeliefState` to infer unobserved opponent moves, items, abilities and Tera types from meta data and replay-derived usage.
- Score risks as probability-weighted outcomes instead of assuming every hidden move is known.
- Keep local full-information benchmarks available as controlled engineering tests, but label them separately from realistic competitive benchmarks.

## Why This Matters

Current local generated battles can expose complete opponent sets to the agent. That is useful for debugging search behavior, but not realistic for ladder or tournament play.

Final target:

```text
observed facts
+ plausible hidden-set distribution
-> expected risk / reward
-> decision
```

