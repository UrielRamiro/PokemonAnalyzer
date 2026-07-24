# BeliefState

`search-v2-belief` is the first opponent-uncertainty agent. It receives the
normal player request plus `observed_opponent`, a sanitized opponent view that
hides private moves, item, ability and Tera information.

## Model

- `WeightedValue`: value plus probability.
- `PokemonBelief`: possible items, abilities, moves and Tera types for one
  opponent Pokemon, plus revealed facts.
- `BeliefState`: opponent team beliefs.
- `OpponentScenario`: one resolved battle state with assumptions and weight.

## Updates

`BeliefStateReducer` handles revealed moves, items, abilities, Tera type and
simple incompatibilities. For example, hazard damage removes
`heavydutyboots` from item hypotheses and renormalizes the distribution.

## Search

`BeliefSearchDecisionEngine` generates the top K active-opponent scenarios and
evaluates each scenario with the existing search engine. Action values are
combined by scenario probability.

`search-v2-belief-shared` keeps a shared L1 damage cache for the whole decision
instead of clearing it per scenario. It also performs a global root prefetch
across all scenarios so repeated official damage calculations can be batched
and reused before individual scenario searches expand.

`search-v2-belief-layered` adds a rigid decision budget and iterative
deepening. It tries depth 1 first, stores the completed result, then attempts
depth 2 only while the shared deadline still has room. If a deeper layer times
out, the agent returns the last completed depth instead of falling back all the
way to the old one-turn agent.

Smoke result on `search-v2-belief-shared` vs `search-v2-belief-layered` with
`--pairs 1 --maximum-turns 1`:

- shared pipeline: ~1007ms average decision time, depth 2 attempted directly;
- layered scheduler: ~421ms average decision time, depth 1 completed and depth
  2 skipped when the bridge safety estimate did not fit the remaining budget;
- stability remained 0 illegal actions, 0 crashes and 0 protocol errors.

Smoke result on `search-v2-belief` vs `search-v2-belief-shared` with
`--pairs 1 --maximum-turns 1`:

- old belief agent: ~13.8s average decision time, 41 bridge batches;
- shared pipeline: ~986ms average decision time, 2 bridge batches;
- stability remained 0 illegal actions, 0 crashes and 0 protocol errors.

Current v1 simplifications:

- item, ability, move and Tera distributions are independent;
- EV inference is not modeled;
- local priors are deterministic placeholders until usage-stat imports exist;
- only a few top scenarios are evaluated per decision.
- the shared pipeline currently optimizes root damage prefetch and cache reuse;
  deeper multi-scenario layer batching is still future work.
- the layered scheduler currently batches root prefetch per depth and records
  layer metrics; full split planning/resolution for every deep layer is still
  future work.
