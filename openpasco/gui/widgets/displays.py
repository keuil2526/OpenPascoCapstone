"""Display widgets placed on an experiment page (Graph, Table, Digits, Meter).

Each display implements show(measurement, data) where data is (t, y) arrays or None.
DisplayFrame owns the measurement selector and pulls data from the DataManager.
"""
import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QTableView, QToolButton,
    QVBoxLayout, QWidget,
)

from openpasco.analysis.numeric import MODELS, auto_analyze, derivative, fit, integral, select, statistics
from openpasco.gui import icons
from openpasco.gui.widgets.annotations import Marks, box_position
from openpasco.hardware.base import Measurement


class DisplayFrame(QFrame):
    """Titled frame: measurement selector, close button, and one display body."""

    closed = Signal(QWidget)

    def __init__(self, title: str, body: QWidget):
        super().__init__()
        self.setObjectName("display_frame")
        self.setFrameShape(QFrame.NoFrame)
        self.body = body
        self.kind = title
        self._older_sig = None
        self._dm = None
        if hasattr(body, "older_toggled"):
            body.older_toggled.connect(self._older_toggled)
        self.measurements: dict[str, Measurement] = {}

        bar = QWidget(objectName="display_bar")
        header = QHBoxLayout(bar)
        header.setContentsMargins(6, 2, 2, 2)
        header.addWidget(QLabel(title))
        self.selector = QComboBox(toolTip="표시할 측정값")
        self.selector.setPlaceholderText("측정값 선택")
        self.selector.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.selector.currentIndexChanged.connect(lambda _: self.body.show(self.measurement, None))
        header.addWidget(self.selector)
        for w in getattr(body, "tool_widgets", lambda: [])():  # display-specific tools share the one strip
            header.addWidget(w)
        header.addStretch()
        close = QToolButton(text="✕", autoRaise=True, toolTip="디스플레이 닫기")
        close.clicked.connect(lambda: self.closed.emit(self))
        header.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar)
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
        axis.setStyle(tickFont=QFont("sans-serif", 11))


