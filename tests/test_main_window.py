import numpy as np
import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()  # keep QSettings out of the real ~/.config

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from openpasco.gui.main_window import DISPLAY_MIME, MainWindow
from openpasco.gui.widgets.displays import DISPLAY_TYPES


@pytest.fixture
def win(monkeypatch):
    from openpasco.gui import main_window
    from openpasco.hardware import simulated
    # never touch real Bluetooth in tests
    monkeypatch.setattr(main_window.discovery, "scan_all", lambda: (simulated.scan(), []))
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("OpenPASCO-test")
    w = MainWindow()
    yield w
    w.dirty = False  # closing a modified window would open a modal prompt
    w.close()


def test_starts_with_one_page(win):
    assert win.pages.count() == 1


def test_add_and_remove_displays(win):
    page = win.pages.currentWidget()
    frames = [page.add_display(kind) for kind in DISPLAY_TYPES]
    assert len(page.displays) == len(DISPLAY_TYPES)
    assert not page.hint.isVisibleTo(page)
    page.remove_display(frames[0])
    assert len(page.displays) == len(DISPLAY_TYPES) - 1


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
    win.scan_devices(wait=True)
    win.toggle_record()
    assert win.recording and not win.rate_combo.isEnabled()
    win.toggle_record()
    assert not win.recording and win.rate_combo.isEnabled()


def test_new_experiment_resets(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    win.scan_devices(wait=True)
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
    from openpasco.gui.widgets.displays import Meter
    m = Meter(0, 10)
    assert m._angle(0) == 210 and m._angle(10) == -30 and m._angle(5) == 90
    assert m._angle(-5) == m._angle(0) and m._angle(99) == m._angle(10)


def test_dark_mode_restyles_plots(win):
    page = win.pages.currentWidget()
    plot = page.add_display("그래프").body.plot
    win.act_dark.setChecked(True)
    dark_bg = plot.backgroundBrush().color().lightness()
    win.act_dark.setChecked(False)
    assert dark_bg < 100 < plot.backgroundBrush().color().lightness()


@pytest.mark.parametrize("value", [None, 3.7, -100])
def test_meter_paints_without_error(win, capfd, value):
    from openpasco.gui.widgets.displays import Meter
    m = Meter(0, 10, "N")
    m.resize(200, 180)
    m.set_value(value)
    m.grab()  # runs paintEvent; PySide prints (not raises) errors from Python overrides
    assert "Error calling Python override" not in capfd.readouterr().err


def test_new_experiment_cancel_keeps_data(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Cancel)
    win.scan_devices(wait=True)
    win.toggle_record()
    win.toggle_record()
    win.new_experiment()
    assert len(win.dm.runs) == 1


def test_recording_end_to_end(win):
    import time
    win.scan_devices(wait=True)
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
    win.scan_devices(wait=True)
    win.device_list.item(1).setCheckState(Qt.Unchecked)  # temperature sensor off
    frame = win.pages.currentWidget().add_display("테이블")
    assert all(not k.startswith("sim-temp") for k in frame.measurements)
    win.toggle_record()
    win.toggle_record()
    assert all(not k.startswith("sim-temp") for k in win.dm.runs[-1].series)


def _record_a_bit(win):
    import time
    win.scan_devices(wait=True)
    win.rate_combo.setCurrentText("100 Hz")
    page = win.pages.currentWidget()
    page.add_display("그래프")
    page.add_display("숫자").selector.setCurrentIndex(2)
    win.toggle_record()
    time.sleep(0.2)
    win.toggle_record()


def test_save_open_roundtrip(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    p = str(tmp_path / "e.cap")
    _record_a_bit(win)
    win.pages.setTabText(0, "내 실험")
    from openpasco.core.conditions import Condition, Conditions
    win.conditions = Conditions(Condition("measure", "sim-motion:position", "<", 0.5), Condition("time", value=3))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (p, ""))
    win.save_experiment()
    assert win.path.name == "e.cap" and "e.cap" in win.windowTitle()
    n = len(win.dm.latest("sim-motion:position")[0])

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    win.new_experiment()
    assert not win.dm.runs and win.path is None
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (p, ""))
    win.open_experiment()  # no sensors scanned: file must open on its own
    assert win.pages.tabText(0) == "내 실험" and win.rate_combo.currentText() == "100 Hz"
    assert win.conditions.start.op == "<" and win.conditions.stop_after == 3
    graph, digits = win.pages.currentWidget().displays
    assert graph.key == "sim-motion:position" and digits.key == "sim-temp:temperature"
    assert len(graph.body.curve.getData()[0]) == n
    assert digits.body.value.text() != "— — —"


