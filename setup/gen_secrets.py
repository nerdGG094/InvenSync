"""Gera SECRET_KEY e VAULT_KEY fortes e grava no .env (substitui os placeholders).

Chamado pelo install.bat logo após criar o .env a partir do .env.example, para
que uma instalação nova NUNCA nasça com segredos previsíveis (senão o cookie de
sessão é forjável e o Cofre fica decifrável por quem tiver o repositório)."""
import os
import secrets
import sys

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

if not os.path.exists(ENV):
    print("[.env ausente — nada a fazer]")
    sys.exit(0)

with open(ENV, encoding="utf-8") as f:
    lines = f.read().splitlines()

KEYS = ("SECRET_KEY", "VAULT_KEY")
seen = set()
out = []
for ln in lines:
    k = ln.split("=", 1)[0].strip() if "=" in ln else ""
    if k in KEYS:
        out.append(f"{k}=" + secrets.token_urlsafe(48))
        seen.add(k)
    else:
        out.append(ln)
for k in KEYS:
    if k not in seen:
        out.append(f"{k}=" + secrets.token_urlsafe(48))

with open(ENV, "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")

print("SECRET_KEY e VAULT_KEY gerados automaticamente no .env.")