class GraphDisplay(QWidget):
    """Plot with optional range selection and analysis (stats, fits, derivative, integral)."""

    older_toggled = Signal()  # DisplayFrame reacts by refetching data
    title_changed = Signal()
    ANALYSES = ["분석 없음", "자동 분석", "통계", "넓이", *MODELS, "미분", "적분"]
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
        for angle in (0, 90):  # Capstone draws the x=0 / y=0 axes as dark lines
            self.plot.addItem(pg.InfiniteLine(angle=angle, pos=0, pen=pg.mkPen("#808080", width=1)), ignoreBounds=True)
        self.curve = self.plot.plot(pen=pg.mkPen("#1f2bff", width=3))  # Capstone draws a heavy line
        self.overlay = self.plot.plot(pen=pg.mkPen("#c62828", width=2, style=Qt.DashLine))
        self.marks = Marks(self.plot)  # analysis drawn on the graph (cleared on every re-analysis)
        self.user_marks = Marks(self.plot)  # coordinate marker and text boxes the user placed
        self.coord_point: tuple[float, float] | None = None
        self.notes: list[dict] = []  # [{"x": t, "text": str}] saved with the experiment
        self.region = pg.LinearRegionItem(movable=True)
        self.region.setVisible(False)
        self.plot.addItem(self.region)

        self.legend = self.plot.addLegend(offset=(-10, 10))
        self.older: list[pg.PlotDataItem] = []
        self.older_names: list[str] | None = None
        def toggle(icon_name, tip):  # icon toggle like Capstone's graph toolbar
            b = QToolButton(icon=icons.icon(icon_name), toolTip=tip, checkable=True, autoRaise=True)
            b.setIconSize(QSize(22, 22))
            b.setObjectName("graph_tool")
            return b

        self.older_check = toggle("overlay", "이전 런 겹쳐보기")
        self.range_check = toggle("span", "구간 선택")
        self.fit_btn = QToolButton(icon=icons.icon("fit"), toolTip="크기 맞춤 (전체 데이터가 보이게)", autoRaise=True,
                                   objectName="graph_tool")
        self.fit_btn.setIconSize(QSize(22, 22))
        self.fit_btn.clicked.connect(self.fit_view)
        self.grid_check = toggle("grid", "격자 보이기/숨기기")
        self.grid_check.setChecked(True)
        self.grid_check.toggled.connect(lambda on: self.plot.showGrid(x=on, y=on, alpha=0.3))
        self.coord_check = toggle("coord", "좌표 도구 — 그래프를 클릭하면 그 점의 값을 표시")
        self.note_check = toggle("note", "텍스트 상자 — 그래프를 클릭하면 그 점에 메모를 답니다")
        self.coord_check.toggled.connect(lambda on: on and self.note_check.setChecked(False))
        self.note_check.toggled.connect(lambda on: on and self.coord_check.setChecked(False))
        self.plot.scene().sigMouseClicked.connect(self._clicked)
        self.analysis = QComboBox()
        self.analysis.addItems(self.ANALYSES)
        self.result = QLabel("", wordWrap=True, textInteractionFlags=Qt.TextSelectableByMouse)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.plot, 1)
        self.title_edit = QLineEdit(placeholderText="[그래프 제목]", objectName="graph_title")  # like Capstone's title line
        self.title_edit.textEdited.connect(lambda _: self.title_changed.emit())
        layout.addWidget(self.title_edit)
        layout.addWidget(self.result)

        self.meas: Measurement | None = None
        self.data = None
        self.timer = QTimer(self, singleShot=True, interval=self.DEBOUNCE_MS, timeout=self._analyze)
        self.range_check.toggled.connect(self._range_toggled)
        self.older_check.toggled.connect(lambda _: self.older_toggled.emit())
        self.region.sigRegionChanged.connect(self._schedule)
        self.analysis.currentIndexChanged.connect(lambda _: self._analyze())

    def fit_view(self):
        """Show all data. Clipping to the view is off meanwhile, or panned-away data would not count."""
        self.plot.setClipToView(False)
        self.plot.enableAutoRange()
        self.plot.autoRange()
        self.plot.setClipToView(True)

    def tool_widgets(self):  # placed by DisplayFrame in its toolbar strip
        return [self.fit_btn, self.grid_check, self.older_check, self.range_check, self.coord_check, self.note_check,
                self.analysis]

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
        if rebuild:
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

    def _marks(self, n: int):
        """Capstone draws a dot on every sample; only while the points are few (drawing many is slow)."""
        self.curve.setSymbol("o" if n <= 300 else None)
        self.curve.setSymbolSize(7)
        self.curve.setSymbolBrush("#1f2bff")
        self.curve.setSymbolPen(None)

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
            self._marks(len(data[0]))
            self._set_ylabel(None)
            if self.coord_point or self.notes:
                self.draw_user_marks()
            if self.analysis.currentIndex() > 0:
                self._schedule()

    def _plain_axis(self):
        """Tick numbers stay in the unit named on the axis (no mm for m), so they match the on-graph labels.
        pyqtgraph still recomputes a prefix scale on every range change, hence the override."""
        ax = self.plot.getAxis("left")
        ax.enableAutoSIPrefix(False)
        ax.updateAutoSIPrefix = lambda: setattr(ax, "autoSIPrefixScale", 1.0)
        ax.autoSIPrefixScale = 1.0

    def _set_ylabel(self, derived):
        if self.meas is None:
            return
        name, unit = self.meas.name, self.meas.unit
        if derived == "미분":
            name, unit = f"d{name}/dt", f"{unit}/s"
        elif derived == "적분":
            name, unit = f"∫{name}dt", f"{unit}·s"
        self._plain_axis()
        self.plot.setLabel("left", name, units=unit)

    def _unit(self):
        return self.meas.unit if self.meas else ""

    def _view(self):
        return self.plot.getPlotItem().vb.viewRange()

    def _draw_stats(self, t, y):
        """Capstone's statistics box: a shaded band over the range with Max / Mean / Min lines and labels."""
        st = statistics(t, y)
        x0, x1 = float(t[0]), float(t[-1])
        self.marks.band(x0, x1, st.minimum, st.maximum)
        self.marks.line([x0, x1], [st.mean, st.mean], style=Qt.DashLine)
        self.marks.label(f"Max.: {st.maximum:.4g}", x0, st.maximum, anchor=(0, 0))
        self.marks.label(f"Mean: {st.mean:.4g}", x0, st.mean, anchor=(0, 0.5))
        self.marks.label(f"Min.: {st.minimum:.4g}", x0, st.minimum, anchor=(0, 1))
        return st

    def _draw_area(self, t, y):
        area = float(np.trapezoid(y, t)) if len(t) > 1 else 0.0
        self.marks.area(t, y)
        mid = len(t) // 2
        point = (float(t[mid]), float(y[mid]))
        unit = f"{self._unit()}·s" if self._unit() else "s"
        self.marks.callout(f"Area: {area:.4g} {unit}", point, box_position(self._view(), point))
        return area

    def _analyze(self):
        self.timer.stop()
        mode = self.analysis.currentText()
        self.overlay.setData([], [])
        self.marks.clear()
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
                if mode != "분석 없음" and len(t) > 1:  # Capstone highlights the analysed part of the curve
                    self.marks.line(t, y, width=9, color=QColor(255, 215, 0, 140))
            if mode == "분석 없음":
                self.result.setText("")
            elif mode == "자동 분석":
                a = auto_analyze(t, y)
                self._draw_stats(t, y)
                if a.fit:
                    self.overlay.setData(t, a.fit.predict(t))
                    top = self._view()[1][1]
                    self.marks.label(a.fit.summary(), float(t[0]), top, anchor=(0, 0))
                for px, py in a.peaks[:3]:
                    self.marks.callout(f"{px:.4g} s, {py:.4g} {self._unit()}", (px, py),
                                       box_position(self._view(), (px, py)))
                self.result.setText(a.summary())
            elif mode == "통계":
                s = self._draw_stats(t, y)
                self.result.setText(
                    f"n={s.n}  평균={s.mean:.4g}  표준편차={s.std:.4g}  "
                    f"최소={s.minimum:.4g} (t={s.t_min:.3g})  최대={s.maximum:.4g} (t={s.t_max:.3g})")
            elif mode == "넓이":
                area = self._draw_area(t, y)
                self.result.setText(f"넓이 = {area:.4g}")
            else:
                f = fit(mode, t, y)
                self.overlay.setData(t, f.predict(t))
                self.marks.label(f.summary(), float(t[0]), self._view()[1][1], anchor=(0, 0))
                self.result.setText(f.summary())
        except ValueError as e:  # too few points, no convergence, empty selection
            self.result.setText(str(e))

    # --- user annotations: coordinate tool and text boxes -----------------------------------------
    def _clicked(self, event):
        if event.button() != Qt.LeftButton or self.data is None or len(self.data[0]) == 0:
            return
        if not (self.coord_check.isChecked() or self.note_check.isChecked()):
            return
        vb = self.plot.getPlotItem().vb
        if not vb.sceneBoundingRect().contains(event.scenePos()):
            return
        self.place_at(vb.mapSceneToView(event.scenePos()).x())

    def place_at(self, x: float):
        """Coordinate tool / text box at the data point nearest to time x."""
        t, y = self.data
        i = int(np.clip(np.searchsorted(t, x), 0, len(t) - 1))
        if i > 0 and abs(t[i - 1] - x) < abs(t[i] - x):
            i -= 1
        if self.coord_check.isChecked():
            self.coord_point = (float(t[i]), float(y[i]))
        elif self.note_check.isChecked():
            span = float(t[-1] - t[0]) or 1.0
            near = [n for n in self.notes if abs(n["x"] - float(t[i])) <= 0.02 * span]
            if near:  # clicking an existing text box with the tool on removes it
                self.notes.remove(near[0])
                self.title_changed.emit()
                self.draw_user_marks()
                return
            text = self._ask_note()
            if not text:
                return
            self.notes.append({"x": float(t[i]), "text": text})
            self.title_changed.emit()  # marks the experiment as modified
        self.draw_user_marks()

    def _ask_note(self) -> str:
        text, ok = QInputDialog.getText(self, "텍스트 상자", "메모:")
        return text.strip() if ok else ""

    def set_notes(self, notes):
        self.notes = [n for n in notes if isinstance(n, dict) and isinstance(n.get("text"), str)
                      and isinstance(n.get("x"), (int, float))]
        self.draw_user_marks()

    def draw_user_marks(self):
        self.user_marks.clear()
        if self.data is None or len(self.data[0]) == 0:
            return
        t, y = self.data
        if self.coord_point:
            px, py = self.coord_point
            self.user_marks.crosshair(px, py)
            self.user_marks.callout(f"{px:.4g} s, {py:.4g} {self._unit()}", (px, py),
                                    box_position(self._view(), (px, py)))
        for n in self.notes:
            i = int(np.clip(np.searchsorted(t, n["x"]), 0, len(t) - 1))
            point = (float(t[i]), float(y[i]))
            self.user_marks.callout(n["text"], point, box_position(self._view(), point, dx=0.04, dy=0.2))


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