def test_open_bad_file_keeps_state(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    bad = tmp_path / "bad.cap"
    bad.write_bytes(b"junk")
    _record_a_bit(win)
    shown = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(bad), ""))
    win.open_experiment()
    assert shown and len(win.dm.runs) == 1


def test_export_csv(win, tmp_path, monkeypatch):
    import csv
    from PySide6.QtWidgets import QFileDialog
    _record_a_bit(win)
    p = str(tmp_path / "r.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (p, ""))
    win.export_csv()
    rows = list(csv.reader(open(p, encoding="utf-8-sig")))
    assert "위치 (m)" in rows[0] and len(rows) > 10


def _graph_with_data(win, t, y):
    from openpasco.hardware.base import Measurement
    g = win.pages.currentWidget().add_display("그래프").body
    g.show(Measurement("x", "위치", "m", 0, 1), (t, y))
    return g


def _pick(g, name):
    g.analysis.setCurrentIndex(g.analysis.findText(name))  # triggers _analyze synchronously


def test_graph_stats_fit_and_range(win):
    import numpy as np
    t = np.linspace(0, 10, 101)
    g = _graph_with_data(win, t, 2 * t + 1)
    _pick(g, "통계")
    assert "n=101" in g.result.text() and "최대=21" in g.result.text()
    g.range_check.setChecked(True)
    g.region.setRegion((2, 4))
    g._analyze()
    assert "n=21" in g.result.text()
    _pick(g, "선형")
    assert "m=2" in g.result.text() and g.overlay.getData()[0] is not None
    assert g.overlay.getData()[0].min() >= 2 - 1e-9 and g.overlay.getData()[0].max() <= 4 + 1e-9


def test_graph_derivative_and_errors(win):
    import numpy as np
    t = np.linspace(0, 10, 101)
    g = _graph_with_data(win, t, t**2)
    _pick(g, "미분")
    assert abs(g.curve.getData()[1][50] - 10) < 0.2
    g.range_check.setChecked(True)
    g.region.setRegion((100, 200))  # outside data
    _pick(g, "통계")
    assert "데이터가 없습니다" in g.result.text()
    g.show(None, None)  # data cleared: no crash, empty result
    assert g.result.text() == ""


def test_open_capstone_file_is_a_copy(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from tests.test_capstone_import import make_cap
    p = make_cap(tmp_path / "lab.cap")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(p), ""))
    win.open_experiment()
    assert win.pages.tabText(0) == "lab" and "복사본" in win.windowTitle() and win.path is None  # Save As needed
    graph = win.pages.currentWidget().displays[0]
    assert graph.key == "cap:Force" and len(graph.body.curve.getData()[0]) == 2  # newest run (#2) has 2 samples


def test_sensor_error_stops_recording(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    win.scan_devices(wait=True)
    win.toggle_record()
    win.sensors[0].on_error("연결 끊김")  # called from a "sensor thread"; here the main thread
    QApplication.processEvents()
    assert not win.recording and shown == ["연결 끊김"]
    assert "연결 끊김" in win.statusBar().currentMessage()


def test_scan_warnings_shown_and_rescan_closes_old(win, monkeypatch):
    from openpasco.gui import main_window
    from openpasco.hardware import simulated
    closed = []
    win.scan_devices(wait=True)
    win.sensors[0].close = lambda: closed.append(1)
    monkeypatch.setattr(main_window.discovery, "scan_all", lambda: (simulated.scan(), ["BLE 실패"]))
    win.scan_devices(wait=True)
    assert closed == [1] and "BLE 실패" in win.statusBar().currentMessage()
    assert win.scan_btn.isEnabled() and not win.scanning


def _record_motion(win, seconds=0.25):
    import time
    win.scan_devices(wait=True)
    win.rate_combo.setCurrentText("100 Hz")
    win.toggle_record()
    time.sleep(seconds)
    win.toggle_record()


def test_calculation_end_to_end(win):
    import numpy as np
    from openpasco.core.calculation import CalcError
    _record_motion(win)
    calc = win.create_calc("2배 위치", "m", "[위치] * 2")
    assert calc.refs == {"위치": "sim-motion:position"} and "calc:2배 위치" in win.known
    t, y = win.dm.latest("calc:2배 위치")
    assert np.allclose(y, 2 * win.dm.latest("sim-motion:position")[1])
    page = win.pages.currentWidget()
    graph = page.add_display("그래프")
    graph.selector.setCurrentIndex(graph.selector.findData("calc:2배 위치"))
    graph.refresh(win.dm)
    assert len(graph.body.curve.getData()[0]) == len(t)
    # chained calculation, and validation errors
    win.create_calc("제곱", "", "[2배 위치] ** 2")
    for name, expr, msg in [("", "[위치]", "이름"), ("위치", "[위치]", "이미 사용"),
                            ("x", "[없는것]", "찾을 수 없"), ("y", "[위치] +", "문법"),
                            ("z", "1 + 2", "하나 이상"), ("2배 위치", "[위치]", "이미 사용")]:
        with pytest.raises(CalcError, match=msg):
            win.create_calc(name, "", expr)


def test_calculation_saved_and_restored(win, tmp_path, monkeypatch):
    import numpy as np
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    _record_motion(win)
    win.create_calc("v2", "", "[속도] ** 2")
    frame = win.pages.currentWidget().add_display("숫자")
    frame.selector.setCurrentIndex(frame.selector.findData("calc:v2"))
    expected = win.dm.latest("calc:v2")[1][-1]
    p = str(tmp_path / "c.cap")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (p, ""))
    win.save_experiment()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    win.new_experiment()
    assert not win.dm.calcs
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (p, ""))
    win.open_experiment()
    digits = win.pages.currentWidget().displays[0]
    assert digits.key == "calc:v2" and np.isclose(win.dm.latest("calc:v2")[1][-1], expected)


