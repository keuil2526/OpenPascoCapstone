"""Display widgets placed on an experiment page (Graph, Table, Digits, Meter).

Each display implements show(measurement, data) where data is (t, y) arrays or None.
DisplayFrame owns the measurement selector and pulls data from the DataManager.
"""
import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QTableView, QToolButton,
    QVBoxLayout, QWidget,
)

from openpasco.analysis.numeric import MODELS, derivative, fit, integral, select, statistics
from openpasco.hardware.base import Measurement


class DisplayFrame(QFrame):
    """Titled frame: measurement selector, close button, and one display body."""

    closed = Signal(QWidget)

    def __init__(self, title: str, body: QWidget):
        super().__init__()
        self.setObjectName("display_frame")
        self.setFrameShape(QFrame.StyledPanel)
        self.body = body
        self.kind = title
        self._older_sig = None
        self._dm = None
        if hasattr(body, "older_toggled"):
            body.older_toggled.connect(self._older_toggled)
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

    def _older_toggled(self):
        self._older_sig = None
        if self._dm is not None:
            self.refresh(self._dm)

    def refresh(self, data_manager):
        self._dm = data_manager
        if self.key is None:
            return
        self.body.show(self.measurement, data_manager.latest(self.key))
        if getattr(self.body, "wants_older", False):
            # older runs never change while recording: refetch only when the run set or selection changes
            sig = (self.key, tuple(id(r) for r in data_manager.runs))
            if sig != self._older_sig:
                self._older_sig = sig
                self.body.show_older(data_manager.older_runs(self.key))
        elif hasattr(self.body, "show_older"):
            self._older_sig = None
            self.body.show_older([])


def style_plot(plot: pg.PlotWidget):
    """Match plot colours to the current application palette (light/dark)."""
    pal = QApplication.palette()  # widget palette updates lazily after app.setPalette()
    plot.setBackground(pal.color(QPalette.Base))
    fg = pal.color(QPalette.Text)
    for name in ("left", "bottom"):
        axis = plot.getAxis(name)
        axis.setPen(fg)
        axis.setTextPen(fg)


