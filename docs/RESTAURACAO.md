# Restauração do banco — InvenSync

Procedimento para recuperar dados do InvenSync a partir dos backups. Leia antes
de precisar: a hora de descobrir que o dump não presta não é durante a queda.

---

## O que existe hoje

| Camada | O que cobre | O que **não** cobre |
|---|---|---|
| **Backup da VM inteira** para outro servidor (rotina de infraestrutura, fora deste repositório) | Perda do servidor: disco, máquina, sala | Recuperar **um** dado. Voltar a VM inteira para pegar uma tabela derruba tudo o que roda nela |
| **`pg_dump` diário do banco** (`backup_db.py`, formato *custom* `-Fc`) | Recuperação **cirúrgica e rápida**: uma tabela, um registro, o banco todo | Perda do servidor — os arquivos ficam dentro da própria VM |

As duas se complementam: a VM é o seguro contra perder a máquina; o dump é o que
se usa no dia em que alguém apagou algo ou uma alteração saiu errada.

**Estado medido em 18/09/2026:** 30 dumps na pasta `backups/` (rotação por
`BACKUP_KEEP`), 161 MB no total, um por dia às ~02:08, o mais recente com
8,2 MB. O agendador é o próprio app (`BACKUP_SCHEDULER_ENABLED`, `BACKUP_HOUR`)
e ele tem *self-heal*: se o servidor estava desligado na hora marcada, o backup
sai na primeira verificação depois que ele sobe.

---

## Antes de qualquer coisa: a VAULT_KEY

O banco guarda **segredos cifrados** — cofre de senhas, senha de roteador, senha
de DVR e a *local key* das tomadas. A chave **não está no banco**: está no
`.env`, em `VAULT_KEY`.

> Restaurar o banco num ambiente com `VAULT_KEY` diferente devolve tudo **menos**
> esses segredos: as linhas voltam, mas o texto cifrado não abre. E o sintoma é
> traiçoeiro — as telas carregam normalmente, e só quem tentar **usar** uma senha
> descobre. Guarde a `VAULT_KEY` junto com a rotina de backup, não só no servidor.

Vale o mesmo para `SECRET_KEY` (sessões e CSRF): trocá-la não perde dado, apenas
desloga todo mundo.

---

## Ensaio (faça isto de tempos em tempos, sem medo)

```powershell
cd C:\...\InventarioAlmox
powershell -ExecutionPolicy Bypass -File setup\ensaio_restauracao.ps1
```

O script restaura o dump **mais recente** num banco descartável
(`inventario_almox_ensaio`), conta as linhas das tabelas principais, compara com
a produção, cronometra e apaga o banco de ensaio no fim. Ele **nunca** escreve no
banco de produção — e se recusa a rodar se o nome do banco de ensaio for igual ao
da produção.

Opções úteis:

```powershell
# ensaiar um dump específico (ex.: o mais antigo, para testar a retenção)
powershell -ExecutionPolicy Bypass -File setup\ensaio_restauracao.ps1 -Dump backups\inventario_almox_20260820_020810.dump

# manter o banco restaurado, para olhar os dados
powershell -ExecutionPolicy Bypass -File setup\ensaio_restauracao.ps1 -Manter
```

---

## Cenário 1 — recuperar um dado apagado (o mais comum)

Não restaure por cima da produção para isso. Restaure num banco paralelo e copie
só o que precisa:

```powershell
$PG = "C:\Program Files\PostgreSQL\17\bin"
$env:PGPASSWORD = "<senha do postgres>"

& "$PG\createdb.exe"   -U postgres inventario_almox_recuperar
& "$PG\pg_restore.exe" -U postgres -d inventario_almox_recuperar --no-owner --no-privileges `
                       backups\inventario_almox_20260917_020824.dump