def test_corrupt_saved_calcs_are_skipped(win):
    bad = [{"key": "calc:a", "name": "a", "unit": "", "expr": "[x] +", "refs": {}},   # syntax error
           {"key": "calc:b", "name": "b", "unit": "", "expr": "[x]", "refs": {"y": "k"}},  # stray ref
           {"key": "oops"}, "junk",
           {"key": "calc:c", "name": "c", "unit": "", "expr": "[c] + 1", "refs": {"c": "calc:c"}}]
    assert win._restore_calcs(bad + [None]) == 5  # the self-referencing one is accepted ...
    assert win.dm.latest("calc:c") is None  # ... but evaluating it does not crash or hang


def test_calc_dialog_keeps_open_on_error(win):
    from PySide6.QtWidgets import QTableWidgetItem
    from openpasco.gui.widgets.calc_dialog import CalcDialog
    win.scan_devices(wait=True)
    dlg = CalcDialog(win, ["위치"], win.create_calc)

    def line(row, text, unit=""):
        dlg.table.setItem(row, 0, QTableWidgetItem(text))
        dlg.table.setItem(row, 1, QTableWidgetItem(unit))

    line(0, "x = [위치] +")
    dlg.accept()
    assert dlg.result() == 0 and "문법" in dlg.status.text() and "1번째" in dlg.status.text()
    line(0, "k = 3")  # a constant line, used by the next line
    line(1, "x = k * [위치]", "m")
    dlg.accept()
    assert dlg.result() == 1 and "calc:x" in win.dm.calcs and "(3.0)" in win.dm.calcs["calc:x"].expr


def test_overlay_older_runs(win):
    import time
    win.scan_devices(wait=True)
    win.rate_combo.setCurrentText("100 Hz")
    frame = win.pages.currentWidget().add_display("그래프")
    g = frame.body
    for _ in range(3):  # three runs
        win.toggle_record()
        time.sleep(0.12)
        win.toggle_record()
    assert len(win.dm.runs) == 3 and g.older == []  # off by default
    g.older_check.setChecked(True)  # frame refetches immediately
    assert len(g.older) == 2 and g.older_names == ["런 #1", "런 #2"]
    n_newest = len(win.dm.latest(frame.key)[0])
    assert len(g.curve.getData()[0]) == n_newest
    g.older_check.setChecked(False)
    assert g.older == [] and g.older_names == []


def test_older_runs_with_calc_and_missing_data(win):
    import time
    win.scan_devices(wait=True)
    win.rate_combo.setCurrentText("100 Hz")
    for i in range(2):
        win.toggle_record()
        time.sleep(0.1)
        win.toggle_record()
    win.create_calc("c2", "", "[위치] * 2")
    older = win.dm.older_runs("calc:c2")
    assert [n for n, _, _ in older] == [1]
    assert win.dm.older_runs("sim-temp:nonexistent") == [] and win.dm.series("x", 99) is None


