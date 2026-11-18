"""Display widgets placed on an experiment page (Graph, Table, Digits, Meter).

Phase 2: empty shells only. Data binding arrives with the data engine (Phase 2b)
and full features in Phase 3.
"""
import math

import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication, QFrame, QLabel, QTableWidget, QToolButton, QVBoxLayout, QHBoxLayout, QWidget,
)


class DisplayFrame(QFrame):
    """Titled frame with a close button that wraps one display."""

    closed = Signal(QWidget)

    def __init__(self, title: str, body: QWidget):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        header = QHBoxLayout()
        header.setContentsMargins(6, 2, 2, 2)
        header.addWidget(QLabel(f"<b>{title}</b>"))
        header.addStretch()
        close = QToolButton(text="✕", autoRaise=True, toolTip="디스플레이 닫기")
        close.clicked.connect(lambda: self.closed.emit(self))
        header.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(header)
        layout.addWidget(body, 1)
        self.body = body


def style_plot(plot: pg.PlotWidget):
    """Match plot colours to the current application palette (light/dark)."""
    pal = QApplication.palette()  # widget palette updates lazily after app.setPalette()
    plot.setBackground(pal.color(QPalette.Base))
    fg = pal.color(QPalette.Text)
    for name in ("left", "bottom"):
        axis = plot.getAxis(name)
        axis.setPen(fg)
        axis.setTextPen(fg)


def make_graph() -> QWidget:
    plot = pg.PlotWidget()
    style_plot(plot)
    plot.showGrid(x=True, y=True, alpha=0.3)
    plot.setLabel("bottom", "시간", units="s")
    plot.setLabel("left", "측정값 선택")
    return plot


def make_table() -> QWidget:
    table = QTableWidget(0, 2)
    table.setHorizontalHeaderLabels(["시간 (s)", "측정값 선택"])
    table.horizontalHeader().setStretchLastSection(True)
    return table


def make_digits() -> QWidget:
    label = QLabel("— — —", alignment=Qt.AlignCenter)
    font = QFont()
    font.setPointSize(40)
    font.setBold(True)
    label.setFont(font)
    return label


class Meter(QWidget):
    """Analog gauge: 240° arc with ticks, needle and value readout. value=None draws no needle."""

    SWEEP = 240  # degrees, centred on 12 o'clock
    TICKS = 10

    def __init__(self, minimum=0.0, maximum=10.0, unit=""):
        super().__init__()
        self.minimum, self.maximum, self.unit = minimum, maximum, unit
        self.value = None
        self.setMinimumSize(160, 140)

    def set_value(self, value):
        self.value = value
        self.update()

    def _angle(self, v):
        """Qt angle in degrees (0 = 3 o'clock, counter-clockwise) for value v, clamped to range."""
        frac = (min(max(v, self.minimum), self.maximum) - self.minimum) / (self.maximum - self.minimum)
        return 90 + self.SWEEP / 2 - frac * self.SWEEP

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fg = self.palette().color(QPalette.WindowText)
        side = min(self.width(), self.height() * 1.15)
        r = side * 0.42
        c = QPointF(self.width() / 2, self.height() * 0.55)

        p.setPen(QPen(fg, 3))
        p.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r),
                  int(self._angle(self.maximum) * 16), int(self.SWEEP * 16))

        font = p.font()
        font.setPointSizeF(max(7.0, r / 10))
        p.setFont(font)
        for i in range(self.TICKS + 1):
            v = self.minimum + (self.maximum - self.minimum) * i / self.TICKS
            a = math.radians(self._angle(v))
            d = QPointF(math.cos(a), -math.sin(a))
            p.setPen(QPen(fg, 2))
            p.drawLine(c + d * r, c + d * (r * 0.88))
            label_pos = c + d * (r * 0.72)
            p.drawText(QRectF(label_pos.x() - 25, label_pos.y() - 10, 50, 20), Qt.AlignCenter, f"{v:g}")

        text = "—" if self.value is None else f"{self.value:.3g} {self.unit}".strip()
        p.drawText(QRectF(c.x() - r, c.y() + r * 0.25, 2 * r, r * 0.4), Qt.AlignCenter, text)

        if self.value is not None:
            a = math.radians(self._angle(self.value))
            p.setPen(QPen(QColor("#c62828"), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(c, c + QPointF(math.cos(a), -math.sin(a)) * (r * 0.85))
        p.setBrush(fg)
        p.drawEllipse(c, 4, 4)


def make_meter() -> QWidget:
    return Meter()


DISPLAY_TYPES = {
    "그래프": make_graph,
    "테이블": make_table,
    "숫자": make_digits,
    "미터": make_meter,
}
