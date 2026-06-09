"""
Gera os ícones do InvenSync a partir de inventory/static/favicon.svg.

Saídas (em inventory/static/):
    favicon.ico (16..256)  ·  favicon-16x16.png  ·  favicon-32x32.png
    apple-touch-icon.png (180)

Uso:  python inventory/static/gerar_favicon.py
"""
import io
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QByteArray, QBuffer, QIODevice
from PyQt5.QtGui import QImage, QPainter, QGuiApplication
from PyQt5.QtSvg import QSvgRenderer
from PIL import Image

HERE = Path(__file__).resolve().parent
SVG = HERE / "favicon.svg"


def render_png(size: int) -> Image.Image:
    renderer = QSvgRenderer(QByteArray(SVG.read_bytes()))
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(p)
    p.end()
    buf = QByteArray()
    qbuf = QBuffer(buf)
    qbuf.open(QIODevice.WriteOnly)
    img.save(qbuf, "PNG")
    qbuf.close()
    return Image.open(io.BytesIO(buf.data())).convert("RGBA")


def main():
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    pngs = {s: render_png(s) for s in ico_sizes}

    # favicon.ico multi-resolução
    pngs[256].save(HERE / "favicon.ico", format="ICO",
                   sizes=[(s, s) for s in ico_sizes])
    # PNGs referenciados no base.html
    pngs[16].save(HERE / "favicon-16x16.png")
    pngs[32].save(HERE / "favicon-32x32.png")
    render_png(180).save(HERE / "apple-touch-icon.png")

    print("Ícones gerados:", ", ".join(
        f.name for f in HERE.glob("favicon*") if f.is_file()))


if __name__ == "__main__":
    main()
