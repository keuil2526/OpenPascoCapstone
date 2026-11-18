"""Small icons drawn in code (original artwork, no image files)."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF

SIZE = 40
SCALE = 2


def _icon(draw) -> QIcon:
    pm = QPixmap(SIZE * SCALE, SIZE * SCALE)  # drawn at 2x so 125%/150% screens stay sharp
    pm.setDevicePixelRatio(SCALE)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw(p)
    p.end()
    return QIcon(pm)


def _pen(color, w=2.5):
    return QPen(QColor(color), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def graph(p):
    p.setPen(_pen("#cfd8dc", 2))
    p.drawLine(7, 5, 7, 34)
    p.drawLine(7, 34, 35, 34)
    p.setPen(_pen("#ef5350", 3))
    p.drawPolyline(QPolygonF([QPointF(9, 28), QPointF(16, 14), QPointF(23, 24), QPointF(31, 8)]))


def table(p):
    p.setPen(_pen("#cfd8dc", 2))
    p.drawRect(QRectF(5, 7, 30, 26))
    for y in (15, 24):
        p.drawLine(5, y, 35, y)
    p.drawLine(18, 7, 18, 33)
    p.fillRect(QRectF(6, 8, 29, 6), QColor("#5c8dd6"))


def digits(p):
    p.setPen(_pen("#e8e8e8", 1))
    f = QFont("monospace")
    f.setStyleHint(QFont.Monospace)
    f.setBold(True)
    f.setPixelSize(15)
    p.setFont(f)
    p.drawText(QRectF(2, 8, 36, 24), Qt.AlignCenter, "1.23")


def meter(p):
    c = QPointF(20, 24)
    p.setPen(_pen("#cfd8dc", 2.5))
    p.drawArc(QRectF(6, 10, 28, 28), 30 * 16, 120 * 16)
    p.setPen(_pen("#ef5350", 3))
    a = math.radians(60)
    p.drawLine(c, QPointF(20 + 13 * math.cos(a), 24 - 13 * math.sin(a)))


def hardware(p):
    p.setPen(_pen("#cfd8dc", 2))
    p.setBrush(QColor("#37474f"))
    p.drawRect(QRectF(10, 10, 20, 20))
    for i in (15, 20, 25):
        p.drawLine(i, 5, i, 10)
        p.drawLine(i, 30, i, 35)
        p.drawLine(5, i, 10, i)
        p.drawLine(30, i, 35, i)
    p.setPen(_pen("#66bb6a", 3))
    p.drawPoint(20, 20)


def summary(p):
    p.setPen(_pen("#cfd8dc", 2))
    for i, y in enumerate((10, 20, 30)):
        p.drawLine(8, y, 12, y)
        p.drawLine(16, y, 33 - i * 5, y)


def calculator(p):
    p.setPen(_pen("#cfd8dc", 2))
    p.setBrush(QColor("#37474f"))
    p.drawRoundedRect(QRectF(8, 4, 24, 32), 3, 3)
    p.fillRect(QRectF(11, 8, 18, 7), QColor("#a5d6a7"))
    p.setPen(_pen("#cfd8dc", 3))
    for y in (21, 27, 33):
        for x in (13, 20, 27):
            p.drawPoint(x, y - 2)


def record(p):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#e53935"))
    p.drawEllipse(QRectF(8, 8, 24, 24))


def clock(p):
    p.setPen(_pen("#cfd8dc", 2.5))
    p.drawEllipse(QRectF(7, 7, 26, 26))
    p.setPen(_pen("#ffd54f", 2.5))
    p.drawLine(20, 20, 20, 12)
    p.drawLine(20, 20, 26, 23)


def trash(p):
    p.setPen(_pen("#cfd8dc", 2.5))
    p.drawLine(9, 11, 31, 11)
    p.drawLine(16, 11, 16, 7)
    p.drawLine(16, 7, 24, 7)
    p.drawLine(24, 7, 24, 11)
    p.drawPolyline(QPolygonF([QPointF(11, 11), QPointF(13, 33), QPointF(27, 33), QPointF(29, 11)]))
    p.setPen(_pen("#ef5350", 2.5))
    p.drawLine(18, 17, 22, 27)
    p.drawLine(22, 17, 18, 27)


def stop(p):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#eeeeee"))
    p.drawRoundedRect(QRectF(10, 10, 20, 20), 3, 3)


def overlay(p):  # stacked runs (dark strokes: used on the light graph toolbar)
    for i, c in enumerate(("#9fb4e8", "#e8a09f", "#1f2bff")):
        p.setPen(_pen(c, 3))
        y = 10 + 7 * i
        p.drawPolyline(QPolygonF([QPointF(5, y + 10), QPointF(14, y), QPointF(24, y + 8), QPointF(35, y - 2)]))


def span(p):  # selected x range
    p.fillRect(QRectF(12, 6, 16, 28), QColor(42, 130, 218, 90))
    p.setPen(_pen("#2a82da", 3))
    p.drawLine(12, 5, 12, 35)
    p.drawLine(28, 5, 28, 35)
    p.setPen(_pen("#555555", 2))
    p.drawLine(4, 35, 36, 35)


_DRAW = {f.__name__: f for f in (graph, table, digits, meter, hardware, summary, calculator, record, stop, clock, trash, overlay, span)}


def icon(name: str) -> QIcon:
    return _icon(_DRAW[name])
