"""
Gera os ícones do InvenSync a partir do monograma `logos/is2.png`.

O monograma é branco com fundo transparente; aqui ele é composto sobre a faixa
VERMELHA da marca — a mesma do topo do menu — para que a aba do navegador e o
app instalado tenham exatamente a identidade que o sistema mostra na tela.

Ícone maskable: o Android recorta o ícone em qualquer formato (círculo,
squircle, gota) e só a área central ~80% é garantida. Por isso o fundo é de
sangria total e o monograma ocupa só ~58% do lado — em qualquer máscara ele
sobra inteiro.

Saídas (em inventory/static/):
    favicon.ico (16..256)  ·  favicon-16x16.png  ·  favicon-32x32.png
    apple-touch-icon.png (180)  ·  icon-192.png  ·  icon-512.png

Uso:  .venv\\Scripts\\python.exe inventory/static/gerar_favicon.py
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
MARCA = HERE / "logos" / "is2.png"

BANDA = (138, 47, 47)      # --band  #8a2f2f
BANDA_2 = (116, 39, 39)    # --band-2 #742727
PROPORCAO = 0.58           # lado do monograma sobre o lado do ícone


def icone(lado: int) -> Image.Image:
    """Fundo vermelho em degradê vertical + monograma branco centralizado."""
    img = Image.new("RGBA", (lado, lado), BANDA + (255,))
    px = img.load()
    for y in range(lado):
        t = y / max(1, lado - 1)
        cor = tuple(round(a + (b - a) * t) for a, b in zip(BANDA, BANDA_2)) + (255,)
        for x in range(lado):
            px[x, y] = cor

    marca = Image.open(MARCA).convert("RGBA")
    alvo = round(lado * PROPORCAO)
    esc = alvo / marca.height
    marca = marca.resize((max(1, round(marca.width * esc)), alvo), Image.LANCZOS)
    img.alpha_composite(marca, ((lado - marca.width) // 2, (lado - marca.height) // 2))
    return img


def main():
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    pngs = {s: icone(s) for s in ico_sizes}

    pngs[256].save(HERE / "favicon.ico", format="ICO",
                   sizes=[(s, s) for s in ico_sizes])
    pngs[16].save(HERE / "favicon-16x16.png")
    pngs[32].save(HERE / "favicon-32x32.png")

    for lado, nome in ((180, "apple-touch-icon.png"), (192, "icon-192.png"),
                       (512, "icon-512.png")):
        icone(lado).save(HERE / nome, optimize=True)

    print("Ícones gerados a partir de", MARCA.name)


if __name__ == "__main__":
    main()