class BarMeterDisplay(QWidget):
    """Vertical bar filled in proportion to the latest value between the sensor's range limits."""

    def __init__(self):
        super().__init__()
        self.minimum, self.maximum, self.unit, self.value = 0.0, 10.0, "", None

    @staticmethod
    def fraction(value, minimum, maximum):
        if value is None or maximum <= minimum:
            return 0.0
        return min(1.0, max(0.0, (value - minimum) / (maximum - minimum)))

    def show(self, meas, data):
        if meas:
            self.minimum, self.maximum, self.unit = meas.minimum, meas.maximum, meas.unit
        self.value = None if data is None or len(data[1]) == 0 else float(data[1][-1])
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        pal = self.palette()
        w, h = self.width(), self.height()
        bar = QRectF(w / 2 - 25, 20, 50, h - 60)
        p.setPen(QPen(pal.color(QPalette.Text), 1))
        p.setBrush(pal.color(QPalette.Base))
        p.drawRect(bar)
        f = self.fraction(self.value, self.minimum, self.maximum)
        p.setBrush(QColor("#1f2bff"))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(bar.left(), bar.bottom() - f * bar.height(), bar.width(), f * bar.height()))
        p.setPen(pal.color(QPalette.Text))
        p.drawText(QRectF(0, h - 36, w, 30), Qt.AlignCenter,
                   "— — —" if self.value is None else f"{self.value:.4g} {self.unit}")
        p.drawText(QRectF(bar.right() + 6, bar.top() - 8, 80, 16), Qt.AlignLeft, f"{self.maximum:g}")
        p.drawText(QRectF(bar.right() + 6, bar.bottom() - 8, 80, 16), Qt.AlignLeft, f"{self.minimum:g}")


