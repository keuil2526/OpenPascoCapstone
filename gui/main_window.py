"""OpenPASCO main window: pages of displays, side tool panel, recording control bar."""
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QMimeData, QSettings, Qt, QTimer, Signal
import pyqtgraph as pg
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QComboBox, QDockWidget, QHBoxLayout, QInputDialog,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSplitter, QStyle,
    QTabWidget, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from core.data_manager import DataManager
from gui.widgets.displays import DISPLAY_TYPES, DisplayFrame, style_plot
from hardware import simulated
from hardware.base import Sensor
from storage import experiment_storage as storage

FILE_FILTER = "OpenPASCO 실험 (*.opasco)"
SAMPLE_RATES_HZ = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
GRID_COLUMNS = 2
DISPLAY_MIME = "application/x-openpasco-display"

RECORD_STYLE = """
QPushButton { background: %s; color: white; font-weight: bold;
              border: none; border-radius: 4px; padding: 6px 14px; }
QPushButton:hover { background: %s; }
"""


def dark_palette() -> QPalette:
    pal = QPalette()
    for role, color in {
        QPalette.Window: "#2b2b2b", QPalette.WindowText: "#e0e0e0",
        QPalette.Base: "#1e1e1e", QPalette.AlternateBase: "#2b2b2b",
        QPalette.Text: "#e0e0e0", QPalette.Button: "#353535", QPalette.ButtonText: "#e0e0e0",
        QPalette.ToolTipBase: "#353535", QPalette.ToolTipText: "#e0e0e0",
        QPalette.Highlight: "#2a82da", QPalette.HighlightedText: "#ffffff",
        QPalette.Link: "#5aa9f0", QPalette.PlaceholderText: "#808080",
    }.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#707070"))
    return pal


IDLE_STYLE = RECORD_STYLE % ("#2e7d32", "#388e3c")
RECORDING_STYLE = RECORD_STYLE % ("#c62828", "#d32f2f")


class DisplayPalette(QListWidget):
    """List of display types; items can be dragged onto a page."""

    def __init__(self):
        super().__init__()
        self.addItems(DISPLAY_TYPES)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setToolTip("페이지로 끌어다 놓거나 더블클릭하여 추가")

    def mimeData(self, items):
        mime = QMimeData()
        mime.setData(DISPLAY_MIME, items[0].text().encode())
        return mime


