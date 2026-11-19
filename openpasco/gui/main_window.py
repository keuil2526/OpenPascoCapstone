"""OpenPASCO main window: pages of displays, side tool panel, recording control bar."""
import threading
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QMimeData, QSettings, QSize, Qt, QTimer, Signal
import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QAction, QColor, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDockWidget, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QListView, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QStatusBar, QTabBar,
    QFrame, QPushButton, QSplitter, QStyle, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar, QToolButton,
    QVBoxLayout, QWidget,
)

from openpasco.core.calculation import CalcError, parse
from openpasco.core.data_manager import Calc, DataManager, Run, Series
from openpasco.gui import icons
from openpasco.gui.theme import CHROME_QSS, CHROME_QSS_LIGHT
from openpasco.core.conditions import Condition, Conditions, Gate
from openpasco.gui.widgets.calc_dialog import CalcDialog
from openpasco.gui.widgets.conditions_dialog import ConditionsDialog
from openpasco.gui.widgets.start_cards import StartCards
from openpasco.gui.widgets.displays import DISPLAY_TYPES, DisplayFrame, style_plot
from openpasco.hardware import discovery
from openpasco.hardware.base import Measurement, Sensor
from openpasco.storage import capstone_export, capstone_import, experiment_storage as storage

FILE_FILTER = "Capstone 실험 (*.cap)"
SAMPLE_RATES_HZ = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
GRID_COLUMNS = 2
DISPLAY_MIME = "application/x-openpasco-display"

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


class DisplayPalette(QListWidget):
    """List of display types; items can be dragged onto a page."""

    ICON_FOR = {"그래프": "graph", "테이블": "table", "숫자": "digits", "미터": "meter", "FFT": "fft", "막대 미터": "bar_meter", "히스토그램": "histogram"}

    def __init__(self):
        super().__init__()
        self.setObjectName("display_list")
        for name in DISPLAY_TYPES:
            self.addItem(QListWidgetItem(icons.icon(self.ICON_FOR[name]), name))
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.TopToBottom)
        self.setMovement(QListView.Static)  # required for drag-out
        self.setWrapping(False)
        self.setIconSize(QSize(28, 28))
        self.setGridSize(QSize(84, 56))
        self.setFixedWidth(94)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setToolTip("클릭하거나 페이지로 끌어다 놓아 디스플레이를 추가")

    def mimeData(self, items):
        mime = QMimeData()
        mime.setData(DISPLAY_MIME, items[0].text().encode())
        return mime


class Page(QWidget):
    """One experiment page: displays in rows of 2, resizable with splitters."""

    display_added = Signal(DisplayFrame)
    display_removed = Signal()
    start_requested = Signal(str, QWidget)  # start-card id, button

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        self.setAttribute(Qt.WA_StyledBackground)  # plain QWidget subclasses ignore QSS backgrounds otherwise
        self.setAcceptDrops(True)
        self.box = QVBoxLayout(self)
        self.displays: list[DisplayFrame] = []
        self.hint = StartCards()  # empty-page start screen
        self.hint.chosen.connect(self.start_requested)
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
        self.display_removed.emit()

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


def dock_title(dock: QDockWidget) -> QWidget:
    """Capstone-style panel title: small bold name, close button on the right, dotted grip underneath."""
    box = QWidget(objectName="dock_title")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(6, 3, 4, 0)
    lay.setSpacing(0)
    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    top.addWidget(QLabel(dock.windowTitle()), 1)
    close = QToolButton(text="✕", autoRaise=True, toolTip="닫기 (보기 메뉴에서 다시 열기)", objectName="dock_close")
    close.clicked.connect(dock.close)
    top.addWidget(close)
    lay.addLayout(top)
    lay.addWidget(QLabel("· ·", objectName="dock_grip"))
    return box


class TimedStatusBar(QStatusBar):
    """Capstone has no permanent status text; messages fade after a few seconds."""
    def showMessage(self, text, ms=8000):
        super().showMessage(text, ms)


class PageTabs(QTabWidget):
    """QTabWidget that tells the window when tabs come and go, so a full-width tab row can mirror them."""
    changed = Signal()

    def tabInserted(self, index):
        super().tabInserted(index)
        self.changed.emit()

    def tabRemoved(self, index):
        super().tabRemoved(index)
        self.changed.emit()


