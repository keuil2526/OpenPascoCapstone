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


def fft(p):
    p.setPen(_pen("#cfd8dc", 2))
    p.drawLine(7, 34, 35, 34)
    p.setPen(_pen("#66bb6a", 3))
    for x, h in ((11, 12), (17, 26), (23, 8), (29, 16)):
        p.drawLine(x, 34, x, 34 - h)


def histogram(p):
    p.setPen(_pen("#cfd8dc", 2))
    p.drawLine(7, 34, 35, 34)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ef5350"))
    for x, h in ((9, 8), (15, 18), (21, 26), (27, 12)):
        p.drawRect(QRectF(x, 34 - h, 5, h))


def bar_meter(p):
    p.setPen(_pen("#cfd8dc", 2))
    p.drawRect(QRectF(13, 6, 14, 28))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#42a5f5"))
    p.drawRect(QRectF(14, 20, 12, 13))


def copy(p):
    p.setPen(_pen("#cfd8dc", 2))
    p.setBrush(QColor("#455a64"))
    p.drawRect(QRectF(7, 7, 16, 20))
    p.setBrush(QColor("#eceff1"))
    p.drawRect(QRectF(15, 14, 16, 20))


def fit(p):
    p.setPen(_pen("#42a5f5", 2.5))
    for a, b, c, d in ((8, 14, 8, 8), (8, 8, 14, 8), (32, 8, 26, 8), (32, 8, 32, 14),
                       (8, 26, 8, 32), (8, 32, 14, 32), (32, 26, 32, 32), (32, 32, 26, 32)):
        p.drawLine(a, b, c, d)
    p.setPen(_pen("#cfd8dc", 2))
    p.drawLine(15, 25, 20, 17)
    p.drawLine(20, 17, 25, 23)


def grid(p):
    p.setPen(_pen("#90a4ae", 2))
    for v in (12, 20, 28):
        p.drawLine(v, 8, v, 32)
        p.drawLine(8, v, 32, v)


def coord(p):
    p.setPen(_pen("#cfd8dc", 2))
    p.drawLine(20, 6, 20, 34)
    p.drawLine(6, 20, 34, 20)
    p.setPen(_pen("#42a5f5", 2.5))
    p.drawRect(QRectF(15, 15, 10, 10))


def note(p):
    p.setPen(_pen("#42a5f5", 2))
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(7, 9, 26, 16))
    p.setPen(_pen("#42a5f5", 2))
    p.drawLine(16, 25, 12, 33)


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
    p.setBrush(QColor("#c4c4c4"))  # Capstone's record button is a grey sphere
    p.drawEllipse(QRectF(5, 5, 30, 30))
    p.setBrush(QColor("#e53935"))
    p.drawEllipse(QRectF(14, 14, 12, 12))


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


def new_doc(p):  # cream page with a folded corner (colourful toolbar icons, like Capstone's)
    p.setPen(_pen("#8a7a55", 2))
    p.setBrush(QColor("#fff3c4"))
    p.drawPolygon(QPolygonF([QPointF(9, 4), QPointF(26, 4), QPointF(33, 11), QPointF(33, 36), QPointF(9, 36)]))
    p.setBrush(QColor("#e6d28a"))
    p.drawPolygon(QPolygonF([QPointF(26, 4), QPointF(26, 11), QPointF(33, 11)]))


def open_folder(p):
    p.setPen(_pen("#b07d12", 2))
    p.setBrush(QColor("#f5b733"))
    p.drawPolygon(QPolygonF([QPointF(4, 10), QPointF(15, 10), QPointF(18, 14), QPointF(34, 14),
                             QPointF(34, 33), QPointF(4, 33)]))
    p.setBrush(QColor("#ffd36b"))
    p.drawPolygon(QPolygonF([QPointF(4, 33), QPointF(10, 19), QPointF(38, 19), QPointF(34, 33)]))


def save_disk(p):
    p.setPen(_pen("#1b3f73", 2))
    p.setBrush(QColor("#3a73c6"))
    p.drawRoundedRect(QRectF(6, 5, 28, 30), 3, 3)
    p.setBrush(QColor("#f2f2f2"))
    p.drawRect(QRectF(11, 5, 17, 11))
    p.setBrush(QColor("#1b3f73"))
    p.drawRect(QRectF(11, 23, 18, 12))


def add_page(p):
    new_doc(p)
    p.setPen(_pen("#2e9d3b", 4))
    p.drawLine(28, 24, 38, 24)
    p.drawLine(33, 19, 33, 29)


_DRAW = {f.__name__: f for f in (graph, fit, grid, coord, note, copy, bar_meter, fft, histogram, table, digits, meter, hardware, summary, calculator, record, stop, clock, trash, overlay, span, new_doc, open_folder, save_disk, add_page)}


def icon(name: str) -> QIcon:
    return _icon(_DRAW[name])