class Page(QWidget):
    """One experiment page: displays in rows of 2, resizable with splitters."""

    display_added = Signal(DisplayFrame)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.box = QVBoxLayout(self)
        self.displays: list[DisplayFrame] = []
        self.hint = QLabel("왼쪽 '디스플레이' 목록에서 항목을 끌어다 놓거나 더블클릭하여 추가하세요.",
                           alignment=Qt.AlignCenter)
        self.hint.setStyleSheet("color: gray; font-size: 14px;")
        self.splitter = QSplitter(Qt.Vertical)
        self.box.addWidget(self.hint)
        self.box.addWidget(self.splitter)
        self._relayout()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(DISPLAY_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event):
        kind = bytes(event.mimeData().data(DISPLAY_MIME)).decode()
        if kind in DISPLAY_TYPES:  # mime data can come from outside the app
            self.add_display(kind)
            event.acceptProposedAction()

    def add_display(self, kind: str) -> DisplayFrame:
        frame = DisplayFrame(kind, DISPLAY_TYPES[kind]())
        frame.closed.connect(self.remove_display)
        self.displays.append(frame)
        self._relayout()
        self.display_added.emit(frame)
        return frame

    def remove_display(self, frame):
        self.displays.remove(frame)
        frame.deleteLater()
        self._relayout()

    def _relayout(self):
        # Rebuild splitters; addWidget reparents frames, so deleting the old tree keeps them.
        root = QSplitter(Qt.Vertical, childrenCollapsible=False)
        for r in range(0, len(self.displays), GRID_COLUMNS):
            row = QSplitter(Qt.Horizontal, childrenCollapsible=False)
            for i, frame in enumerate(self.displays[r:r + GRID_COLUMNS]):
                row.addWidget(frame)
                row.setStretchFactor(i, 1)  # equal widths regardless of size hints
            root.addWidget(row)
            root.setStretchFactor(root.count() - 1, 1)
        self.box.replaceWidget(self.splitter, root)
        self.splitter.deleteLater()
        self.splitter = root
        self.hint.setVisible(not self.displays)
        root.setVisible(bool(self.displays))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenPASCO")
        self.resize(1280, 800)
        self.recording = False
        self.dm = DataManager()
        self.sensors: list[Sensor] = []
        self.known: dict = {}  # key -> (sensor name, Measurement) from opened files
        self.path: Path | None = None

        self.pages = QTabWidget(tabsClosable=True, movable=True, documentMode=True)
        self.pages.tabCloseRequested.connect(self.close_page)
        self.pages.tabBarDoubleClicked.connect(self.rename_page)
        self.pages.currentChanged.connect(lambda _: self.refresh_displays())
        plus = QToolButton(text="+", autoRaise=True, toolTip="페이지 추가 (Ctrl+T)")
        plus.clicked.connect(self.add_page)
        self.pages.setCornerWidget(plus, Qt.TopRightCorner)
        self.setCentralWidget(self.pages)

        self._build_actions()
        self._build_tool_dock()
        self._build_control_bar()
        self.new_experiment()
        self._restore_layout()

    # --- construction -----------------------------------------------------
    def _build_actions(self):
        icon = lambda sp: self.style().standardIcon(sp)

        def act(text, slot, shortcut=None, sp=None):
            a = QAction(text, self, triggered=slot)
            if shortcut:
                a.setShortcut(shortcut)
            if sp is not None:
                a.setIcon(icon(sp))
            return a

        self.act_new = act("새 실험", self.new_experiment, QKeySequence.New, QStyle.SP_FileIcon)
        self.act_open = act("열기…", self.open_experiment, QKeySequence.Open, QStyle.SP_DialogOpenButton)
        self.act_save = act("저장", self.save_experiment, QKeySequence.Save, QStyle.SP_DialogSaveButton)
        self.act_save_as = act("다른 이름으로 저장…", lambda: self.save_experiment(as_new=True),
                               QKeySequence.SaveAs)
        self.act_export = act("CSV 내보내기…", self.export_csv)
        self.act_quit = act("종료", self.close, QKeySequence.Quit)
        self.act_add_page = act("페이지 추가", self.add_page, "Ctrl+T", QStyle.SP_FileDialogNewFolder)
        self.act_rename_page = act("페이지 이름 바꾸기…",
                                   lambda: self.rename_page(self.pages.currentIndex()), "F2")
        self.act_record = act("기록 / 정지", self.toggle_record, "Ctrl+R", QStyle.SP_MediaPlay)

        mb = self.menuBar()
        file_menu = mb.addMenu("파일(&F)")
        for a in (self.act_new, self.act_open, self.act_save, self.act_save_as, None, self.act_export, None, self.act_quit):
            file_menu.addSeparator() if a is None else file_menu.addAction(a)
        page_menu = mb.addMenu("페이지(&P)")
        page_menu.addActions([self.act_add_page, self.act_rename_page])
        mb.addMenu("측정(&M)").addAction(self.act_record)
        self.view_menu = mb.addMenu("보기(&V)")
        self.act_dark = QAction("다크 모드", self, checkable=True, toggled=self.set_dark)
        self.view_menu.addAction(self.act_dark)
        self.view_menu.addSeparator()
        mb.addMenu("도움말(&H)").addAction(act("정보", self.about))

        tb = QToolBar("기본", movable=False, objectName="main_toolbar")
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.addActions([self.act_new, self.act_open, self.act_save])
        tb.addSeparator()
        tb.addAction(self.act_add_page)
        self.addToolBar(tb)

    def _build_tool_dock(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("<b>하드웨어 설정</b>"))
        self.device_list = QListWidget()
        self.device_list.addItem("연결된 장치 없음 — '장치 검색'을 누르세요")
        self.device_list.setEnabled(False)
        self.device_list.itemChanged.connect(lambda _: self.update_measurements())
        layout.addWidget(self.device_list, 1)
        scan = QPushButton("장치 검색", clicked=self.scan_devices)
        scan.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        layout.addWidget(scan)

        layout.addSpacing(8)
        layout.addWidget(QLabel("<b>디스플레이</b>"))
        self.display_list = DisplayPalette()
        self.display_list.itemDoubleClicked.connect(lambda item: self.add_display(item.text()))
        layout.addWidget(self.display_list, 1)

        dock = QDockWidget("도구", self, objectName="tool_dock")
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        dock.setWidget(panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.view_menu.addAction(dock.toggleViewAction())

    def _build_control_bar(self):
        bar = QToolBar("측정 제어", movable=False, objectName="control_bar")
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(6, 4, 6, 4)

        self.record_btn = QPushButton("● 기록", clicked=self.toggle_record)
        self.record_btn.setMinimumWidth(110)
        self.record_btn.setToolTip("기록 시작/정지 (Ctrl+R)")
        self.record_btn.setStyleSheet(IDLE_STYLE)
        row.addWidget(self.record_btn)

        row.addSpacing(12)
        row.addWidget(QLabel("샘플링 속도:"))
        self.rate_combo = QComboBox()
        self.rate_combo.addItems([f"{r} Hz" for r in SAMPLE_RATES_HZ])
        self.rate_combo.setCurrentText("10 Hz")
        row.addWidget(self.rate_combo)

        row.addSpacing(20)
        self.elapsed_label = QLabel("00:00.0")
        font = QFont("monospace")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(14)
        self.elapsed_label.setFont(font)
        row.addWidget(self.elapsed_label)
        row.addStretch()

        bar.addWidget(container)
        self.addToolBar(Qt.BottomToolBarArea, bar)

        self.elapsed = QElapsedTimer()
        self.clock = QTimer(self, interval=33, timeout=self._tick)  # ~30 fps display refresh

    # --- window state -----------------------------------------------------
    def _restore_layout(self):
        s = QSettings()
        if s.value("geometry"):
            self.restoreGeometry(s.value("geometry"))
        if s.value("windowState"):
            self.restoreState(s.value("windowState"))
        self.act_dark.setChecked(s.value("dark", False, type=bool))

    def set_dark(self, on: bool):
        app = QApplication.instance()
        app.setPalette(dark_palette() if on else app.style().standardPalette())
        for plot in self.findChildren(pg.PlotWidget):
            style_plot(plot)
        QSettings().setValue("dark", on)

    def closeEvent(self, event):
        if self.recording:
            self.toggle_record()  # stop sensor threads
        s = QSettings()
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState())
        super().closeEvent(event)

    # --- actions ----------------------------------------------------------
    def new_experiment(self):
        if self.dm.runs and QMessageBox.question(
                self, "새 실험", "기록된 데이터가 모두 사라집니다. 계속할까요?") != QMessageBox.Yes:
            return
        if self.recording:
            self.toggle_record()
        self.dm.clear()
        self.known.clear()
        self.path = None
        self.setWindowTitle("OpenPASCO")
        self.pages.clear()
        self.add_page()
        self.statusBar().showMessage("새 실험")

    # --- files ------------------------------------------------------------
    def layout_state(self) -> dict:
        return {"rate_index": self.rate_combo.currentIndex(), "pages": [
            {"name": self.pages.tabText(i),
             "displays": [{"kind": f.kind, "key": f.key} for f in self.pages.widget(i).displays]}
            for i in range(self.pages.count())]}

    def apply_layout(self, layout: dict):
        self.pages.clear()
        for pg_state in layout.get("pages") or [{"name": "페이지 1", "displays": []}]:
            page = self.add_page()
            self.pages.setTabText(self.pages.indexOf(page), pg_state["name"])
            for d in pg_state["displays"]:
                if d["kind"] not in DISPLAY_TYPES:
                    continue  # file from a newer version; skip unknown display
                frame = page.add_display(d["kind"])
                idx = frame.selector.findData(d["key"])
                if idx >= 0:
                    frame.selector.setCurrentIndex(idx)
                frame.refresh(self.dm)
        self.pages.setCurrentIndex(0)
        rate = layout.get("rate_index")
        if isinstance(rate, int) and 0 <= rate < self.rate_combo.count():
            self.rate_combo.setCurrentIndex(rate)

    def _set_path(self, path):
        self.path = Path(path)
        self.setWindowTitle(f"{self.path.name} — OpenPASCO")

    def save_experiment(self, as_new=False):
        if self.recording:
            return
        path = self.path
        if as_new or path is None:
            name, _ = QFileDialog.getSaveFileName(self, "실험 저장", str(path or "실험.opasco"), FILE_FILTER)
            if not name:
                return
            path = Path(name).with_suffix(".opasco")
        used = {k for r in self.dm.runs for k in r.series}
        meas = {k: v for k, v in self._all_measurements().items() if k in used}
        try:
            storage.save(path, self.dm.runs, self.layout_state(), meas)
        except (OSError, TypeError) as e:
            QMessageBox.critical(self, "저장 실패", str(e))
            return
        self._set_path(path)
        self.statusBar().showMessage(f"저장됨: {path}")

    def _all_measurements(self):
        items = dict(self.known)
        items.update({f"{s.id}:{m.id}": (s.name, m) for s in self.sensors for m in s.measurements})
        return items

    def open_experiment(self):
        if self.recording:
            return
        name, _ = QFileDialog.getOpenFileName(self, "실험 열기", "", FILE_FILTER)
        if not name:
            return
        if self.dm.runs and QMessageBox.question(
                self, "실험 열기", "현재 기록된 데이터가 닫힙니다(저장하지 않았다면 사라집니다). 계속할까요?"
        ) != QMessageBox.Yes:
            return
        try:
            runs, layout, meas = storage.load(name)
        except (ValueError, OSError) as e:
            QMessageBox.critical(self, "열기 실패", str(e))
            return
        self.dm.load(runs)
        self.known = meas
        self.apply_layout(layout)
        self._set_path(name)
        self.statusBar().showMessage(f"열기: {name} — 런 {len(runs)}개")

    def export_csv(self):
        runs = self.dm.runs
        if not runs or self.recording:
            self.statusBar().showMessage("내보낼 기록이 없습니다.")
            return
        run = runs[-1]
        if len(runs) > 1:
            labels = [f"런 #{r.number}" for r in runs]
            label, ok = QInputDialog.getItem(self, "CSV 내보내기", "내보낼 런:", labels, len(labels) - 1, False)
            if not ok:
                return
            run = runs[labels.index(label)]
        name, _ = QFileDialog.getSaveFileName(self, "CSV 내보내기", f"런{run.number}.csv", "CSV (*.csv)")
        if not name:
            return
        try:
            storage.export_csv(name, run, self._all_measurements())
        except OSError as e:
            QMessageBox.critical(self, "내보내기 실패", str(e))
            return
        self.statusBar().showMessage(f"CSV 저장됨: {name}")

    def add_page(self) -> Page:
        page = Page()
        page.display_added.connect(self._init_display)
        idx = self.pages.addTab(page, f"페이지 {self.pages.count() + 1}")
        self.pages.setCurrentIndex(idx)
        return page

    def rename_page(self, index: int):
        if index < 0:
            return
        name, ok = QInputDialog.getText(self, "페이지 이름", "새 이름:", text=self.pages.tabText(index))
        if ok and name.strip():
            self.pages.setTabText(index, name.strip())

    def close_page(self, index: int):
        if self.pages.count() > 1:  # always keep one page
            self.pages.widget(index).deleteLater()
            self.pages.removeTab(index)

    def add_display(self, kind: str):
        self.pages.currentWidget().add_display(kind)

    # --- sensors & recording ---------------------------------------------
    def scan_devices(self):
        if self.recording:
            return
        self.sensors = simulated.scan()  # shortcut: simulated only; real drivers join in Phase 4
        self.device_list.blockSignals(True)
        self.device_list.clear()
        for sensor in self.sensors:
            item = QListWidgetItem(sensor.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setToolTip(", ".join(m.label for m in sensor.measurements))
            self.device_list.addItem(item)
        self.device_list.blockSignals(False)
        self.device_list.setEnabled(True)
        self.update_measurements()
        self.statusBar().showMessage(f"장치 {len(self.sensors)}개 발견")

    def active_sensors(self) -> list[Sensor]:
        return [s for i, s in enumerate(self.sensors)
                if self.device_list.item(i).checkState() == Qt.Checked]

    def available_measurements(self):
        items = dict(self.known)
        items.update({f"{s.id}:{m.id}": (s.name, m) for s in self.active_sensors() for m in s.measurements})
        return items

    def all_frames(self):
        return [f for i in range(self.pages.count()) for f in self.pages.widget(i).displays]

    def update_measurements(self):
        items = self.available_measurements()
        for frame in self.all_frames():
            frame.set_measurements(items)
            frame.refresh(self.dm)

    def _init_display(self, frame):
        frame.set_measurements(self.available_measurements())
        frame.refresh(self.dm)

    def refresh_displays(self):
        page = self.pages.currentWidget()
        if page:
            for frame in page.displays:
                frame.refresh(self.dm)

    def _on_samples(self, sensor_id, t, values):  # called from sensor threads
        for mid, y in values.items():
            self.dm.append(f"{sensor_id}:{mid}", t, y)

    def toggle_record(self):
        if not self.recording:
            sensors = self.active_sensors()
            if not sensors:
                self.statusBar().showMessage("기록할 센서가 없습니다. '장치 검색' 후 센서를 선택하세요.")
                return
            run = self.dm.start_run()
            rate = SAMPLE_RATES_HZ[self.rate_combo.currentIndex()]
            self.running_sensors = sensors
            for sensor in sensors:
                sensor.start(rate, self._on_samples)
            self.recording = True
            self.elapsed.start()
            self.clock.start()
            self.record_btn.setText("■ 정지")
            self.record_btn.setStyleSheet(RECORDING_STYLE)
            self.statusBar().showMessage(f"기록 중 — 런 #{run.number}, {rate} Hz")
        else:
            for sensor in self.running_sensors:
                sensor.stop()
            self.dm.stop_run()
            self.recording = False
            self.clock.stop()
            self.refresh_displays()
            self.record_btn.setText("● 기록")
            self.record_btn.setStyleSheet(IDLE_STYLE)
            self.statusBar().showMessage(f"정지 — 런 {len(self.dm.runs)}개 기록됨")
        self.rate_combo.setEnabled(not self.recording)
        self.device_list.setEnabled(not self.recording and bool(self.sensors))

    def _tick(self):
        s = self.elapsed.elapsed() / 1000
        self.elapsed_label.setText(f"{int(s // 60):02d}:{s % 60:04.1f}")
        self.refresh_displays()

    def not_ready(self):
        QMessageBox.information(self, "미구현", "이 기능은 아직 구현되지 않았습니다.")

    def about(self):
        QMessageBox.about(self, "OpenPASCO",
                          "OpenPASCO — Linux용 PASCO 데이터 수집 프로그램 (개발 중)\n"
                          "개인·비상업·교육 목적")
