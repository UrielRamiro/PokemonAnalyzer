# Public Replay Parser

`PublicReplayParser` reconstructs only observable public state from Pokemon
Showdown replay logs.

## Layers

```text
raw log
-> ReplayProtocolParser
-> typed ReplayEvent objects
-> PublicReplayStateReducer
-> ReplaySnapshot objects
-> PolicyExampleBuilder
-> PartialPolicyExample objects
```

The parser does not call the opponent policy model. It only reconstructs facts.

## Supported Scope

V1 targets Gen 9 singles logs without ambiguous identity mechanics. Unsupported
or suspicious protocol lines are preserved as typed unsupported events and
surface through `ReplayReconstructionStatus`.

Supported event families include:

- turn start;
- team preview species;
- switches;
- moves;
- damage and healing;
- fainting;
- status;
- stat boosts;
- item, ability and Tera reveals;
- hazards, weather and terrain;
- battle end.

## Hidden Information

The parser does not invent hidden information:

- no EVs, IVs or natures;
- no unrevealed moves;
- no unrevealed item or ability;
- no exact HP when only percentage HP is public.

When legal actions cannot be generated safely, the builder emits
`PartialPolicyExample` instead of `PolicyTrainingExample`.

## Catalog Status

The replay extraction job now parses raw public replay logs. If legal actions or
full team information are missing, the catalog uses:

```text
parse_status = partial
failure_reason = partial_missing_legal_actions,partial_missing_team
```

This keeps the dataset useful for coverage and calibration diagnostics without
turning incomplete public information into supervised labels.
