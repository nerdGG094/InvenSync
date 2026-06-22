"""Documentação viva do sistema (módulo Admin → Documentação).

Boa parte do conteúdo é **introspectada do app em tempo de request**: rotas
(de `app.url_map`), blueprints, modelos (`models/`), serviços (`services/`),
repositórios (`repositories/`) e tabelas (do `metadata` do SQLAlchemy). Por isso
a página se atualiza sozinha conforme o código muda — não há texto fixo a manter.

A seção de **Arquitetura & Diagramas** vem do markdown em `docs/DOCUMENTACAO.md`,
convertido para HTML aqui mesmo (sem dependências externas). Os blocos
```mermaid viram <div class="mermaid"> e são renderizados no navegador. Editar o
.md atualiza tanto esta seção quanto o `docs/DOCUMENTACAO.html`.
"""
import ast
import html
import os
import re
import unicodedata

DIR_INVENTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(DIR_INVENTORY)
DIR_MODELS = os.path.join(DIR_INVENTORY, "models")
DIR_ROUTES = os.path.join(DIR_INVENTORY, "routes")
DIR_SERVICES = os.path.join(DIR_INVENTORY, "services")
DIR_REPOS = os.path.join(DIR_INVENTORY, "repositories")
DOC_MD = os.path.join(PROJECT_ROOT, "docs", "DOCUMENTACAO.md")

_HTTP_OCULTOS = {"HEAD", "OPTIONS"}


# ======================================================================
#  Introspecção ao vivo
# ======================================================================
def _docstring_primeira_linha(caminho):
    """Primeira linha do docstring de um arquivo .py (sem executá-lo)."""
    try:
        with open(caminho, encoding="utf-8") as f:
            doc = ast.get_docstring(ast.parse(f.read())) or ""
        return doc.strip().split("\n")[0].strip()
    except Exception:
        return ""


def _modulos_de(diretorio):
    itens = []
    if not os.path.isdir(diretorio):
        return itens
    for nome in sorted(os.listdir(diretorio)):
        if not nome.endswith(".py") or nome == "__init__.py":
            continue
        itens.append({
            "nome": nome,
            "descricao": _docstring_primeira_linha(os.path.join(diretorio, nome)),
        })
    return itens


def _rotas(app):
    """Rotas agrupadas por blueprint, a partir de app.url_map."""
    grupos = {}
    for regra in app.url_map.iter_rules():
        endpoint = regra.endpoint
        bp = endpoint.split(".")[0] if "." in endpoint else "(app)"
        metodos = sorted((regra.methods or set()) - _HTTP_OCULTOS)
        grupos.setdefault(bp, []).append({
            "rule": str(regra),
            "endpoint": endpoint,
            "metodos": metodos,
        })
    for bp in grupos:
        grupos[bp].sort(key=lambda r: r["rule"])
    return dict(sorted(grupos.items()))


def _tabelas():
    """Tabelas do banco a partir do metadata do SQLAlchemy (nome + nº de colunas)."""
    try:
        from ..extensions import db
        meta = db.metadata
        return [
            {"tabela": nome, "colunas": len(tab.columns)}
            for nome, tab in sorted(meta.tables.items())
        ]
    except Exception:
        return []


def _acesso():
    """Resumo do modelo de acesso (RBAC) lido do pacote da aplicação."""
    try:
        from .. import NON_ADMIN_PREFIXES, NON_ADMIN_ENDPOINTS
        return {
            "prefixos_comuns": sorted(NON_ADMIN_PREFIXES),
            "endpoints_comuns": sorted(NON_ADMIN_ENDPOINTS),
        }
    except Exception:
        return {"prefixos_comuns": [], "endpoints_comuns": []}


def introspectar(app):
    """Snapshot vivo da estrutura do app para a página de documentação."""
    rotas = _rotas(app)
    total_rotas = sum(len(v) for v in rotas.values())
    modelos = _modulos_de(DIR_MODELS)
    servicos = _modulos_de(DIR_SERVICES)
    repos = _modulos_de(DIR_REPOS)
    tabelas = _tabelas()
    blueprints = sorted(b for b in app.blueprints)
    return {
        "rotas": rotas,
        "modelos": modelos,
        "servicos": servicos,
        "repositorios": repos,
        "tabelas": tabelas,
        "blueprints": blueprints,
        "acesso": _acesso(),
        "resumo": {
            "blueprints": len(blueprints),
            "rotas": total_rotas,
            "modelos": len(modelos),
            "servicos": len(servicos),
            "repositorios": len(repos),
            "tabelas": len(tabelas),
        },
    }