def test_dirty_flag_lifecycle(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    assert not win.dirty and win.windowTitle() == "제목 없음 — OpenPASCO"
    win.add_page()
    assert win.dirty and win.windowTitle().startswith("● ")
    p = str(tmp_path / "d.cap")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (p, ""))
    win.save_experiment()
    assert not win.dirty and win.windowTitle() == "d.cap — OpenPASCO"
    for change in (lambda: win.pages.currentWidget().add_display("숫자"),
                   lambda: win.pages.currentWidget().remove_display(win.pages.currentWidget().displays[0]),
                   lambda: win.close_page(1)):
        win._set_clean()
        change()
        assert win.dirty, change


def test_discard_prompt_save_discard_cancel(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    win.add_page()  # now dirty
    answers = iter([QMessageBox.Cancel, QMessageBox.Discard, QMessageBox.Save])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: next(answers))
    assert not win.confirm_discard("t") and win.dirty  # cancel
    assert win.confirm_discard("t") and win.dirty  # discard: caller proceeds, state untouched
    p = str(tmp_path / "s.cap")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (p, ""))
    assert win.confirm_discard("t") and not win.dirty and (tmp_path / "s.cap").exists()  # save
    win.add_page()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Save)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))  # user cancels the file dialog
    win.path = None
    assert not win.confirm_discard("t")  # Save chosen but not completed -> do not proceed


def test_close_event_respects_cancel(win, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox
    win.add_page()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Cancel)
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert not ev.isAccepted()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted()


