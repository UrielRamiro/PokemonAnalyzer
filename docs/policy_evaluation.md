# Policy Evaluation Framework

Este modulo mede se um preditor de politica realmente melhorou antes de qualquer modelo novo entrar na busca.

## Preditores

Todos os modelos implementam o mesmo contrato:

```python
class PolicyPredictor(Protocol):
    name: str

    def predict(self, example: PolicyTrainingExample) -> PolicyPrediction:
        ...
```

`PolicyPrediction` guarda:

- `ranked_actions`: acoes ordenadas por preferencia.
- `probabilities`: probabilidades na mesma ordem das acoes.
- `inference_time_ms`: custo de inferencia por exemplo.

Os preditores iniciais sao:

- `random`
- `frequency`
- `frequency-active-species`
- `heuristic-v3`

## Metricas

O runner gera:

- Top-1 Accuracy
- Top-3 Coverage
- Top-5 Coverage
- Log Loss
- Brier Score
- Expected Calibration Error
- inferencia media, p95 e p99
- acoes impossiveis previstas
- probabilidade media da acao real
- entropia media
- curva de calibracao
- intervalos de confianca 95% por bootstrap agrupado por batalha
- buckets de erro por tipo de acao
- buckets por arquotipo aproximado de matchup
- casos de inspecao com replay, turno, predicao e acao real

## Comandos

Avaliar os baselines no mesmo conjunto:

```powershell
.\.venv\bin\python.exe -m pokebrain evaluate-policy-baselines --format gen9ou --replays runs\2026-07-20\policy-smoke-3 --output runs\2026-07-20\policy-eval
```

Comparar o baseline de frequencia contra a heuristica atual:

```powershell
.\.venv\bin\python.exe -m pokebrain compare-policy-baselines --format gen9ou --replays runs\2026-07-20\policy-smoke-3 --output runs\2026-07-20\policy-compare
```

## Golden Benchmark

Para congelar uma avaliacao, use sempre o mesmo conjunto de replays e salve a pasta de saida. Modelos futuros devem ser comparados contra esse mesmo conjunto, olhando nao apenas Top-1, mas tambem Log Loss, calibracao, latencia e acoes impossiveis.
