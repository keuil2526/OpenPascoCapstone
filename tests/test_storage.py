import csv
import sqlite3
from datetime import datetime

import numpy as np
import pytest

from openpasco.core.data_manager import Run, Series
from openpasco.hardware.base import Measurement
from openpasco.storage import experiment_storage as st

M = {"s:x": ("센서", Measurement("x", "위치", "m", -1, 1))}


def make_run(n=3, number=1):
    r = Run(number, datetime(2026, 11, 18, 9, 0))
    s = Series()
    s.extend(np.arange(n) * 0.1, np.arange(n) * 2.0)
    r.series["s:x"] = s
    return r


def test_roundtrip(tmp_path):
    p = tmp_path / "a.opasco"
    st.save(p, [make_run(), make_run(5, 2)], {"pages": [{"name": "실험", "displays": []}]}, M)
    runs, layout, meas = st.load(p)
    assert len(runs) == 2 and layout["pages"][0]["name"] == "실험"
    t, y = runs[0].series["s:x"].view()
    assert np.allclose(t, [0, .1, .2]) and np.allclose(y, [0, 2, 4])
    assert meas["s:x"] == M["s:x"]
    assert runs[0].started == datetime(2026, 11, 18, 9, 0)


def test_load_rejects_garbage(tmp_path):
    p = tmp_path / "bad.opasco"
    p.write_bytes(b"not a database at all")
    with pytest.raises(ValueError):
        st.load(p)
    q = tmp_path / "other.db"
    sqlite3.connect(q).executescript("CREATE TABLE x(a);")
    with pytest.raises(ValueError):
        st.load(q)


def test_failed_save_keeps_old_file(tmp_path):
    p = tmp_path / "a.opasco"
    st.save(p, [make_run()], {}, M)
    before = p.read_bytes()
    with pytest.raises(TypeError):
        st.save(p, [make_run()], {"bad": object()}, M)  # layout not JSON-serialisable
    assert p.read_bytes() == before and not list(tmp_path.glob("*.tmp"))


def test_csv_export(tmp_path):
    p = tmp_path / "a.csv"
    run = make_run()
    s2 = Series()
    s2.extend(np.array([0.0]), np.array([9.0]))
    run.series["s:z"] = s2  # shorter series -> blank cells
    st.export_csv(p, run, M)
    rows = list(csv.reader(open(p, encoding="utf-8-sig")))
    assert rows[0] == ["시간 (s:x) (s)", "위치 (m)", "시간 (s:z) (s)", "s:z"]
    assert rows[1] == ["0", "0", "0", "9"] and rows[3] == ["0.2", "4", "", ""]