```

Depois, com `psql` no banco `inventario_almox_recuperar`, localize a linha e
copie-a para a produção (ou apenas anote os valores e refaça o cadastro pela
tela, que é mais seguro e deixa rastro na auditoria). Ao terminar:

```powershell
& "$PG\dropdb.exe" -U postgres inventario_almox_recuperar
```

## Cenário 2 — restaurar o banco inteiro por cima

Isto **descarta** tudo o que aconteceu depois do dump escolhido. Só faça com essa
decisão tomada.

```powershell
# 1. Derrube o app (senão as conexões abertas impedem o drop).
#    Pelo launcher (botão Parar) ou, na mão, pelo MESMO filtro que o
#    reiniciar.ps1 usa -- por ExecutablePath, nunca por nome de processo:
#    este servidor roda outros apps Python com linha de comando idêntica.
$raiz = (Resolve-Path .).Path.TrimEnd('\') + '\'
Get-CimInstance Win32_Process -Filter "name='pythonw.exe' or name='python.exe'" |
  Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($raiz, 'OrdinalIgnoreCase') } |
  Sort-Object ParentProcessId -Descending |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# 2. Guarde o estado atual antes de sobrescrever -- inclusive um banco quebrado
#    é evidência: se a restauração der errado, é para ele que se volta
.venv\Scripts\python.exe backup_db.py

# 3. Recrie o banco vazio e restaure
$PG = "C:\Program Files\PostgreSQL\17\bin"
$env:PGPASSWORD = "<senha do postgres>"
& "$PG\dropdb.exe"     -U postgres --force inventario_almox
& "$PG\createdb.exe"   -U postgres -O postgres inventario_almox
& "$PG\pg_restore.exe" -U postgres -d inventario_almox --no-owner --no-privileges `
                       backups\<arquivo escolhido>.dump

# 4. Suba e confira
powershell -ExecutionPolicy Bypass -File setup\reiniciar.ps1
curl.exe -s http://127.0.0.1:5090/health | python -m json.tool
```

O `pg_restore` pode terminar com avisos sobre *owner*/extensões mesmo tendo dado
certo — é o esperado com `--no-owner`. O que importa é o código de saída e a
conferência do passo 4.

## Cenário 3 — o servidor se perdeu

1. Restaure a VM no destino disponível (rotina de infraestrutura).
2. Confira o `.env` — principalmente **`VAULT_KEY`** e `SECRET_KEY`.
3. Veja a data do dump mais recente dentro da VM restaurada (`backups\`). Se o
   snapshot da VM for mais novo que o último dump, o banco que veio na imagem já
   é o mais atual: **não restaure o dump por cima**, ele é mais velho.
4. Suba pelo launcher e confira `/health` e a tela de login.

---

## Conferência depois de restaurar

```sql
-- contagens das tabelas que mais contam a história
SELECT 'user' t, count(*) FROM "user"
UNION ALL SELECT 'product',        count(*) FROM product
UNION ALL SELECT 'stock_movement', count(*) FROM stock_movement
UNION ALL SELECT 'machine',        count(*) FROM machine
UNION ALL SELECT 'ticket',         count(*) FROM ticket
UNION ALL SELECT 'audit_log',      count(*) FROM audit_log;

-- até quando o banco restaurado enxerga
SELECT max(created_at) FROM audit_log;
SELECT max(created_at) FROM stock_movement;
```

E, pela aplicação: abrir `/audit` (o evento mais recente tem de bater com a data
do dump), fazer login, e **revelar uma senha do cofre** — é o teste que prova que
a `VAULT_KEY` do ambiente combina com o banco restaurado.

---

## Armadilhas conhecidas

- **`pg_restore` mais antigo que o `pg_dump`** que gerou o arquivo não lê o
  formato. Use o binário da mesma instalação (ou mais nova) que gerou o dump.
- **Conexões abertas impedem `dropdb`**. Pare o app primeiro; `--force` resolve
  no PostgreSQL 13+, mas derrubar conexão de um app vivo é pior que pará-lo.
- **`--no-owner --no-privileges`** evita erro quando o *role* dono não existe no
  destino. Sem isso, um restore em outra máquina falha em cascata.
- **O dump não leva o `.env`.** Uploads (anexos de chamados, NFs, fotos do cofre,
  avatares) também **não** estão no dump: vivem em `uploads_private\` e
  `inventory\static\uploads\`, e quem os cobre é o backup da VM.
- **Restaurar não devolve espaço em disco automaticamente** no banco de origem;
  isso é assunto de `VACUUM`, não de restauração.
