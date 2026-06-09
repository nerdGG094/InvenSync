# 📦 InvenSync

Sistema de controle de **almoxarifado de TI** (toner, cilindros, periféricos, peças e ativos) da
**Refrigerantes Jaboti**. Aplicação web em **Flask + PostgreSQL**, servida em produção via
**waitress** e gerenciada por um **launcher** desktop (PyQt5).

## 📚 Documentação

A documentação técnica completa (arquitetura, modelo de dados, UML, sequências e fluxos) está em
diagramas **Mermaid**:

➡️ **[docs/DOCUMENTACAO.md](docs/DOCUMENTACAO.md)** — abra no GitHub ou no VS Code para ver os diagramas renderizados.
➡️ **[docs/DOCUMENTACAO.html](docs/DOCUMENTACAO.html)** — versão para visualizar no navegador / exportar PDF (Ctrl+P).

> Para regenerar o HTML após editar o `.md`: `python docs/gerar_html.py`

## ✨ Principais recursos

- Cadastro de produtos com campos de TI (marca, modelo, patrimônio, nº de série, localização, compatibilidade, validade)
- **SKU automático** (`PREFIXO-0001`) a partir da categoria/tipo
- Movimentações de estoque (entrada/saída) com histórico, filtros e totais
- **Kanban** de saúde de estoque e **painel** com gráficos
- Relatórios e exportação **CSV**
- Gestão de usuários com **controle de acesso** (ativo/inativo)
- Interface responsiva (celular/tablet) e tema escuro

## 🛠️ Stack

Python 3.12 · Flask 3 · SQLAlchemy 2 · PostgreSQL 17 · psycopg 3 · Bootstrap 5 · waitress · PyQt5

## 🚀 Como rodar

### Produção (recomendado)
```bat
setup\install.bat          :: cria .venv, instala deps, gera .env e atalhos (Desktop + Inicialização)
setup\start_invensync.bat  :: abre o painel e sobe o servidor (waitress)
```
Acesse **http://192.168.0.54:5090**

### Desenvolvimento
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      :: e preencha a senha do PostgreSQL
python run.py
```

## 🔐 Configuração

As credenciais (`SECRET_KEY`, `DB_PASSWORD`, …) ficam no arquivo **`.env`** (não versionado).
Use o **`.env.example`** como modelo.

---
🤖 Desenvolvido com apoio do [Claude Code](https://claude.com/claude-code)
