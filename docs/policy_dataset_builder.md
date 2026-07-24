# Policy Dataset Builder

`PolicyDatasetBuilder` is the first data-science layer after replay collection,
public parsing and team information recovery.

It does not train a model. It answers:

- how many complete examples exist;
- where they came from;
- how they split temporally;
- what the feature schema is;
- how simple baselines perform.

## Flow

```text
PolicyTrainingExample
-> quality filter
-> FeatureExtractor
-> temporal train / validation / test split
-> manifest
-> quality report
-> baseline report
```

`PartialPolicyExample` records remain useful for coverage analysis, but they are
not included in the main supervised dataset.

## Commands

Build a local dataset from replay artifact directories:

```powershell
.\.venv\bin\python.exe -m pokebrain build-policy-dataset --format gen9ou --replays runs\2026-07-20\policy-smoke-3 --output data\policy\datasets\policy-dataset-v1
```

Report quality without writing a full dataset:

```powershell
.\.venv\bin\python.exe -m pokebrain report-policy-dataset --format gen9ou --replays runs\2026-07-20\policy-smoke-3
```

Report replay catalog coverage:

```powershell
.\.venv\bin\python.exe -m pokebrain coverage-policy-dataset --format gen9ou --database data\database\replays.db
```

## Outputs

```text
manifest.json
quality_report.json
baseline_report.json
authoritative/
  train.jsonl
  validation.jsonl
  test.jsonl
reconstructed_complete/
partial/
```

## Feature Versioning

The current schema is:

```text
policy-features-v1
```

Changing feature names, order or semantics must create a new schema version.

## Baselines

The builder evaluates:

- random;
- frequency;
- current heuristic `OpponentPolicyModel`.

Future learned models should beat these baselines on the frozen test set before
being considered useful.
