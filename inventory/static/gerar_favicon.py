"""
Gera os ícones do InvenSync a partir do monograma `logos/is2.png`.

O monograma é branco com fundo transparente; aqui ele é composto sobre a faixa
VERMELHA da marca — a mesma do topo do menu — para que a aba do navegador e o
app instalado tenham exatamente a identidade que o sistema mostra na tela.

DUAS proporções, de propósito:

* **Ícone maskable (PWA)** — o Android recorta em qualquer formato (círculo,
  squircle, gota) e só a área central ~80% é garantida. O fundo sangra e o
  monograma fica em ~58% do lado, para sobrar inteiro em qualquer máscara.
* **Favicon** — ninguém recorta, e o espaço é ridículo (16px). Com os mesmos
  58% o monograma virava um borrão indistinguível na aba; aqui ele ocupa 80%
  do lado, que é o que faz os traços internos ainda se lerem.

Saídas (em inventory/static/):
    favicon.ico (16..256)  ·  favicon-16x16.png  ·  favicon-32x32.png
    favicon.svg  ·  apple-touch-icon.png (180)  ·  icon-192.png  ·  icon-512.png

Uso:  .venv\\Scripts\\python.exe inventory/static/gerar_favicon.py
"""
import base64
import io
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
MARCA = HERE / "logos" / "is2.png"

BANDA = (138, 47, 47)      # --band  #8a2f2f
BANDA_2 = (116, 39, 39)    # --band-2 #742727
P_FAVICON = 0.80           # aba do navegador: sem recorte, precisa de tamanho
P_MASKABLE = 0.58          # PWA: sobra folga para a máscara do sistema


def icone(lado: int, proporcao: float = P_FAVICON) -> Image.Image:
    """Fundo vermelho em degradê vertical + monograma branco centralizado."""
    img = Image.new("RGBA", (lado, lado), BANDA + (255,))
    px = img.load()
    for y in range(lado):
        t = y / max(1, lado - 1)
        cor = tuple(round(a + (b - a) * t) for a, b in zip(BANDA, BANDA_2)) + (255,)
        for x in range(lado):
            px[x, y] = cor

    marca = Image.open(MARCA).convert("RGBA")
    alvo = round(lado * proporcao)
    esc = alvo / marca.height
    marca = marca.resize((max(1, round(marca.width * esc)), alvo), Image.LANCZOS)
    img.alpha_composite(marca, ((lado - marca.width) // 2, (lado - marca.height) // 2))
    return img


def svg(lado: int = 128) -> str:
    """SVG com o ícone embutido — o navegador prefere este quando existe, e ele
    serve qualquer tamanho (aba em tela retina, barra de favoritos, atalho)."""
    buf = io.BytesIO()
    icone(lado).save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" '
        'width="512" height="512">\n'
        "  <!-- Gerado por gerar_favicon.py a partir de logos/is2.png. -->\n"
        '  <image href="data:image/png;base64,' + b64 + '" '
        'x="0" y="0" width="512" height="512"/>\n'
        "</svg>\n"
    )


def main():
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    pngs = {s: icone(s) for s in ico_sizes}

    pngs[256].save(HERE / "favicon.ico", format="ICO",
                   sizes=[(s, s) for s in ico_sizes])
    pngs[16].save(HERE / "favicon-16x16.png")
    pngs[32].save(HERE / "favicon-32x32.png")
    (HERE / "favicon.svg").write_text(svg(), encoding="utf-8")

    # Estes o sistema operacional recorta: menos monograma, mais folga
    for lado, nome in ((180, "apple-touch-icon.png"), (192, "icon-192.png"),
                       (512, "icon-512.png")):
        icone(lado, P_MASKABLE).save(HERE / nome, optimize=True)

    print("Ícones gerados a partir de", MARCA.name)


if __name__ == "__main__":
    main()
