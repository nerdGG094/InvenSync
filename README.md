\
# Inventário (Flask + SQLite) — v2 (login fix)

- **Admin criado deterministicamente** ao iniciar o app (não depende de request).
- **Validação de e-mail ajustada** para aceitar `admin@local`.
- Estrutura em camadas: routes / services / repositories / models / forms.
- Compatível com Flask 3.x.

## Rodando
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python run.py
```
Abra http://127.0.0.1:5000

Login inicial: **admin@local** / **admin**

Se quiser resetar o banco, apague `instance/inventory.db` e execute novamente.