def test_confirm_discard_stops_recording(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    win.scan_devices(wait=True)
    win.toggle_record()
    assert win.confirm_discard("t") and not win.recording


def test_delete_calc_and_dependents(win):
    from openpasco.core.calculation import CalcError
    _record_motion(win)
    win.create_calc("a", "", "[위치] * 2")
    win.create_calc("b", "", "[a] + 1")
    frame = win.pages.currentWidget().add_display("숫자")
    frame.selector.setCurrentIndex(frame.selector.findData("calc:a"))
    with pytest.raises(CalcError, match="b"):
        win.delete_calc("calc:a")  # b depends on a
    win.delete_calc("calc:b")
    win.delete_calc("calc:a")
    assert not win.dm.calcs and "calc:a" not in win.known
    assert frame.key == "sim-motion:position"  # display fell back to a recorded measurement


def test_csv_includes_calculations(win, tmp_path, monkeypatch):
    import csv
    from PySide6.QtWidgets import QFileDialog
    _record_motion(win)
    win.create_calc("두배", "m", "[위치] * 2")
    p = str(tmp_path / "c.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (p, ""))
    win.export_csv()
    rows = list(csv.reader(open(p, encoding="utf-8-sig")))
    hdr = rows[0]
    pos, dbl = hdr.index("위치 (m)"), hdr.index("두배 (m)")
    first = rows[5]
    assert float(first[dbl]) == pytest.approx(2 * float(first[pos]), rel=1e-6)
    assert len(win.dm.runs[-1].series) == 3 and not any("calc" in k for k in win.dm.runs[-1].series)  # run untouched


def _set_conditions(win, monkeypatch, conds):
    from PySide6.QtWidgets import QDialog
    from openpasco.gui import main_window as mw
    monkeypatch.setattr(mw.ConditionsDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(mw.ConditionsDialog, "result_conditions", lambda self: conds)
    win.set_recording_conditions()


def _wait_stopped(win, seconds=3):
    import time
    end = time.time() + seconds
    while win.recording and time.time() < end:  # the clock timer must stop it
        QApplication.processEvents()
        time.sleep(0.01)


def test_recording_conditions_auto_stop(win, monkeypatch):
    from openpasco.core.conditions import Condition, Conditions
    _set_conditions(win, monkeypatch, Conditions(stop=Condition("time", value=0.2)))
    assert win.stop_after == 0.2
    win.scan_devices(wait=True)
    win.toggle_record()
    _wait_stopped(win, 2)
    assert not win.recording and len(win.dm.runs) == 1
    _set_conditions(win, monkeypatch, Conditions())
    assert win.stop_after is None


def test_stop_condition_on_measurement(win, monkeypatch):
    from openpasco.core.conditions import Condition, Conditions
    win.scan_devices(wait=True)
    key = "sim-motion:position"
    _set_conditions(win, monkeypatch, Conditions(stop=Condition("measure", key, ">", -1e9)))  # always true
    win.toggle_record()
    _wait_stopped(win)
    assert not win.recording and len(win.dm.runs) == 1


def test_start_condition_zeroes_time(win, monkeypatch):
    import time
    from openpasco.core.conditions import Condition, Conditions
    win.scan_devices(wait=True)
    key = "sim-motion:position"
    _set_conditions(win, monkeypatch, Conditions(start=Condition("measure", key, ">", -1e9)))
    win.toggle_record()
    time.sleep(0.3)
    win.toggle_record()
    t, _ = win.dm.series(key)
    assert len(t) and t[0] == pytest.approx(0.0, abs=0.2) and (t >= 0).all()


def test_delete_last_run_and_numbering(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    _record_motion(win, 0.1)
    _record_motion(win, 0.1)
    assert [r.number for r in win.dm.runs] == [1, 2]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    win.delete_last_run()
    assert len(win.dm.runs) == 2
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win.delete_last_run()
    assert [r.number for r in win.dm.runs] == [1] and win.dirty
    win.toggle_record(); win.toggle_record()  # next run must not reuse a live number
    assert [r.number for r in win.dm.runs] == [1, 2]
    win.dm.runs[0].number = 7  # e.g. imported file with gaps
    win.toggle_record(); win.toggle_record()
    assert [r.number for r in win.dm.runs] == [7, 2, 8]
    win.dm.delete_last_run(); win.dm.delete_last_run(); win.dm.delete_last_run()
    assert win.dm.delete_last_run() is None  # nothing left


def test_data_summary_dialog(win, monkeypatch):
    from PySide6.QtWidgets import QDialog, QTableWidget
    seen = {}
    monkeypatch.setattr(QDialog, "exec", lambda self: seen.update(dlg=self))
    win.show_data_summary()
    assert not seen and "요약할 기록이 없습니다" in win.statusBar().currentMessage()
    _record_motion(win, 0.1)
    win.show_data_summary()
    table = seen["dlg"].findChild(QTableWidget)
    assert table.columnCount() == 1 and table.rowCount() == 3
    assert int(table.item(0, 0).text()) > 3 and table.horizontalHeaderItem(0).text() == "런 #1"


def test_palette_click_adds_display(win):
    win.display_list.itemClicked.emit(win.display_list.item(2))
    assert [f.kind for f in win.pages.currentWidget().displays] == ["숫자"]


def test_start_cards(win, monkeypatch):
    page = win.pages.currentWidget()
    assert page.hint.isVisibleTo(page)
    win.on_start_card("sensor", page.hint)  # graph + table, and a device search
    assert [f.kind for f in page.displays] == ["그래프", "테이블"] and not page.hint.isVisibleTo(page)
    win.scan_devices(wait=True)
    called = []
    monkeypatch.setattr(win, "open_experiment", lambda: called.append(1))
    win.on_start_card("open", page.hint)
    assert called


def test_bad_saved_conditions_are_ignored(win):
    for bad in (None, 5, {"start": {"kind": "x"}}, {"stop": {"kind": "time", "value": "abc"}}):
        c = win._conditions_from(bad)
        assert c.start is None and c.stop is None


def test_graph_title_saved_and_marks_dirty(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    g = win.pages.currentWidget().add_display("그래프")
    win._set_clean()
    g.body.title_edit.textEdited.emit("진자 실험")  # user typing marks the experiment as changed
    assert win.dirty
    g.body.title_edit.setText("진자 실험")
    assert win.layout_state()["pages"][0]["displays"][0]["title"] == "진자 실험"
    win.apply_layout(win.layout_state())
    assert win.pages.currentWidget().displays[0].body.title_edit.text() == "진자 실험"


def test_fft_finds_sine_frequency():
    from openpasco.gui.widgets.displays import FftDisplay
    t = np.arange(0, 2, 0.01)
    f, a = FftDisplay.spectrum(t, 3 * np.sin(2 * np.pi * 5 * t) + 10)
    assert abs(f[np.argmax(a)] - 5) < 0.5 and abs(a.max() - 3) < 0.3
    assert FftDisplay.spectrum([0, 1], [1, 2]) is None


def test_histogram_bins_cover_all_values():
    from openpasco.gui.widgets.displays import HistogramDisplay
    x, counts, w = HistogramDisplay.bins([1, 2, 2, 3, 3, 3, 4, 10])
    assert counts.sum() == 8 and w > 0
    assert HistogramDisplay.bins([]) is None


def test_bar_meter_fraction():
    from openpasco.gui.widgets.displays import BarMeterDisplay as B
    assert B.fraction(5, 0, 10) == 0.5 and B.fraction(99, 0, 10) == 1 and B.fraction(None, 0, 10) == 0
    assert B.fraction(1, 5, 5) == 0


def test_copy_page_image_puts_pixmap_on_clipboard(win):
    from PySide6.QtWidgets import QApplication
    QApplication.clipboard().clear()
    win.act_copy_page.trigger()
    assert not QApplication.clipboard().pixmap().isNull()
