"""Regenerate the Windows application icon.

Run with the project venv:  python packaging/windows/make_icon.py

The generated .ico is committed, so this only needs re-running if the artwork
changes. A real icon matters beyond looks: unsigned executables carrying no
version resources and no icon are exactly what antivirus heuristics score as
suspicious, so shipping proper resources measurably reduces false positives.
"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygonF,
)

ICON_SIZES = (16, 32, 48, 64, 128, 256)
OUTPUT = Path(__file__).with_name("AlcoholTracker.ico")

BACKGROUND_TOP = QColor("#22262d")
BACKGROUND_BOTTOM = QColor("#15171a")
GLASS_EDGE = QColor("#e2e6ec")
LIQUID_TOP = QColor("#e0ab1f")
LIQUID_BOTTOM = QColor("#b07f00")


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    scale = size / 256.0
    painter.scale(scale, scale)

    backdrop = QLinearGradient(0, 0, 0, 256)
    backdrop.setColorAt(0.0, BACKGROUND_TOP)
    backdrop.setColorAt(1.0, BACKGROUND_BOTTOM)
    painter.setBrush(QBrush(backdrop))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(4, 4, 248, 248), 52, 52)

    # Tumbler: a slightly tapered glass, filled two-thirds with spirit.
    glass_top, glass_bottom = 62.0, 206.0
    half_top, half_bottom = 62.0, 50.0
    centre = 128.0
    liquid_top = glass_top + (glass_bottom - glass_top) * 0.34

    def half_width_at(y: float) -> float:
        ratio = (y - glass_top) / (glass_bottom - glass_top)
        return half_top + (half_bottom - half_top) * ratio

    liquid = QLinearGradient(0, liquid_top, 0, glass_bottom)
    liquid.setColorAt(0.0, LIQUID_TOP)
    liquid.setColorAt(1.0, LIQUID_BOTTOM)
    painter.setBrush(QBrush(liquid))
    top_half = half_width_at(liquid_top)
    painter.drawPolygon(
        QPolygonF(
            [
                QPointF(centre - top_half, liquid_top),
                QPointF(centre + top_half, liquid_top),
                QPointF(centre + half_bottom, glass_bottom),
                QPointF(centre - half_bottom, glass_bottom),
            ]
        )
    )

    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(GLASS_EDGE, 11, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPolyline(
        QPolygonF(
            [
                QPointF(centre - half_top, glass_top),
                QPointF(centre - half_bottom, glass_bottom),
                QPointF(centre + half_bottom, glass_bottom),
                QPointF(centre + half_top, glass_top),
            ]
        )
    )
    painter.drawLine(
        QPointF(centre - half_top, glass_top), QPointF(centre + half_top, glass_top)
    )

    # Tick marks on the glass read as "measured", which is what the app is for.
    # They vanish at small sizes where they would only turn into mush.
    if size >= 48:
        painter.setPen(QPen(QColor(255, 255, 255, 150), 7, Qt.SolidLine, Qt.RoundCap))
        for fraction in (0.52, 0.68):
            y = glass_top + (glass_bottom - glass_top) * fraction
            painter.drawLine(QPointF(centre + 8, y), QPointF(centre + half_width_at(y) - 16, y))

    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    # `storage` must outlive the buffer; QBuffer does not take ownership of it.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def build_ico(path: Path) -> None:
    frames = [png_bytes(render(size)) for size in ICON_SIZES]

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)
    entries, payload = bytearray(), bytearray()
    for size, data in zip(ICON_SIZES, frames):
        # 256 is stored as 0 in the directory entry.
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset
        )
        payload += data
        offset += len(data)

    path.write_bytes(header + bytes(entries) + bytes(payload))


if __name__ == "__main__":
    from PySide6.QtGui import QGuiApplication

    QGuiApplication([])
    build_ico(OUTPUT)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes, sizes: {ICON_SIZES})")