# ======================================================================
#  Markdown -> HTML (mini conversor, sem dependências)
# ======================================================================
def _slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    t = t.lower()
    t = re.sub(r"[^a-z0-9 \-]", "", t)
    return t.replace(" ", "-")


def _inline(texto):
    codes = []

    def guardar(m):
        codes.append(html.escape(m.group(1)))
        return f"\x00{len(codes) - 1}\x00"

    texto = re.sub(r"`([^`]+)`", guardar, texto)
    texto = html.escape(texto)
    texto = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", texto)
    texto = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', texto)
    texto = re.sub(r"\x00(\d+)\x00",
                   lambda m: f"<code>{codes[int(m.group(1))]}</code>", texto)
    return texto


def _eh_separador(linha):
    return (bool(re.match(r"^\s*\|?\s*:?-{2,}", linha))
            and set(linha.strip()) <= set("|:- "))


def _celulas(linha):
    return [c.strip() for c in linha.strip().strip("|").split("|")]


def markdown_para_html(md):
    linhas = md.split("\n")
    out, i, n = [], 0, len(linhas)
    while i < n:
        ln = linhas[i]

        if ln.startswith("```"):
            lang = ln[3:].strip()
            buf = []
            i += 1
            while i < n and not linhas[i].startswith("```"):
                buf.append(linhas[i])
                i += 1
            i += 1
            corpo = "\n".join(buf)
            if lang == "mermaid":
                out.append('<div class="mermaid">\n' + corpo + "\n</div>")
            else:
                out.append('<pre class="md-code"><code>' + html.escape(corpo) + "</code></pre>")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            nivel, txt = len(m.group(1)), m.group(2).strip()
            out.append(f'<h{nivel} id="{_slug(txt)}">{_inline(txt)}</h{nivel}>')
            i += 1
            continue

        if ln.strip() == "---":
            out.append("<hr>")
            i += 1
            continue

        if "|" in ln and i + 1 < n and _eh_separador(linhas[i + 1]):
            header = _celulas(ln)
            i += 2
            corpo = []
            while i < n and "|" in linhas[i] and linhas[i].strip():
                corpo.append(_celulas(linhas[i]))
                i += 1
            t = ["<table>", "<thead><tr>"]
            t += [f"<th>{_inline(c)}</th>" for c in header]
            t.append("</tr></thead><tbody>")
            for row in corpo:
                t.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>")
            t.append("</tbody></table>")
            out.append("\n".join(t))
            continue

        if ln.startswith(">"):
            buf = []
            while i < n and linhas[i].startswith(">"):
                buf.append(linhas[i].lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + _inline(" ".join(buf)) + "</blockquote>")
            continue

        if re.match(r"^\d+\.\s+", ln):
            buf = []
            while i < n and re.match(r"^\d+\.\s+", linhas[i]):
                buf.append(re.sub(r"^\d+\.\s+", "", linhas[i]))
                i += 1
            out.append("<ol>" + "".join(f"<li>{_inline(x)}</li>" for x in buf) + "</ol>")
            continue

        if re.match(r"^[-*]\s+", ln):
            buf = []
            while i < n and re.match(r"^[-*]\s+", linhas[i]):
                buf.append(re.sub(r"^[-*]\s+", "", linhas[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in buf) + "</ul>")
            continue

        if not ln.strip():
            i += 1
            continue

        buf = [ln]
        i += 1
        while (i < n and linhas[i].strip()
               and not re.match(r"^(#{1,6}\s|```|>|[-*]\s|\d+\.\s)", linhas[i])
               and linhas[i].strip() != "---"
               and not ("|" in linhas[i] and i + 1 < n and _eh_separador(linhas[i + 1]))):
            buf.append(linhas[i])
            i += 1
        out.append("<p>" + _inline(" ".join(buf)) + "</p>")

    return "\n".join(out)


def doc_arquitetura_html():
    """HTML da documentação (DOCUMENTACAO.md). Retorna None se o arquivo não existir."""
    if not os.path.isfile(DOC_MD):
        return None
    try:
        with open(DOC_MD, encoding="utf-8") as f:
            return markdown_para_html(f.read())
    except Exception:
        return None
