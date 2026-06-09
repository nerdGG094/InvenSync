"""
Gera docs/DOCUMENTACAO.html a partir de docs/DOCUMENTACAO.md.

O HTML é autossuficiente (abre com duplo-clique): renderiza Markdown com
marked.js e os diagramas Mermaid no navegador. Para exportar PDF, abra o
HTML e use Ctrl+P → "Salvar como PDF".

Uso:  python docs/gerar_html.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MD = ROOT / "DOCUMENTACAO.md"
OUT = ROOT / "DOCUMENTACAO.html"

TEMPLATE = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>InvenSync — Documentação Técnica</title>
<style>
  :root { --fg:#1f2328; --muted:#656d76; --border:#d0d7de; --bg:#ffffff; --code:#f6f8fa; --accent:#0969da; }
  * { box-sizing: border-box; }
  body { margin:0; background:#eaeef2; color:var(--fg);
         font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; line-height:1.6; }
  .page { max-width:1000px; margin:24px auto; background:var(--bg); padding:48px 56px;
          border:1px solid var(--border); border-radius:10px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
  h1,h2,h3,h4 { line-height:1.25; margin-top:1.6em; margin-bottom:.6em; font-weight:600; }
  h1 { font-size:2em; border-bottom:1px solid var(--border); padding-bottom:.3em; }
  h2 { font-size:1.5em; border-bottom:1px solid var(--border); padding-bottom:.3em; }
  h3 { font-size:1.2em; }
  a { color:var(--accent); text-decoration:none; }
  a:hover { text-decoration:underline; }
  p,li { font-size:15px; }
  hr { border:0; border-top:1px solid var(--border); margin:2em 0; }
  blockquote { margin:1em 0; padding:.4em 1em; color:var(--muted);
               border-left:4px solid var(--border); background:#f6f8fa; }
  code { background:var(--code); padding:.15em .4em; border-radius:6px;
         font-family:"Cascadia Code",Consolas,monospace; font-size:85%; }
  pre code { display:block; padding:14px 16px; overflow:auto; }
  pre:not(.mermaid) { background:var(--code); border-radius:8px; overflow:auto; }
  table { border-collapse:collapse; width:100%; margin:1em 0; display:block; overflow:auto; }
  th,td { border:1px solid var(--border); padding:7px 12px; font-size:14px; text-align:left; }
  th { background:#f6f8fa; font-weight:600; }
  tr:nth-child(2n) td { background:#fbfcfd; }
  pre.mermaid { background:transparent; text-align:center; margin:1.4em 0; }
  .toolbar { max-width:1000px; margin:18px auto -6px; display:flex; gap:10px; justify-content:flex-end; }
  .toolbar button { border:1px solid var(--border); background:#fff; border-radius:8px;
                    padding:8px 14px; cursor:pointer; font-size:14px; }
  .toolbar button:hover { background:#f3f4f6; }
  @media print {
    body { background:#fff; } .toolbar { display:none; }
    .page { box-shadow:none; border:0; margin:0; padding:0; max-width:none; }
  }
</style>
</head>
<body>
<div class="toolbar"><button onclick="window.print()">🖨️ Imprimir / Salvar PDF</button></div>
<div class="page"><article id="content">Carregando…</article></div>

<textarea id="src" hidden>__MARKDOWN__</textarea>

<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });

  const src = document.getElementById('src').value;
  const content = document.getElementById('content');
  content.innerHTML = marked.parse(src);

  // Converte blocos ```mermaid (code.language-mermaid) em <pre class="mermaid">
  content.querySelectorAll('code.language-mermaid').forEach(code => {
    const holder = document.createElement('pre');
    holder.className = 'mermaid';
    holder.textContent = code.textContent;
    code.parentElement.replaceWith(holder);
  });

  try { await mermaid.run({ querySelector: 'pre.mermaid' }); }
  catch (e) { console.error('Mermaid:', e); }
</script>
</body>
</html>
"""


def main():
    md = MD.read_text(encoding="utf-8")
    if "</textarea>" in md:
        raise SystemExit("O Markdown contém '</textarea>', que quebraria o HTML.")
    OUT.write_text(TEMPLATE.replace("__MARKDOWN__", md), encoding="utf-8")
    print(f"Gerado: {OUT}  ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
