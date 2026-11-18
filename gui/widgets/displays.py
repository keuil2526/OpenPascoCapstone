"""Display widgets placed on an experiment page (Graph, Table, Digits, Meter).

Each display implements show(measurement, data) where data is (t, y) arrays or None.
DisplayFrame owns the measurement selector and pulls data from the DataManager.
"""
import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QTableView, QToolButton,
    QVBoxLayout, QWidget,
)

from hardware.base import Measurement


class DisplayFrame(QFrame):
    """Titled frame: measurement selector, close button, and one display body."""

    closed = Signal(QWidget)

    def __init__(self, title: str, body: QWidget):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.body = body
        self.measurements: dict[str, Measurement] = {}

        header = QHBoxLayout()
        header.setContentsMargins(6, 2, 2, 2)
        header.addWidget(QLabel(f"<b>{title}</b>"))
        self.selector = QComboBox(toolTip="표시할 측정값")
        self.selector.setPlaceholderText("측정값 선택")
        self.selector.setMinimumContentsLength(12)
        self.selector.currentIndexChanged.connect(lambda _: self.body.show(self.measurement, None))
        header.addWidget(self.selector)
        header.addStretch()
        close = QToolButton(text="✕", autoRaise=True, toolTip="디스플레이 닫기")
        close.clicked.connect(lambda: self.closed.emit(self))
        header.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(header)
        layout.addWidget(body, 1)

    @property
    def key(self) -> str | None:
        return self.selector.currentData()

    @property
    def measurement(self) -> Measurement | None:
        return self.measurements.get(self.key)

    def set_measurements(self, items: dict[str, tuple[str, Measurement]]):
        """items: key -> (sensor name, measurement). Keeps the selection if still available."""
        keep = self.key
        self.measurements = {k: m for k, (_, m) in items.items()}
        self.selector.blockSignals(True)
        self.selector.clear()
        for k, (sensor, m) in items.items():
            self.selector.addItem(f"{m.label} — {sensor}", k)
        idx = self.selector.findData(keep)
        self.selector.setCurrentIndex(idx if idx >= 0 else (0 if items else -1))
        self.selector.blockSignals(False)
        self.body.show(self.measurement, None)

    def refresh(self, data_manager):
        if self.key is not None:
            self.body.show(self.measurement, data_manager.latest(self.key))


def style_plot(plot: pg.PlotWidget):
    """Match plot colours to the current application palette (light/dark)."""
    pal = QApplication.palette()  # widget palette updates lazily after app.setPalette()
    plot.setBackground(pal.color(QPalette.Base))
    fg = pal.color(QPalette.Text)
    for name in ("left", "bottom"):
        axis = plot.getAxis(name)
        axis.setPen(fg)
        axis.setTextPen(fg)


class GraphDisplay(pg.PlotWidget):
    def __init__(self):
        super().__init__()
        style_plot(self)
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setLabel("bottom", "시간", units="s")
        self.setLabel("left", "측정값 선택")
        self.setDownsampling(auto=True, mode="peak")  # long runs stay fast
        self.setClipToView(True)
        self.curve = self.plot(pen=pg.mkPen("#2a82da", width=2))

    def show(self, meas, data):
        if meas:
            self.setLabel("left", meas.name, units=meas.unit)
        if data is None:
            self.curve.setData([], [])
        else:
            self.curve.setData(*data)


class ArrayModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self.t = self.y = np.empty(0)
        self.headers = ["시간 (s)", "측정값"]

    def set_data(self, t, y):
        old = len(self.t)
        if len(t) > old > 0 or (old == 0 and len(t) > 0):
            self.beginInsertRows(QModelIndex(), old, len(t) - 1)
            self.t, self.y = t, y
            self.endInsertRows()
        elif len(t) < old:  # new run or cleared
            self.beginResetModel()
            self.t, self.y = t, y
            self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.t)

    def columnCount(self, parent=QModelIndex()):
        return 2

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            arr = self.t if index.column() == 0 else self.y
            return f"{arr[index.row()]:.4g}"
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return super().headerData(section, orientation, role)


class TableDisplay(QTableView):
    def __init__(self):
        super().__init__()
        self.model_ = ArrayModel()
        self.setModel(self.model_)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setDefaultSectionSize(20)

    def show(self, meas, data):
        if meas and self.model_.headers[1] != meas.label:
            self.model_.headers[1] = meas.label
            self.model_.headerDataChanged.emit(Qt.Horizontal, 1, 1)
        follow = self.verticalScrollBar().value() == self.verticalScrollBar().maximum()
        t, y = data if data is not None else (np.empty(0), np.empty(0))
        self.model_.set_data(t, y)
        if follow:
            self.scrollToBottom()


class DigitsDisplay(QWidget):
    def __init__(self):
        super().__init__()
        self.value = QLabel("— — —", alignment=Qt.AlignCenter)
        font = QFont()
        font.setPointSize(40)
        font.setBold(True)
        self.value.setFont(font)
        self.caption = QLabel("", alignment=Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self.value)
        layout.addWidget(self.caption)
        layout.addStretch()

    def show(self, meas, data):
        self.caption.setText(meas.label if meas else "")
        if data is None or len(data[1]) == 0:
            self.value.setText("— — —")
        else:
            self.value.setText(f"{data[1][-1]:.4g}")


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


class MeterDisplay(Meter):
    def show(self, meas, data):
        if meas:
            self.minimum, self.maximum, self.unit = meas.minimum, meas.maximum, meas.unit
        self.set_value(None if data is None or len(data[1]) == 0 else float(data[1][-1]))


DISPLAY_TYPES = {
    "그래프": GraphDisplay,
    "테이블": TableDisplay,
    "숫자": DigitsDisplay,
    "미터": MeterDisplay,
}
