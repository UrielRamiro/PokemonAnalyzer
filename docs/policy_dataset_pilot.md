# Policy Dataset Pilot 1

O `policy-dataset-pilot-1` e o primeiro dataset com volume para diagnostico. Ele continua restrito a `gen9ou` e nao treina nenhum modelo.

## Construir

```powershell
.\.venv\bin\python.exe -m pokebrain build-policy-dataset-pilot --replays runs\2026-07-20\policy-smoke-3 --output data\policy\datasets\policy-dataset-pilot-1
```

Para o piloto real, substitua `policy-smoke-3` por uma lista maior de replays completos vindos de batalhas locais ou artefatos confiaveis.

## Auditar

Pelo CLI principal:

```powershell
.\.venv\bin\python.exe -m pokebrain audit-policy-dataset --dataset data\policy\datasets\policy-dataset-pilot-1
```

Pelo comando curto pedido no roadmap:

```powershell
.\.venv\bin\python.exe -m pokebrain.policy audit --dataset data\policy\datasets\policy-dataset-pilot-1
```

A auditoria falha com exit code diferente de zero se houver violacoes graves.

## Relatorios Gerados

- `manifest.json`: versoes, contagens e split.
- `quality_report.json`: cobertura basica.
- `audit_report.json`: integridade estrutural e semantica.
- `diversity_report.json`: concentracao por batalha, time, especie, turno, acoes e campo.
- `fingerprint_report.json`: duplicatas e ambiguidades.
- `baseline_report.json`: baselines antigos no split de teste.
- `authoritative/train.jsonl`, `validation.jsonl`, `test.jsonl`: splits por batalha.

## Verificacao De Baselines

Depois de construir o piloto, rode:

```powershell
.\.venv\bin\python.exe -m pokebrain evaluate-policy-baselines --format gen9ou --replays <replays> --output data\policy\eval\policy-dataset-pilot-1
```

Esse comando compara `random`, `frequency`, `frequency-active-species` e `heuristic-v3`, incluindo intervalos de confianca bootstrap agrupados por batalha.
