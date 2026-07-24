# Team Information Recovery

The recovery pipeline upgrades `PartialPolicyExample` records only when the
missing information comes from a trusted source. It must improve coverage
without turning inference into ground truth.

## Evidence

Every recovered field is represented with:

```text
value
source
confidence
first_known_turn
```

Supported sources are:

- `authoritative_runner`
- `team_export`
- `format_defined_set`
- `public_replay_log`
- `statistical_inference`

Only authoritative runner data, team exports, format-defined sets and observed
public replay facts may produce trusted legal actions. Statistical inference can
inform `BeliefState`, but it cannot create supervised labels.

## Separation

The actor's real team can be used to reconstruct legal actions, but it is not
copied into the policy observation. The policy state only receives public
knowledge known at that turn.

This prevents the dangerous leak:

```text
team export -> legal actions
team export -> hidden opponent set in observed state
```

The first arrow is allowed for trusted artifacts. The second is not.

## Legal Action Quality

Recovered legal actions are classified as:

- `authoritative`
- `reconstructed_complete`
- `reconstructed_partial`
- `unavailable`

Only `authoritative` and `reconstructed_complete` can become
`PolicyTrainingExample` records for the main supervised loss. Partial examples
remain useful for parser coverage, action frequency and calibration diagnostics.

## Current V1 Scope

Implemented:

- team export resolution;
- provenance per recovered field;
- conflict detection against observed public log facts;
- move and switch reconstruction for Gen 9 singles;
- forced-switch filtering;
- trapped active Pokemon cannot switch;
- basic Choice lock when the locked move is already observed;
- actual action must appear in reconstructed legal actions;
- differential legal-action metrics.

Still partial:

- PP tracking;
- Taunt, Encore and Disable timelines;
- ambiguous identity mechanics such as Illusion;
- doubles target selection;
- public replay recovery without any trusted team artifact.
