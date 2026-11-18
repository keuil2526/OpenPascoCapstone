import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()  # keep QSettings out of the real ~/.config

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from gui.main_window import DISPLAY_MIME, MainWindow
from gui.widgets.displays import DISPLAY_TYPES


@pytest.fixture
def win():
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("OpenPASCO-test")
    w = MainWindow()
    yield w
    w.close()


def test_starts_with_one_page(win):
    assert win.pages.count() == 1


def test_add_and_remove_displays(win):
    page = win.pages.currentWidget()
    frames = [page.add_display(kind) for kind in DISPLAY_TYPES]
    assert len(page.displays) == 4
    assert not page.hint.isVisibleTo(page)
    page.remove_display(frames[0])
    assert len(page.displays) == 3


def test_pages_last_page_cannot_close(win):
    win.add_page()
    assert win.pages.count() == 2
    win.close_page(1)
    win.close_page(0)
    assert win.pages.count() == 1


def test_record_needs_sensor(win):
    win.toggle_record()
    assert not win.recording and not win.dm.runs


def test_record_toggle_locks_rate(win):
    win.scan_devices()
    win.toggle_record()
    assert win.recording and not win.rate_combo.isEnabled()
    win.toggle_record()
    assert not win.recording and win.rate_combo.isEnabled()


def test_new_experiment_resets(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win.scan_devices()
    win.add_page()
    win.toggle_record()
    win.new_experiment()
    assert not win.dm.runs
    assert win.pages.count() == 1 and not win.recording


def _drop(page, payload: bytes):
    mime = QMimeData()
    mime.setData(DISPLAY_MIME, payload)
    ev = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    page.dropEvent(ev)


def test_drop_adds_display_and_rejects_unknown(win):
    page = win.pages.currentWidget()
    _drop(page, "그래프".encode())
    _drop(page, b"bogus")
    assert [f.body.__class__.__name__ for f in page.displays] == ["GraphDisplay"]


def test_palette_mime_carries_kind(win):
    item = win.display_list.item(1)
    mime = win.display_list.mimeData([item])
    assert bytes(mime.data(DISPLAY_MIME)).decode() == item.text()


def test_rename_page(win, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("  운동 실험 ", True))
    win.rename_page(0)
    assert win.pages.tabText(0) == "운동 실험"
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("   ", True))
    win.rename_page(0)
    assert win.pages.tabText(0) == "운동 실험"


def test_displays_survive_relayout(win):
    page = win.pages.currentWidget()
    frames = [page.add_display("숫자") for _ in range(3)]
    page.remove_display(frames[1])
    QApplication.processEvents()  # run deleteLater on old splitters
    assert all(f.isVisibleTo(page) for f in (frames[0], frames[2]))


def test_meter_angle_clamps():
    from gui.widgets.displays import Meter
    m = Meter(0, 10)
    assert m._angle(0) == 210 and m._angle(10) == -30 and m._angle(5) == 90
    assert m._angle(-5) == m._angle(0) and m._angle(99) == m._angle(10)


def test_dark_mode_restyles_plots(win):
    page = win.pages.currentWidget()
    plot = page.add_display("그래프").body
    win.act_dark.setChecked(True)
    dark_bg = plot.backgroundBrush().color().lightness()
    win.act_dark.setChecked(False)
    assert dark_bg < 100 < plot.backgroundBrush().color().lightness()


@pytest.mark.parametrize("value", [None, 3.7, -100])
def test_meter_paints_without_error(win, capfd, value):
    from gui.widgets.displays import Meter
    m = Meter(0, 10, "N")
    m.resize(200, 180)
    m.set_value(value)
    m.grab()  # runs paintEvent; PySide prints (not raises) errors from Python overrides
    assert "Error calling Python override" not in capfd.readouterr().err


def test_new_experiment_cancel_keeps_data(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    win.scan_devices()
    win.toggle_record()
    win.toggle_record()
    win.new_experiment()
    assert len(win.dm.runs) == 1


def test_recording_end_to_end(win):
    import time
    win.scan_devices()
    win.rate_combo.setCurrentText("100 Hz")
    page = win.pages.currentWidget()
    graph, digits = page.add_display("그래프"), page.add_display("숫자")
    assert graph.key == "sim-motion:position"  # first measurement auto-selected
    win.toggle_record()
    time.sleep(0.3)
    win.toggle_record()
    t, y = win.dm.latest(graph.key)
    assert 15 < len(t) < 60 and abs(t[1] - t[0] - 0.01) < 1e-12
    assert len(graph.body.curve.getData()[0]) == len(t)
    assert digits.body.value.text() != "— — —"


def test_unchecked_sensor_not_recorded(win):
    from PySide6.QtCore import Qt
    win.scan_devices()
    win.device_list.item(1).setCheckState(Qt.Unchecked)  # temperature sensor off
    frame = win.pages.currentWidget().add_display("테이블")
    assert all(not k.startswith("sim-temp") for k in frame.measurements)
    win.toggle_record()
    win.toggle_record()
    assert all(not k.startswith("sim-temp") for k in win.dm.runs[-1].series)