class GraphDisplay(QWidget):
    """Plot with optional range selection and analysis (stats, fits, derivative, integral)."""

    older_toggled = Signal()  # DisplayFrame reacts by refetching data
    ANALYSES = ["분석 없음", "통계", *MODELS, "미분", "적분"]
    DEBOUNCE_MS = 400  # analysis runs at most this often while data streams in

    def __init__(self):
        super().__init__()
        self.plot = pg.PlotWidget()
        style_plot(self.plot)
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel("bottom", "시간", units="s")
        self.plot.setLabel("left", "측정값 선택")
        self.plot.setDownsampling(auto=True, mode="peak")  # long runs stay fast
        self.plot.setClipToView(True)
        self.curve = self.plot.plot(pen=pg.mkPen("#2a82da", width=2))
        self.overlay = self.plot.plot(pen=pg.mkPen("#c62828", width=2, style=Qt.DashLine))
        self.region = pg.LinearRegionItem(movable=True)
        self.region.setVisible(False)
        self.plot.addItem(self.region)

        self.legend = self.plot.addLegend(offset=(-10, 10))
        self.older: list[pg.PlotDataItem] = []
        self.older_names: list[str] = []
        self.older_check = QCheckBox("이전 런 겹쳐보기")
        self.range_check = QCheckBox("구간 선택")
        self.analysis = QComboBox()
        self.analysis.addItems(self.ANALYSES)
        self.result = QLabel("", wordWrap=True, textInteractionFlags=Qt.TextSelectableByMouse)
        bar = QHBoxLayout()
        bar.addWidget(self.older_check)
        bar.addWidget(self.range_check)
        bar.addWidget(self.analysis)
        bar.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.plot, 1)
        layout.addWidget(self.result)

        self.meas: Measurement | None = None
        self.data = None
        self.timer = QTimer(self, singleShot=True, interval=self.DEBOUNCE_MS, timeout=self._analyze)
        self.range_check.toggled.connect(self._range_toggled)
        self.older_check.toggled.connect(lambda _: self.older_toggled.emit())
        self.region.sigRegionChanged.connect(self._schedule)
        self.analysis.currentIndexChanged.connect(lambda _: self._analyze())

    @property
    def wants_older(self) -> bool:
        return self.older_check.isChecked()

    def show_older(self, runs):
        """runs: [(run number, t, y)] drawn faded behind the newest run (analysis uses the newest only)."""
        for item in self.older:
            self.plot.removeItem(item)
        self.older = []
        names = [f"런 #{n}" for n, _, _ in runs]
        if names != self.older_names:  # rebuild the legend only when the run set changed
            self.legend.clear()
            self.older_names = names
            rebuild = True
        else:
            rebuild = False
        for i, (n, t, y) in enumerate(runs):
            item = self.plot.plot(t, y, pen=pg.mkPen(pg.intColor(i, hues=9, alpha=170), width=1.5))
            self.older.append(item)
            if rebuild:
                self.legend.addItem(item, names[i])
        if rebuild and runs:
            self.legend.addItem(self.curve, "최신 런")

    def _range_toggled(self, on):
        self.region.setVisible(on)
        if on and self.data is not None and len(self.data[0]) > 1:
            t = self.data[0]
            self.region.setRegion((t[0] + 0.2 * (t[-1] - t[0]), t[0] + 0.8 * (t[-1] - t[0])))
        self._analyze()

    def _schedule(self):
        if not self.timer.isActive():
            self.timer.start()

    def show(self, meas, data):
        self.meas, self.data = meas, data
        if data is None or len(data[0]) == 0:
            self.curve.setData([], [])
            self.overlay.setData([], [])
            self.result.setText("")
            self._set_ylabel(None)
        elif self.analysis.currentText() in ("미분", "적분"):
            self._schedule()  # derived curve replaces the raw one in _analyze
        else:
            self.curve.setData(*data)
            self._set_ylabel(None)
            if self.analysis.currentIndex() > 0:
                self._schedule()

    def _set_ylabel(self, derived):
        if self.meas is None:
            return
        name, unit = self.meas.name, self.meas.unit
        if derived == "미분":
            name, unit = f"d{name}/dt", f"{unit}/s"
        elif derived == "적분":
            name, unit = f"∫{name}dt", f"{unit}·s"
        self.plot.getAxis("left").enableAutoSIPrefix(bool(unit))  # no "(x0.001)" for unitless data
        self.plot.setLabel("left", name, units=unit)

    def _analyze(self):
        self.timer.stop()
        mode = self.analysis.currentText()
        self.overlay.setData([], [])
        if self.data is None or len(self.data[0]) == 0:
            return
        t, y = self.data
        try:
            if mode in ("미분", "적분"):
                d = derivative(t, y) if mode == "미분" else integral(t, y)
                self.curve.setData(t, d)
                self._set_ylabel(mode)
                self.result.setText(f"{mode} 곡선 표시 중 (구간 선택은 무시됨)")
                return
            self.curve.setData(t, y)
            self._set_ylabel(None)
            if self.range_check.isChecked():
                t, y = select(t, y, *self.region.getRegion())
            if mode == "분석 없음":
                self.result.setText("")
            elif mode == "통계":
                s = statistics(t, y)
                self.result.setText(
                    f"n={s.n}  평균={s.mean:.4g}  표준편차={s.std:.4g}  "
                    f"최소={s.minimum:.4g} (t={s.t_min:.3g})  최대={s.maximum:.4g} (t={s.t_max:.3g})")
            else:
                f = fit(mode, t, y)
                self.overlay.setData(t, f.predict(t))
                self.result.setText(f.summary())
        except ValueError as e:  # too few points, no convergence, empty selection
            self.result.setText(str(e))


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