class MainWindow(QMainWindow):
    scan_done = Signal(list, list)  # sensors, warnings; emitted from the scan thread
    sensor_error = Signal(str)  # emitted from sensor threads

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenPASCO")
        self.setStyleSheet(CHROME_QSS)
        self.resize(1280, 800)
        self.recording = False
        self.dm = DataManager()
        self.sensors: list[Sensor] = []
        self.scanning = False
        self.known: dict = {}  # key -> (sensor name, Measurement) from opened files
        self.path: Path | None = None
        self.doc_name: str | None = None
        self.dirty = False

        self.scan_done.connect(self._on_scan_done)
        self.sensor_error.connect(self._on_sensor_error)
        self.pages = PageTabs(tabsClosable=True, movable=True, documentMode=True)
        self.pages.tabCloseRequested.connect(self.close_page)
        self.pages.tabBarDoubleClicked.connect(self.rename_page)
        self.pages.currentChanged.connect(lambda _: self.refresh_displays())
        self.setCentralWidget(self.pages)
        self.setAcceptDrops(True)  # drop a .cap file on the window to import it

        self.setStatusBar(TimedStatusBar())
        self._build_actions()
        self._build_tab_row()
        self._build_tool_dock()
        self._build_control_bar()
        self._add_panel_toggles()
        self.new_experiment()
        self._restore_layout()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if urls and urls[0].lower().endswith(".cap"):
            self.open_experiment(urls[0])

    # --- construction -----------------------------------------------------
    def _build_actions(self):

        def act(text, slot, shortcut=None, sp=None):
            a = QAction(text, self, triggered=slot)
            if shortcut:
                a.setShortcut(shortcut)
            if sp is not None:
                a.setIcon(icons.icon(sp))
            return a

        self.act_new = act("새 실험", self.new_experiment, QKeySequence.New, "new_doc")
        self.act_open = act("열기… (.cap)", self.open_experiment, QKeySequence.Open, "open_folder")
        self.act_save = act("저장", self.save_experiment, QKeySequence.Save, "save_disk")
        self.act_save_as = act("다른 이름으로 저장…", lambda: self.save_experiment(as_new=True),
                               QKeySequence.SaveAs)
        self.act_export = act("CSV 내보내기…", self.export_csv)
        self.act_quit = act("종료", self.close, QKeySequence.Quit)
        self.act_add_page = act("페이지 추가", self.add_page, "Ctrl+T", "add_page")
        self.act_copy_page = act("페이지 이미지 복사", self.copy_page_image, "Ctrl+Shift+C", "copy")
        self.act_rename_page = act("페이지 이름 바꾸기…",
                                   lambda: self.rename_page(self.pages.currentIndex()), "F2")
        self.act_record = act("기록 / 정지", self.toggle_record, "Ctrl+R")
        self.act_calc = act("계산 추가…", self.add_calculation, "Ctrl+L")
        self.act_conditions = act("기록 조건…", self.set_recording_conditions)
        self.act_delete_run = act("마지막 런 삭제", self.delete_last_run, None, "trash")
        self.act_calc_delete = act("계산 삭제…", self.remove_calculation)

        mb = self.menuBar()  # menu names follow Capstone's: File / Edit / Workbook / Display / Help
        file_menu = mb.addMenu("파일(&F)")
        for a in (self.act_new, self.act_open, self.act_save, self.act_save_as, None, self.act_export, None, self.act_quit):
            file_menu.addSeparator() if a is None else file_menu.addAction(a)
        mb.addMenu("편집(&E)").addActions([self.act_record, self.act_conditions, self.act_delete_run,
                                          self.act_calc, self.act_calc_delete])
        mb.addMenu("워크북(&W)").addActions([self.act_add_page, self.act_rename_page])
        self.view_menu = mb.addMenu("디스플레이(&D)")
        for kind in DISPLAY_TYPES:
            self.view_menu.addAction(act(f"{kind} 추가", lambda _=False, k=kind: self.add_display(k)))
        self.view_menu.addSeparator()
        self.act_dark = QAction("다크 모드", self, checkable=True, toggled=self.set_dark)
        self.view_menu.addAction(self.act_dark)
        self.act_white = QAction("화이트 모드", self, checkable=True, toggled=self.set_white)
        self.view_menu.addAction(self.act_white)
        self.view_menu.addSeparator()
        mb.addMenu("도움말(&H)").addAction(act("정보", self.about))

        tb = QToolBar("기본", movable=False, objectName="main_toolbar")
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)  # icons only, like Capstone; text shows as tooltip
        tb.setIconSize(QSize(22, 22))
        tb.addActions([self.act_new, self.act_open, self.act_save])
        tb.addSeparator()
        tb.addAction(self.act_add_page)
        tb.addSeparator()
        tb.addActions([self.act_copy_page, self.act_delete_run])
        self.addToolBar(tb)

    def copy_page_image(self):
        QApplication.clipboard().setPixmap(self.pages.currentWidget().grab())
        self.statusBar().showMessage("현재 페이지를 이미지로 복사했습니다.")

    def _build_tab_row(self):
        """Capstone's tab row spans the whole window above the side panels. The pages' own tab bar is hidden
        and this bar mirrors it (a QToolBar is the only thing that can sit above the dock areas)."""
        self.pages.tabBar().hide()
        self.tab_row = QTabBar(tabsClosable=True, movable=True, drawBase=False, expanding=False,
                               objectName="tab_row")
        self._syncing = False
        row = self.page_row = QToolBar("페이지", movable=False, objectName="page_row")
        self.addToolBarBreak(Qt.TopToolBarArea)
        row.addWidget(self.tab_row)
        plus = QToolButton(text="+", autoRaise=True, toolTip="페이지 추가 (Ctrl+T)", objectName="tab_plus")
        plus.clicked.connect(self.add_page)
        row.addWidget(plus)
        self.addToolBar(Qt.TopToolBarArea, row)
        self.pages.changed.connect(self.sync_tab_row)
        self.pages.currentChanged.connect(lambda _: self.sync_tab_row())

        def current(i):
            if not self._syncing and i >= 0:
                self.pages.setCurrentIndex(i)

        def moved(a, b):
            if not self._syncing:
                self.pages.tabBar().moveTab(a, b)

        self.tab_row.currentChanged.connect(current)
        self.tab_row.tabCloseRequested.connect(self.close_page)
        self.tab_row.tabMoved.connect(moved)
        self.tab_row.tabBarDoubleClicked.connect(self.rename_page)

    def _add_panel_toggles(self):
        """The small icons left of Capstone's tab row: here they show/hide the tools, displays and controls panels."""
        first = self.page_row.actions()[0]
        for icon_name, tip, target in (("hardware", "도구 패널", self.findChild(QDockWidget, "tool_dock")),
                                       ("graph", "디스플레이 패널", self.findChild(QDockWidget, "display_dock")),
                                       ("record", "제어 바", self.findChild(QToolBar, "control_bar"))):
            a = target.toggleViewAction()
            a.setIcon(icons.icon(icon_name))
            a.setToolTip(tip + " 보이기/숨기기")
            self.page_row.insertAction(first, a)
        self.page_row.insertSeparator(first)

    def sync_tab_row(self):
        bar, n = self.tab_row, self.pages.count()
        self._syncing = True
        try:
            while bar.count() > n:
                bar.removeTab(bar.count() - 1)
            while bar.count() < n:
                bar.addTab("")
            for i in range(n):
                bar.setTabText(i, self.pages.tabText(i))
            bar.setCurrentIndex(self.pages.currentIndex())
        finally:
            self._syncing = False

    def _build_tool_dock(self):
        # left: tool palette + hardware panel
        palette = QWidget(objectName="palette")
        pl = QVBoxLayout(palette)
        pl.setContentsMargins(4, 6, 4, 6)

        def tool(text, icon_name, slot, checkable=False):
            b = QToolButton(objectName="tool_btn", text=text, icon=icons.icon(icon_name), checkable=checkable)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(28, 28))
            b.setFixedWidth(66)
            b.clicked.connect(slot)
            pl.addWidget(b)
            return b

        self.hw_btn = tool("하드웨어\n설정", "hardware", self._toggle_hw_panel, True)
        tool("데이터\n요약", "summary", self.show_data_summary)
        tool("계산기", "calculator", self.add_calculation)
        pl.addStretch()

        self.hw_panel = QWidget(objectName="hw_panel")
        hl = QVBoxLayout(self.hw_panel)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(QLabel("하드웨어 설정", objectName="panel_title"))
        status_row = QWidget(objectName="hw_status_row")
        sr = QHBoxLayout(status_row)
        sr.setContentsMargins(8, 6, 6, 6)
        self.hw_status = QLabel("장치를 검색하려면 오른쪽 버튼을 누르세요", objectName="hw_status")
        sr.addWidget(self.hw_status, 1)
        self.scan_btn = QToolButton(objectName="action_btn", toolTip="장치 검색", text="검색")
        self.scan_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.scan_btn.clicked.connect(lambda: self.scan_devices())
        sr.addWidget(self.scan_btn)
        hl.addWidget(status_row)
        self.hw_hint = QLabel("연결된 장치가 없습니다. 인터페이스나 무선 장치를 연결하세요.", objectName="hw_hint")
        hl.addWidget(self.hw_hint)
        self.device_list = QListWidget(objectName="device_list")
        self.device_list.addItem("연결된 장치 없음 — 검색 버튼을 누르세요")
        self.device_list.setEnabled(False)
        self.device_list.itemChanged.connect(lambda _: self.update_measurements())
        hl.addWidget(self.device_list, 1)
        self.hw_panel.setFixedWidth(330)
        self.hw_panel.setVisible(False)

        left = QWidget(objectName="palette")
        row = QHBoxLayout(left)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(palette)
        row.addWidget(self.hw_panel)
        dock = QDockWidget("도구", self, objectName="tool_dock")
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        dock.setWidget(left)
        dock.setTitleBarWidget(dock_title(dock))
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.view_menu.addAction(dock.toggleViewAction())

        # right: display palette
        self.display_list = DisplayPalette()
        self.display_list.itemClicked.connect(lambda item: self.add_display(item.text()))
        right = QDockWidget("디스플레이", self, objectName="display_dock")
        right.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        right.setWidget(self.display_list)
        right.setTitleBarWidget(dock_title(right))
        self.addDockWidget(Qt.RightDockWidgetArea, right)
        self.view_menu.addAction(right.toggleViewAction())

    def _toggle_hw_panel(self, on: bool):
        self.hw_panel.setVisible(on)
        if on and not self.sensors and not self.scanning and not self.recording:
            self.scan_devices()  # like Capstone, searching starts when the panel opens

    def _build_control_bar(self):
        bar = QToolBar("측정 제어", movable=False, objectName="control_bar")
        container = QWidget(objectName="control_row")
        row = QHBoxLayout(container)
        row.setContentsMargins(10, 0, 10, 0)
        row.setSpacing(10)

        def button(name, text, icon_name, slot, tip):
            b = QToolButton(objectName=name, text=text, icon=icons.icon(icon_name), toolTip=tip)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(26, 26))
            b.setMinimumWidth(62)
            b.clicked.connect(slot)
            return b

        def group():  # rounded darker panel around related controls
            g = QFrame(objectName="ctl_group")
            gl = QHBoxLayout(g)
            gl.setContentsMargins(8, 2, 8, 2)
            gl.setSpacing(8)
            row.addWidget(g)
            return gl

        g1 = group()
        self.record_btn = button("record_btn", "기록", "record", self.toggle_record, "기록 시작/정지 (Ctrl+R)")
        g1.addWidget(self.record_btn)
        self.timer_label = self.elapsed_label = QLabel("00:00.00", objectName="timer")
        g1.addWidget(self.timer_label)

        g2 = group()
        g2.addWidget(QLabel("샘플링 속도"))
        self.rate_combo = QComboBox()
        self.rate_combo.addItems([f"{r} Hz" for r in SAMPLE_RATES_HZ])
        self.rate_combo.setCurrentText("10 Hz")
        g2.addWidget(self.rate_combo)

        self.conditions_btn = button("action_btn", "기록 조건", "clock", self.set_recording_conditions,
                                     "자동 정지 시간 설정")
        self.delete_run_btn = button("action_btn", "마지막 런\n삭제", "trash", self.delete_last_run,
                                     "가장 최근에 기록한 런을 삭제")
        row.addSpacing(12)
        row.addWidget(self.conditions_btn)
        row.addWidget(self.delete_run_btn)
        row.addStretch()

        bar.addWidget(container)
        self.addToolBar(Qt.BottomToolBarArea, bar)

        self.conditions = Conditions()  # start / stop conditions (not saved in files)
        self.gate: Gate | None = None
        self.elapsed = QElapsedTimer()
        self.clock = QTimer(self, interval=33, timeout=self._tick)  # ~30 fps display refresh

    # --- unsaved changes ----------------------------------------------------
    def _mark_dirty(self, *_):
        self.dirty = True
        self._update_title()

    def _set_clean(self):
        self.dirty = False
        self._update_title()

    def _update_title(self):
        self.setWindowTitle(f"{'● ' if self.dirty else ''}{self.doc_name or '제목 없음'} — OpenPASCO")

    def confirm_discard(self, title: str) -> bool:
        """True if it is fine to replace the current experiment (saved, discarded or unchanged)."""
        if self.recording:
            self.toggle_record()
        if not self.dirty:
            return True
        B = QMessageBox
        r = B.question(self, title, "저장하지 않은 변경 사항이 있습니다. 저장할까요?",
                       B.Save | B.Discard | B.Cancel, B.Save)
        if r == B.Save:
            self.save_experiment()
            return not self.dirty  # False if the save dialog was cancelled or failed
        return r == B.Discard

    # --- window state -----------------------------------------------------
    def _restore_layout(self):
        s = QSettings()
        if s.value("geometry"):
            self.restoreGeometry(s.value("geometry"))
        if s.value("windowState"):
            self.restoreState(s.value("windowState"))
        self.act_dark.setChecked(s.value("dark", False, type=bool))
        self.act_white.setChecked(s.value("white", False, type=bool) and not self.act_dark.isChecked())

    def set_white(self, on: bool):
        if on:
            self.act_dark.setChecked(False)  # the two modes are exclusive
        self.setStyleSheet(CHROME_QSS_LIGHT if on else CHROME_QSS)
        icons.set_light(on, self)
        QSettings().setValue("white", on)

    def set_dark(self, on: bool):
        if on:
            self.act_white.setChecked(False)
        app = QApplication.instance()
        app.setPalette(dark_palette() if on else app.style().standardPalette())
        for plot in self.findChildren(pg.PlotWidget):
            style_plot(plot)
        QSettings().setValue("dark", on)

    def closeEvent(self, event):
        if not self.confirm_discard("종료"):
            event.ignore()
            return
        for s in self.sensors:
            s.close()  # disconnect Bluetooth devices
        s = QSettings()
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState())
        super().closeEvent(event)

    # --- actions ----------------------------------------------------------
    def new_experiment(self):
        if not self.confirm_discard("새 실험"):
            return
        self.dm.clear()
        self.cap_origin = {}
        self.conditions = Conditions()
        self.known.clear()
        self.path = self.doc_name = None
        self.pages.clear()
        self.add_page()
        self._set_clean()
        self.statusBar().showMessage("새 실험", 5000)

    # --- files ------------------------------------------------------------
    def layout_state(self) -> dict:
        return {"rate_index": self.rate_combo.currentIndex(), "conditions": asdict(self.conditions),
                "calcs": [asdict(c) for c in self.dm.calcs.values()], "pages": [
            {"name": self.pages.tabText(i),
             "displays": [{"kind": f.kind, "key": f.key, **({"title": f.body.title_edit.text(), "notes": f.body.notes} if hasattr(f.body, "title_edit") else {})}
                          for f in self.pages.widget(i).displays]}
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
                if hasattr(frame.body, "title_edit") and isinstance(d.get("title"), str):
                    frame.body.title_edit.setText(d["title"])
                if hasattr(frame.body, "set_notes") and isinstance(d.get("notes"), list):
                    frame.body.set_notes(d["notes"])
                idx = frame.selector.findData(d["key"])
                if idx >= 0:
                    frame.selector.setCurrentIndex(idx)
                frame.refresh(self.dm)
        self.pages.setCurrentIndex(0)
        self.conditions = self._conditions_from(layout.get("conditions"))
        rate = layout.get("rate_index")
        if isinstance(rate, int) and 0 <= rate < self.rate_combo.count():
            self.rate_combo.setCurrentIndex(rate)

    @staticmethod
    def _conditions_from(d) -> Conditions:
        """Rebuild saved conditions; anything malformed (older/newer file) falls back to none."""
        def one(c):
            try:
                if c and c["kind"] in ("measure", "time") and c.get("op", ">") in (">", "<"):
                    return Condition(c["kind"], str(c.get("key", "")), c.get("op", ">"), float(c.get("value", 0)))
            except (TypeError, ValueError, KeyError):
                pass
            return None
        d = d if isinstance(d, dict) else {}
        return Conditions(one(d.get("start")), one(d.get("stop")))

    def _set_path(self, path):
        self.path = Path(path)
        self.doc_name = self.path.name
        self._set_clean()

    def save_experiment(self, as_new=False):
        if self.recording:
            return
        path = self.path
        if as_new or path is None:
            name, _ = QFileDialog.getSaveFileName(self, "실험 저장", str(path or "실험.cap"), FILE_FILTER)
            if not name:
                return
            path = Path(name).with_suffix(".cap")
        used = {k for r in self.dm.runs for k in r.series}
        meas = {k: v for k, v in self._all_measurements().items() if k in used}
        try:
            warnings = capstone_export.save_cap(path, self.dm.runs, meas, self.layout_state(), self.cap_origin)
        except (OSError, TypeError) as e:
            QMessageBox.critical(self, "저장 실패", str(e))
            return
        self._set_path(path)
        self.statusBar().showMessage(f"저장됨: {path}" + (f" — {warnings[0]}" if warnings else "")
                                     + (f" 외 {len(warnings) - 1}건" if len(warnings) > 1 else ""))

    def _all_measurements(self):
        items = dict(self.known)
        items.update({f"{s.id}:{m.id}": (s.name, m) for s in self.sensors for m in s.measurements})
        return items

    def open_experiment(self, name: str | None = None):
        """Open a .cap. Files written by OpenPASCO restore everything and save back in place; files made by
        Capstone are opened as a copy (Save As), so the original is never overwritten by our reduced writer."""
        if self.recording:
            return
        if not name:
            name, _ = QFileDialog.getOpenFileName(self, "실험 열기", "", FILE_FILTER)
        if not name:
            return
        if not self.confirm_discard("실험 열기"):
            return
        try:
            res = capstone_import.load_cap(name)
        except (ValueError, OSError) as e:
            QMessageBox.critical(self, "열기 실패", str(e))
            return
        own = res.layout is not None
        if not res.runs and not own:
            QMessageBox.information(self, "열기", "읽을 수 있는 측정 데이터가 없습니다."
                                    + (f"\n(지원하지 않는 형식의 데이터 {res.skipped}개 건너뜀)" if res.skipped else ""))
            return
        self.dm.load(res.runs)
        self.known = res.measurements
        self.cap_origin = res.origin
        skipped = 0
        if own:
            layout = res.layout
            skipped = self._restore_calcs(layout.get("calcs", []))
        else:
            layout = {"pages": self._pages_from_cap(res, name)}
        self.apply_layout(layout)
        if own:
            self._set_path(name)
        else:
            self.path = None  # Capstone's own file: saving makes a new .cap
            self.doc_name = f"{Path(name).name} (복사본)"
            self._set_clean()
        notes = (f", 지원하지 않는 데이터 {res.skipped}개 건너뜀" if res.skipped else "") + \
                (f", 경고 {len(res.warnings)}건" if res.warnings else "") + \
                (f", 읽을 수 없는 계산 {skipped}개 건너뜀" if skipped else "")
        self.statusBar().showMessage(f"열기: {Path(name).name} — 런 {len(res.runs)}개, 측정값 {len(res.measurements)}종{notes}")

    @staticmethod
    def _pages_from_cap(res, name) -> list:
        keys = [k for r in res.runs[:1] for k in r.series] or list(res.measurements)
        pages = []
        for pname, items in res.pages:  # unresolved links fall back to cycling through measurements
            if items:
                pages.append({"name": pname, "displays": [{"kind": k, "key": key or keys[i % len(keys)]}
                                                          for i, (k, key) in enumerate(items)]})
        return pages or [{"name": Path(name).stem, "displays": [{"kind": "그래프", "key": keys[0]},
                                                                {"kind": "테이블", "key": keys[0]}]}]

    # --- calculations -----------------------------------------------------
    def create_calc(self, name: str, unit: str, expr: str) -> Calc:
        """Validate and register a calculated measurement; raises CalcError with a user message."""
        items = self.available_measurements()
        by_name: dict[str, list[str]] = {}
        for key, (_, m) in items.items():
            by_name.setdefault(m.name, []).append(key)
        if not name or any(c in name for c in "[]"):
            raise CalcError("이름을 입력하세요 (대괄호 [ ] 는 쓸 수 없습니다)")
        if name in by_name:
            raise CalcError(f"'{name}' 이름은 이미 사용 중입니다")
        _, refs = parse(expr)
        if not refs:
            raise CalcError("수식에 측정값을 [이름]으로 하나 이상 넣어야 합니다")
        resolved = {}
        for ref in refs:
            keys = by_name.get(ref, [])
            if not keys:
                raise CalcError(f"측정값 '{ref}'을(를) 찾을 수 없습니다")
            if len(keys) > 1:
                raise CalcError(f"측정값 이름 '{ref}'이(가) 여러 개입니다. 센서 하나만 선택하세요")
            resolved[ref] = keys[0]
        calc = Calc(f"calc:{name}", name, unit, expr, resolved)
        self._register_calc(calc)
        return calc

    def _register_calc(self, calc: Calc):
        self.dm.calcs[calc.key] = calc
        self._mark_dirty()
        data = self.dm.latest(calc.key)
        finite = data[1][np.isfinite(data[1])] if data is not None else []
        lo, hi = (float(np.min(finite)), float(np.max(finite))) if len(finite) else (0.0, 10.0)
        self.known[calc.key] = ("계산", Measurement(calc.key, calc.name, calc.unit,
                                                    lo, hi if hi > lo else lo + 1))
        self.update_measurements()

    def _restore_calcs(self, saved) -> int:
        """Re-register calculations from a file; returns how many entries were unusable."""
        bad = 0
        for d in saved if isinstance(saved, list) else []:
            try:
                calc = Calc(**d)
                parse(calc.expr)
                if not (calc.key.startswith("calc:") and set(calc.refs) <= set(parse(calc.expr)[1])):
                    raise ValueError
            except (TypeError, ValueError):  # CalcError is a ValueError
                bad += 1
                continue
            self._register_calc(calc)
        return bad

    def add_calculation(self):
        names = sorted({m.name for _, m in self.available_measurements().values()})
        if not names:
            self.statusBar().showMessage("계산할 측정값이 없습니다. 장치 검색 또는 파일 열기를 먼저 하세요.")
            return
        CalcDialog(self, names, self.create_calc).exec()

    def delete_calc(self, key: str):
        users = [c.name for c in self.dm.calcs.values() if c.key != key and key in c.refs.values()]
        if users:
            raise CalcError(f"다른 계산({', '.join(users)})에서 사용 중이라 삭제할 수 없습니다")
        del self.dm.calcs[key]
        self.known.pop(key, None)
        self._mark_dirty()
        self.update_measurements()

    def remove_calculation(self):
        calcs = {c.name: c.key for c in self.dm.calcs.values()}
        if not calcs:
            self.statusBar().showMessage("삭제할 계산이 없습니다.")
            return
        name, ok = QInputDialog.getItem(self, "계산 삭제", "삭제할 계산:", list(calcs), 0, False)
        if ok:
            try:
                self.delete_calc(calcs[name])
            except CalcError as e:
                QMessageBox.warning(self, "삭제할 수 없음", str(e))

    def _run_with_calcs(self, index: int) -> Run:
        """A copy of run `index` that also carries every calculated measurement as a series."""
        src = self.dm.runs[index]
        run = Run(src.number, src.started, dict(src.series))
        for key in self.dm.calcs:
            s = self.dm.series(key, index)
            if s is not None:
                run.series[key] = Series(max(len(s[0]), 1))
                run.series[key].extend(*s)
        return run

    def export_csv(self):
        runs = self.dm.runs
        if not runs or self.recording:
            self.statusBar().showMessage("내보낼 기록이 없습니다.")
            return
        index = len(runs) - 1
        if len(runs) > 1:
            labels = [f"런 #{r.number}" for r in runs]
            label, ok = QInputDialog.getItem(self, "CSV 내보내기", "내보낼 런:", labels, len(labels) - 1, False)
            if not ok:
                return
            index = labels.index(label)
        run = self._run_with_calcs(index)
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
        page.display_added.connect(self._mark_dirty)
        page.display_removed.connect(self._mark_dirty)
        page.start_requested.connect(self.on_start_card)
        self._mark_dirty()
        idx = self.pages.addTab(page, f"페이지 {self.pages.count() + 1}")
        self.pages.setCurrentIndex(idx)
        return page

    TEMPLATES = {"그래프 + 표": ("그래프", "테이블"), "그래프 두 개": ("그래프", "그래프"),
                 "숫자 + 미터": ("숫자", "미터"), "그래프 + 표 + 숫자 + 미터": ("그래프", "테이블", "숫자", "미터")}

    def on_start_card(self, card: str, button: QWidget):
        if card == "sensor":
            self.apply_template(("그래프", "테이블"))
            self.scan_devices()
        elif card == "open":
            self.open_experiment()
        elif card == "help":
            self.about()
        elif card == "templates":
            menu = QMenu(self)
            for name, kinds in self.TEMPLATES.items():
                menu.addAction(name, lambda k=kinds: self.apply_template(k))
            menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def apply_template(self, kinds):
        page = self.pages.currentWidget()
        for kind in kinds:
            page.add_display(kind)

    def rename_page(self, index: int):
        if index < 0:
            return
        name, ok = QInputDialog.getText(self, "페이지 이름", "새 이름:", text=self.pages.tabText(index))
        if ok and name.strip():
            self.pages.setTabText(index, name.strip())
            self.sync_tab_row()
            self._mark_dirty()

    def close_page(self, index: int):
        if self.pages.count() > 1:  # always keep one page
            self.pages.widget(index).deleteLater()
            self.pages.removeTab(index)
            self._mark_dirty()

    def add_display(self, kind: str):
        self.pages.currentWidget().add_display(kind)

    # --- sensors & recording ---------------------------------------------
    def scan_devices(self, wait=False):
        """Search in a worker thread (BLE takes seconds). wait=True blocks until done (tests)."""
        if self.recording or self.scanning:
            return
        self.scanning = True
        self.scan_btn.setEnabled(False)
        self.device_list.setEnabled(False)
        for s in self.sensors:
            s.close()  # old connections are replaced by the new scan
        self.hw_status.setText("장치 검색 중…")
        self.statusBar().showMessage("장치 검색 중… (블루투스 검색은 5초 정도 걸립니다)")
        thread = threading.Thread(target=lambda: self.scan_done.emit(*discovery.scan_all()),
                                  name="scan", daemon=True)
        thread.start()
        if wait:
            thread.join()
            QApplication.processEvents()  # deliver the queued scan_done

    def _on_scan_done(self, sensors, warnings):
        self.scanning = False
        self.scan_btn.setEnabled(True)
        self.sensors = sensors
        for s in sensors:
            s.on_error = self.sensor_error.emit
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
        msg = f"장치 {len(self.sensors)}개 발견"
        self.hw_status.setText(msg)
        self.hw_hint.setVisible(not self.sensors)
        self.statusBar().showMessage(msg + (" — " + " / ".join(warnings) if warnings else ""))
        if warnings:
            self.device_list.setToolTip("\n".join(warnings))

    def _on_sensor_error(self, message: str):
        if self.recording:
            self.toggle_record()
        self.statusBar().showMessage(f"센서 오류로 기록을 멈췄습니다: {message}")
        QMessageBox.warning(self, "센서 오류", message)

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
        if hasattr(frame.body, "title_changed"):
            frame.body.title_changed.connect(self._mark_dirty)
        frame.set_measurements(self.available_measurements())
        frame.refresh(self.dm)

    def refresh_displays(self):
        page = self.pages.currentWidget()
        if page:
            for frame in page.displays:
                frame.refresh(self.dm)

    @property
    def stop_after(self) -> float | None:
        return self.conditions.stop_after

    def _on_samples(self, sensor_id, t, values):  # called from sensor threads
        gate = self.gate
        out = gate.filter(sensor_id, t, values) if gate else (t, values)
        if out is None:
            return
        t, values = out
        for mid, y in values.items():
            self.dm.append(f"{sensor_id}:{mid}", t, y)

    def toggle_record(self):
        if not self.recording:
            sensors = self.active_sensors()
            if not sensors:
                self.statusBar().showMessage("기록할 센서가 없습니다. '장치 검색' 후 센서를 선택하세요.")
                return
            run = self.dm.start_run()
            self.gate = Gate(self.conditions)
            self._mark_dirty()
            rate = SAMPLE_RATES_HZ[self.rate_combo.currentIndex()]
            self.running_sensors = sensors
            for sensor in sensors:
                sensor.start(rate, self._on_samples)
            self.recording = True
            self.elapsed.start()
            self.clock.start()
            self.record_btn.setText("정지")
            self.record_btn.setIcon(icons.icon("stop"))
            self.timer_label.setProperty("recording", True)
            self.timer_label.style().polish(self.timer_label)
            self.statusBar().showMessage(f"기록 중 — 런 #{run.number}, {rate} Hz")
        else:
            for sensor in self.running_sensors:
                sensor.stop()
            self.dm.stop_run()
            self.recording = False
            self.clock.stop()
            self.refresh_displays()
            self.record_btn.setText("기록")
            self.record_btn.setIcon(icons.icon("record"))
            self.timer_label.setProperty("recording", False)
            self.timer_label.style().polish(self.timer_label)
            self.statusBar().showMessage(f"정지 — 런 {len(self.dm.runs)}개 기록됨")
        self.rate_combo.setEnabled(not self.recording)
        self.device_list.setEnabled(not self.recording and bool(self.sensors))

    def _tick(self):
        s = self.elapsed.elapsed() / 1000
        gate = self.gate
        if gate and gate.triggered:  # start condition met: the run's clock starts now
            gate.triggered = False
            self.elapsed.restart()
            s = 0.0
        waiting = gate is not None and gate.t0 is None
        self.elapsed_label.setText("대기 중…" if waiting else f"{int(s // 60):02d}:{s % 60:05.2f}")
        if (self.stop_after and not waiting and s >= self.stop_after) or (gate and gate.stop_hit):
            self.toggle_record()  # auto-stop reached
            return
        self.refresh_displays()

    def set_recording_conditions(self):
        items = [(k, m.label) for k, (_, m) in self.available_measurements().items()]
        dlg = ConditionsDialog(self, items, self.conditions)
        if dlg.exec() != QDialog.Accepted:
            return
        self.conditions = dlg.result_conditions()
        c = self.conditions
        parts = ["시작: " + ("측정값 조건" if c.start else "바로"),
                 "정지: " + ("직접" if not c.stop else f"{c.stop.value:g}초 후" if c.stop.kind == "time" else "측정값 조건")]
        self.statusBar().showMessage("기록 조건 — " + ", ".join(parts))

    def delete_last_run(self):
        if self.recording or not self.dm.runs:
            self.statusBar().showMessage("삭제할 런이 없습니다." if not self.recording else "기록 중에는 삭제할 수 없습니다.")
            return
        n = self.dm.runs[-1].number
        if QMessageBox.question(self, "런 삭제", f"런 #{n}을(를) 삭제할까요? 되돌릴 수 없습니다.") != QMessageBox.Yes:
            return
        self.dm.delete_last_run()
        self._mark_dirty()
        self.update_measurements()
        self.statusBar().showMessage(f"런 #{n} 삭제됨 — 남은 런 {len(self.dm.runs)}개")

    def show_data_summary(self):
        """Table of how many samples each measurement has in each run."""
        runs = self.dm.runs
        if not runs:
            self.statusBar().showMessage("요약할 기록이 없습니다.")
            return
        names = {k: v[1].label for k, v in self._all_measurements().items()}
        keys = sorted({k for r in runs for k in r.series})
        dlg = QDialog(self)
        dlg.setWindowTitle("데이터 요약")
        table = QTableWidget(len(keys), len(runs))
        table.setHorizontalHeaderLabels([f"런 #{r.number}" for r in runs])
        table.setVerticalHeaderLabels([names.get(k, k) for k in keys])
        for i, k in enumerate(keys):
            for j, r in enumerate(runs):
                s = r.series.get(k)
                table.setItem(i, j, QTableWidgetItem(str(s.n) if s else "—"))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("측정값별 샘플 수"))
        lay.addWidget(table)
        dlg.resize(560, 340)
        dlg.exec()

    def not_ready(self):
        QMessageBox.information(self, "미구현", "이 기능은 아직 구현되지 않았습니다.")

    def about(self):
        QMessageBox.about(self, "OpenPASCO",
                          "OpenPASCO — Linux용 PASCO 데이터 수집 프로그램 (개발 중)\n"
                          "개인·비상업·교육 목적")