class FftDisplay(pg.PlotWidget):
    """Amplitude spectrum of the newest run. Assumes even sampling (mean interval); the DC part is removed."""

    def __init__(self):
        super().__init__()
        style_plot(self)
        self.setLabel("bottom", "주파수 (Hz)")
        self.setLabel("left", "진폭")
        self.curve = self.plot(pen=pg.mkPen("#1f2bff", width=2))

    @staticmethod
    def spectrum(t, y):
        """(freqs, amplitudes) or None when there are too few samples."""
        t, y = np.asarray(t, float), np.asarray(y, float)
        if len(t) < 4 or t[-1] <= t[0]:
            return None
        dt = (t[-1] - t[0]) / (len(t) - 1)
        amp = np.abs(np.fft.rfft(y - y.mean())) * 2 / len(y)
        return np.fft.rfftfreq(len(y), dt)[1:], amp[1:]

    def show(self, meas, data):
        spec = None if data is None else self.spectrum(*data)
        self.curve.setData(*(spec if spec else ([], [])))


class HistogramDisplay(pg.PlotWidget):
    """Distribution of the newest run's values (equal-width bins, Sturges' rule)."""

    def __init__(self):
        super().__init__()
        style_plot(self)
        self.setLabel("left", "개수")
        self.bars = pg.BarGraphItem(x=[], height=[], width=1, brush="#1f2bff")
        self.addItem(self.bars)

    @staticmethod
    def bins(y):
        """(bin centres, counts, bin width) or None for empty data."""
        y = np.asarray(y, float)
        y = y[np.isfinite(y)]
        if len(y) == 0:
            return None
        counts, edges = np.histogram(y, bins=int(np.ceil(np.log2(len(y)))) + 1)
        width = edges[1] - edges[0]
        return (edges[:-1] + edges[1:]) / 2, counts, width

    def show(self, meas, data):
        h = None if data is None else self.bins(data[1])
        if h is None:
            self.bars.setOpts(x=[], height=[])
            return
        x, counts, width = h
        self.bars.setOpts(x=x, height=counts, width=width * 0.9)
        self.setLabel("bottom", meas.label if meas else "")


DISPLAY_TYPES = {
    "그래프": GraphDisplay,
    "테이블": TableDisplay,
    "숫자": DigitsDisplay,
    "미터": MeterDisplay,
    "막대 미터": BarMeterDisplay,
    "FFT": FftDisplay,
    "히스토그램": HistogramDisplay,
}
