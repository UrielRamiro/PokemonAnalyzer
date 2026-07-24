# Battle Generation Campaign v1

Uma campanha gera batalhas locais de forma reproduzivel antes do dataset consumir qualquer exemplo.

## Conceitos

Os arquivos em `campaigns/` definem formato, seed mestre, pool de times, matriz de agentes, limites operacionais e metas de cobertura.

O runner escreve primeiro em `runs/<data>/<battle-id>/`. Depois que a batalha passa pela validacao, a campanha preserva o artefato final em `battles/<campaign-id>/<battle-index>/`.

Cada batalha concluida preserva:

```text
battles/
  <campaign-id>/
    000001/
      battle.json
      team-p1.txt
      team-p2.txt
      protocol.log
      decisions.jsonl
      states.jsonl
      metadata.json
```

## Comandos De Campanha

Criar ou atualizar o ledger:

```powershell
.\.venv\bin\python.exe -m pokebrain.battles campaign-create --config campaigns\<campaign-id>.yaml
```

Rodar ou retomar usando o arquivo:

```powershell
.\.venv\bin\python.exe -m pokebrain.battles campaign-run --config campaigns\<campaign-id>.yaml --workers 1 --resume
```

Rodar ou retomar usando o id:

```powershell
.\.venv\bin\python.exe -m pokebrain.battles campaign-run --campaign <campaign-id> --workers 1 --resume
```

Ver resumo da campanha:

```powershell
.\.venv\bin\python.exe -m pokebrain.battles campaign-report --campaign <campaign-id>
```

Listar jobs:

```powershell
.\.venv\bin\python.exe -m pokebrain.battles campaign-jobs --campaign <campaign-id>
```

Listar apenas um status:

```powershell
.\.venv\bin\python.exe -m pokebrain.battles campaign-jobs --campaign <campaign-id> --status failed_retryable
```

Statuses suportados:

```text
pending
running
completed
failed_retryable
invalid
```

## Champions VGC Reg M-B

O projeto usa o formato real do Pokemon Showdown para Champions Reg M-B:

```text
gen9championsvgc2026regmb
```

Esse formato requer uma build atual do Pokemon Showdown com `data/mods/champions`.

O canario atual recomendado para validar a ponte doubles e a homologacao VGC e:

```powershell
.\.venv\bin\python.exe -m pokebrain.battles campaign-run --campaign champions-vgc-regmb-doubles-canary-1 --workers 1 --resume
```

Depois rode a auditoria competitiva:

```powershell
.\.venv\bin\python.exe -m pokebrain.battles vgc-audit --campaign champions-vgc-regmb-doubles-canary-1
```

O relatorio deve mostrar:

```text
Game types: (('doubles', ...),)
```

Tambem deve mostrar mecanicas como Protect, Fake Out, Trick Room, clima e Tera quando elas aparecerem nos jogos.

Para gerar o piloto completo com os times importados do MetaVGC:

```powershell
.\.venv\bin\python.exe -m pokebrain.battles campaign-create --config campaigns\champions-vgc-regmb-doubles-pilot-1.yaml
.\.venv\bin\python.exe -m pokebrain.battles campaign-run --campaign champions-vgc-regmb-doubles-pilot-1 --workers 10 --resume
```

Importante: `champions-vgc-compatible-pilot-1` foi gerado antes da ponte doubles e o protocolo dele aparece como singles. Ele nao deve ser tratado como dataset VGC real. As campanhas `champions-vgc-compatible-*` tambem usavam apenas os times compatíveis com o Showdown npm antigo; prefira `champions-vgc-regmb-doubles-*`.

## Gerar Dataset Da Campanha

```powershell
.\.venv\bin\python.exe -m pokebrain.policy build --campaign <campaign-id> --dataset data\policy\datasets\<dataset-id>
```

Depois:

```powershell
.\.venv\bin\python.exe -m pokebrain.policy audit --dataset data\policy\datasets\<dataset-id>
```

```powershell
.\.venv\bin\python.exe -m pokebrain.policy evaluate --campaign <campaign-id> --output data\policy\eval\<dataset-id>
```
