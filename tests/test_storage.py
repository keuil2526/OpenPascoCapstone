import csv
from datetime import datetime

import numpy as np
import pytest

from openpasco.core.data_manager import Run, Series
from openpasco.hardware.base import Measurement
from openpasco.storage import experiment_storage as st
from openpasco.storage.capstone_export import save_cap
from openpasco.storage.capstone_import import load_cap

M = {"s:x": ("센서", Measurement("x", "위치", "m", -1, 1))}


def make_run(n=3, number=1):
    r = Run(number, datetime(2026, 11, 18, 9, 0))
    s = Series()
    s.extend(np.arange(n) * 0.1, np.arange(n) * 2.0)
    r.series["s:x"] = s
    return r


def test_roundtrip(tmp_path):
    p = tmp_path / "a.cap"
    save_cap(p, [make_run(), make_run(5, 2)], M, {"pages": [{"name": "실험", "displays": []}]})
    res = load_cap(p)
    assert len(res.runs) == 2 and res.layout["pages"][0]["name"] == "실험"
    t, y = res.runs[0].series["s:x"].view()  # original key restored from openpasco.json
    assert np.allclose(t, [0, .1, .2]) and np.allclose(y, [0, 2, 4])
    sensor, m = res.measurements["s:x"]
    assert sensor == "센서" and (m.name, m.unit) == ("위치", "m")
    assert [r.number for r in res.runs] == [1, 2]


def test_plain_cap_has_no_layout_and_extra_member_is_optional(tmp_path):
    import zipfile
    p = tmp_path / "a.cap"
    save_cap(p, [make_run()], M)
    q = tmp_path / "plain.cap"  # same file without our member = what Capstone itself writes
    with zipfile.ZipFile(p) as src, zipfile.ZipFile(q, "w") as dst:
        for n in src.namelist():
            if n != "openpasco.json":
                dst.writestr(n, src.read(n))
    res = load_cap(q)
    assert res.layout is None and "cap:위치" in res.measurements
    bad = tmp_path / "bad.cap"  # damaged extra member: still opens as a plain .cap
    with zipfile.ZipFile(p) as src, zipfile.ZipFile(bad, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, b"{not json" if n == "openpasco.json" else src.read(n))
    assert load_cap(bad).layout is None


def test_uneven_times_use_mean_interval_with_warning(tmp_path):
    r = Run(1, datetime(2026, 11, 18))
    s = Series()
    s.extend(np.array([0.0, 0.1, 0.5]), np.array([1.0, 2.0, 3.0]))
    r.series["s:x"] = s
    warnings = save_cap(tmp_path / "u.cap", [r], M)
    assert warnings and "평균" in warnings[0]
    assert len(load_cap(tmp_path / "u.cap").runs[0].series["s:x"].view()[0]) == 3


def test_failed_save_keeps_old_file(tmp_path):
    p = tmp_path / "a.cap"
    save_cap(p, [make_run()], M)
    before = p.read_bytes()
    with pytest.raises(TypeError):
        save_cap(p, [make_run()], M, {"bad": object()})  # layout not JSON-serialisable
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


def test_capstone_origin_survives_resave(tmp_path):
    """A file opened from Capstone keeps its Hardware section and DataSource attributes when re-saved."""
    import zipfile
    from tests.test_capstone_import import make_cap
    src = make_cap(tmp_path / "orig.cap")
    with zipfile.ZipFile(src) as z:
        files = {n: z.read(n) for n in z.namelist()}
    files["main.xml"] = files["main.xml"].replace(
        b'<DataSource EUID="{F1}"', b'<Hardware><Interface Type="1"/></Hardware><DataSource EUID="{F1}"', 1)
    with zipfile.ZipFile(src, "w") as z:
        for n, v in files.items():
            z.writestr(n, v)
    res = load_cap(src)
    assert "<Interface" in res.origin["hardware"] and res.origin["attrs"]["cap:Force"]["EUID"] == "{F1}"
    save_cap(tmp_path / "out.cap", res.runs, res.measurements, {}, res.origin)
    again = load_cap(tmp_path / "out.cap")
    assert "<Interface" in again.origin["hardware"] and again.origin["attrs"]["cap:Force"]["EUID"] == "{F1}"
    with zipfile.ZipFile(tmp_path / "out.cap") as z:
        assert b'EUID="{F1}"' in z.read("main.xml") and b"<Hardware" in z.read("main.xml")
