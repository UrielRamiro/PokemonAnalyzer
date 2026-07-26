# VGC Iteration Workflow

Este e o fluxo atual para evoluir o agente de VGC Champions Reg M-B.

Use este documento quando quiser:

- gerar runs novas de campanha;
- construir/auditar um dataset;
- rodar benchmark competitivo;
- analisar derrotas;
- decidir a proxima melhoria do Search.

## 1. Gerar Runs De Campanha

Campanhas geram batalhas em massa para dataset e auditoria de cobertura.

Canario rapido:

```powershell
python -m pokebrain.battles campaign-run --campaign champions-vgc-regmb-doubles-search-canary-3 --workers 10 --resume
```

Piloto principal:

```powershell
python -m pokebrain.battles campaign-run --campaign champions-vgc-regmb-doubles-search-pilot-1 --workers 10 --resume

```

Ver progresso:

```powershell
python -m pokebrain.battles campaign-report --campaign champions-vgc-regmb-doubles-search-pilot-1
```

Auditar se as batalhas parecem VGC:

```powershell
python -m pokebrain.battles vgc-audit --campaign champions-vgc-regmb-doubles-search-pilot-1
```

O que olhar no `vgc-audit`:

- `crashes`, `protocol errors` e `invalid`: devem ser zero ou muito raros;
- turnos medios e p95;
- uso de Protect/Detect;
- Fake Out;
- redirection;
- Tailwind/speed control;
- Trick Room;
- weather;
- especies, itens e habilidades mais frequentes.

## 2. Construir Dataset

Depois que a campanha tiver runs suficientes:

```powershell
python -m pokebrain.policy build --campaign champions-vgc-regmb-doubles-search-pilot-1 --dataset data\policy\datasets\champions-vgc-regmb-search-pilot-1 --format gen9championsvgc2026regmb
```

Auditar o dataset:

```powershell
python -m pokebrain.policy audit --dataset data\policy\datasets\champions-vgc-regmb-search-pilot-1
```

Avaliar baselines:

```powershell
python -m pokebrain.policy evaluate --campaign champions-vgc-regmb-doubles-search-pilot-1 --dataset data\policy\datasets\champions-vgc-regmb-search-pilot-1 --output data\policy\eval\champions-vgc-regmb-search-pilot-1 --format gen9championsvgc2026regmb
```

Regra: se o audit tiver violacoes graves, nao use o dataset para treino ou conclusoes.

## 3. Rodar Benchmark Competitivo

Benchmark mede forca de jogo. Ele e separado da campanha de dataset.

Confronto principal atual:

```powershell
python -m pokebrain benchmark --format gen9championsvgc2026regmb --agent-a search-v3-policy --agent-b pokebrain-v1 --battles 10000 --teams teams\champions-vgc-pilot-1 --seed 20260725 --maximum-turns 80 --timeout-seconds 240 --parallel-workers 4
```

Outros confrontos uteis:

```powershell
python -m pokebrain benchmark --format gen9championsvgc2026regmb --agent-a search-v3-policy --agent-b random --battles 10000 --teams teams\champions-vgc-pilot-1 --seed 20260726 --maximum-turns 80 --timeout-seconds 240 --parallel-workers 4
```

```powershell
python -m pokebrain benchmark --format gen9championsvgc2026regmb --agent-a search-v3-policy --agent-b search-v2-belief-layered --battles 10000 --teams teams\champions-vgc-pilot-1 --seed 20260727 --maximum-turns 80 --timeout-seconds 240 --parallel-workers 4
```

O benchmark imprime um `Run ID`:

```text
Run ID: benchmark-YYYYMMDDHHMMSS
```

Guarde esse ID para analise e comparacao.

## 4. Analisar Derrotas

Use o `Run ID` do benchmark:

```powershell
python -m pokebrain review-benchmark --run benchmark-SEU-ID --only-losses --top 15 --min-battles 10
```

Use `--min-battles` para reduzir ruido:

- `3`: bom para investigar benchmark pequeno;
- `10`: bom para 1000 partidas;
- `25+`: bom para benchmarks maiores.

O relatorio mostra:

- piores especies adversarias;
- piores arquetipos adversarios;
- piores leads proprios;
- piores times proprios;
- derrotas mais curtas;
- derrotas mais longas;
- diretorios de replay para abrir.

Nao trate `0V/3D` como prova. Isso e apenas sinal fraco. Priorize grupos com mais volume.

## 5. Comparar Benchmarks

Depois de mudar o Search, rode outro benchmark com seed e times comparaveis.

Compare:

```powershell
python -m pokebrain compare-benchmarks --run-a benchmark-ANTIGO --run-b benchmark-NOVO
```

Promova uma mudanca apenas se ela:

- nao aumentar acoes ilegais;
- nao gerar erros de protocolo;
- melhorar win rate de forma consistente;
- nao piorar muito buckets importantes;
- explicar melhor uma fraqueza observada.

## 6. Ciclo De Trabalho

O ciclo recomendado pelo tech lead agora e:

```text
benchmark
-> review-benchmark
-> escolher uma fraqueza objetiva
-> melhorar Search
-> benchmark novo
-> compare-benchmarks
-> repetir
```

Exemplos de fraquezas objetivas:

- desempenho ruim contra Sun;
- desempenho ruim contra Rain;
- desempenho ruim contra Trick Room;
- lead proprio com win rate baixo;
- Protect usado em momentos ruins;
- Tailwind ou speed control subestimado;
- derrotas muito curtas contra um nucleo especifico.

## 7. Limpeza Antes De Regerar

Para zerar somente benchmarks:

```text
runs/
battles/
data/database/benchmarks.db
```

Para zerar campanhas tambem:

```text
data/database/battle_campaigns.db
```

Nao apague `data/database/pokemon.db` a menos que queira reimportar os dados do Showdown.
