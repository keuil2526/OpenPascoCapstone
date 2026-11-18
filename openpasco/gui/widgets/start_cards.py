"""Start page shown on an empty page: large cards for the ways to begin (layout inspired by Capstone's
welcome page; only actions OpenPASCO really has). Pictures are drawn in code."""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QGridLayout, QToolButton, QWidget

W, H, SCALE = 150, 100, 2
BLUE, GREY = QColor("#1565c0"), QColor("#777777")


def _pen(c, w=2.0):
    return QPen(QColor(c), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def _axes(p, x0, y0, x1, y1):
    p.setPen(_pen(GREY, 2.5))
    p.drawLine(x0, y0, x0, y1)
    p.drawLine(x0, y1, x1, y1)


def _sensor(p):
    _axes(p, 40, 12, 140, 88)
    pts = [QPointF(52, 74), QPointF(72, 48), QPointF(92, 62), QPointF(126, 24)]
    p.setPen(_pen(BLUE, 2.5))
    p.drawPolyline(QPolygonF(pts))
    p.setBrush(BLUE)
    for q in pts:
        p.drawEllipse(q, 5, 5)
    p.setPen(_pen(GREY, 2.5))  # sensor body
    p.setBrush(QColor("#f5f5f5"))
    p.drawRoundedRect(QRectF(8, 14, 22, 34), 4, 4)
    p.drawLine(19, 48, 19, 62)
    p.drawRect(QRectF(11, 62, 16, 14))


def _templates(p):
    p.setPen(_pen(GREY, 2))
    p.drawLine(75, 8, 75, 92)
    p.drawLine(18, 50, 132, 50)
    p.setPen(_pen(BLUE, 2.5))
    p.drawPolyline(QPolygonF([QPointF(24, 40), QPointF(36, 22), QPointF(48, 32), QPointF(64, 12)]))
    p.setPen(_pen(GREY, 1.5))  # table
    p.drawRect(QRectF(88, 12, 38, 28))
    p.drawLine(88, 22, 126, 22)
    p.drawLine(88, 31, 126, 31)
    p.drawLine(107, 12, 107, 40)
    p.setPen(_pen(BLUE, 3))  # meter
    p.drawArc(QRectF(26, 56, 38, 38), 0, 180 * 16)
    p.drawLine(45, 76, 54, 62)
    p.setPen(Qt.NoPen)  # bars
    p.setBrush(BLUE)
    for i, h in enumerate((14, 26, 18)):
        p.drawRect(QRectF(90 + i * 12, 90 - h, 9, h))


def _open(p):
    p.setPen(_pen(GREY, 2.5))
    p.setBrush(QColor("#f0c14b"))
    p.drawRoundedRect(QRectF(30, 30, 90, 52), 5, 5)
    p.drawPolygon(QPolygonF([QPointF(30, 30), QPointF(30, 22), QPointF(58, 22), QPointF(66, 30)]))


def _pixmap(draw) -> QIcon:
    pm = QPixmap(W * SCALE, H * SCALE)
    pm.setDevicePixelRatio(SCALE)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw(p)
    p.end()
    return QIcon(pm)


CARDS = [("sensor", "센서 데이터", _sensor, "그래프와 표를 놓고 센서를 검색합니다"),
         ("templates", "템플릿", _templates, "자주 쓰는 디스플레이 배치로 시작합니다"),
         ("open", "열기", _open, "저장한 실험이나 Capstone(.cap) 파일을 엽니다")]


class StartCards(QWidget):
    chosen = Signal(str, QWidget)  # card id, the card button (menus open next to it)

    def __init__(self):
        super().__init__()
        grid = QGridLayout(self)
        grid.setSpacing(24)
        grid.setContentsMargins(30, 30, 30, 30)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(len(CARDS) + 1, 1)
        for i, (cid, title, draw, tip) in enumerate(CARDS):
            b = QToolButton(objectName="start_card", text=title, toolTip=tip)
            b.setIcon(_pixmap(draw))
            b.setIconSize(QSize(W, H))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.clicked.connect(lambda _=False, c=cid, btn=b: self.chosen.emit(c, btn))
            grid.addWidget(b, 1, i + 1)
