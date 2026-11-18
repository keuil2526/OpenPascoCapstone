"""OpenPASCO main window: pages of displays, side tool panel, recording control bar."""
from PySide6.QtCore import QElapsedTimer, QMimeData, QSettings, Qt, QTimer
import pyqtgraph as pg
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDockWidget, QHBoxLayout, QInputDialog,
    QLabel, QListWidget, QMainWindow, QMessageBox, QPushButton, QSplitter, QStyle,
    QTabWidget, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from gui.widgets.displays import DISPLAY_TYPES, DisplayFrame, style_plot

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
            for frame in self.displays[r:r + GRID_COLUMNS]:
                row.addWidget(frame)
            root.addWidget(row)
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

        self.pages = QTabWidget(tabsClosable=True, movable=True, documentMode=True)
        self.pages.tabCloseRequested.connect(self.close_page)
        self.pages.tabBarDoubleClicked.connect(self.rename_page)
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
        self.act_open = act("열기…", self.not_ready, QKeySequence.Open, QStyle.SP_DialogOpenButton)
        self.act_save = act("저장", self.not_ready, QKeySequence.Save, QStyle.SP_DialogSaveButton)
        self.act_export = act("CSV 내보내기…", self.not_ready)
        self.act_quit = act("종료", self.close, QKeySequence.Quit)
        self.act_add_page = act("페이지 추가", self.add_page, "Ctrl+T", QStyle.SP_FileDialogNewFolder)
        self.act_rename_page = act("페이지 이름 바꾸기…",
                                   lambda: self.rename_page(self.pages.currentIndex()), "F2")
        self.act_record = act("기록 / 정지", self.toggle_record, "Ctrl+R", QStyle.SP_MediaPlay)

        mb = self.menuBar()
        file_menu = mb.addMenu("파일(&F)")
        for a in (self.act_new, self.act_open, self.act_save, None, self.act_export, None, self.act_quit):
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
        self.device_list.addItem("연결된 장치 없음")
        self.device_list.setEnabled(False)
        layout.addWidget(self.device_list, 1)
        scan = QPushButton("장치 검색", clicked=self.not_ready)
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
        self.clock = QTimer(self, interval=100, timeout=self._tick)

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
        s = QSettings()
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState())
        super().closeEvent(event)

    # --- actions ----------------------------------------------------------
    def new_experiment(self):
        if self.recording:
            self.toggle_record()
        self.pages.clear()
        self.add_page()
        self.statusBar().showMessage("새 실험")

    def add_page(self) -> Page:
        page = Page()
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

    def toggle_record(self):
        self.recording = not self.recording
        if self.recording:
            self.elapsed.start()
            self.clock.start()
            self.record_btn.setText("■ 정지")
            self.record_btn.setStyleSheet(RECORDING_STYLE)
            self.statusBar().showMessage("기록 중 (연결된 센서 없음 — 데이터 엔진 미구현)")
        else:
            self.clock.stop()
            self.record_btn.setText("● 기록")
            self.record_btn.setStyleSheet(IDLE_STYLE)
            self.statusBar().showMessage("정지")
        self.rate_combo.setEnabled(not self.recording)

    def _tick(self):
        s = self.elapsed.elapsed() / 1000
        self.elapsed_label.setText(f"{int(s // 60):02d}:{s % 60:04.1f}")

    def not_ready(self):
        QMessageBox.information(self, "미구현", "이 기능은 아직 구현되지 않았습니다.")

    def about(self):
        QMessageBox.about(self, "OpenPASCO",
                          "OpenPASCO — Linux용 PASCO 데이터 수집 프로그램 (개발 중)\n"
                          "개인·비상업·교육 목적")
