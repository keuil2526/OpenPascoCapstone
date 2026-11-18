import struct
import zipfile
from pathlib import Path

import numpy as np
import pytest

from storage.capstone_import import load_cap

XML = """<DSProExperiment><Header Version="2.10.8"/>
<DataSource LongName="Force">{sets}</DataSource>
<DataSource LongName="Force"><DataSet DataGroupNumber="1"><DataSegmentElement>
 <DependentStorageElement StorageType="0" FileName="data\\b.tmp"/>
 <IndependentStorageElement StorageType="1" CacheDataCount="2" IntervalCacheInterval="0.5" IntervalCacheStartValue="0"/>
</DataSegmentElement></DataSet></DataSource>
<DataSource LongName="Manual"><DataSet DataGroupNumber="1"><DataSegmentElement>
 <DependentStorageElement StorageType="7" FileName="data/c.tmp"/><IndependentStorageElement StorageType="4" CacheDataCount="3"/>
</DataSegmentElement></DataSet></DataSource></DSProExperiment>"""
SET = """<DataSet DataGroupNumber="{run}"><DataSegmentElement>
 <DependentStorageElement StorageType="0" FileName="data/a{run}.tmp" DataOffsetValue="0"/>
 <IndependentStorageElement StorageType="1" CacheDataCount="{n}" IntervalCacheInterval="0.05" IntervalCacheStartValue="0.05"/>
</DataSegmentElement></DataSet>"""


def records(vals, pad=3):
    out = b"".join(struct.pack("<Id", 1, v) for v in vals)
    return out + b"\0" * 12 * pad  # real files are zero-padded


def make_cap(path: Path, **overrides):
    files = {"data/a1.tmp": records([1.0, 2.0, 3.0]), "data/a2.tmp": records([4.0, 5.0]),
             "data/b.tmp": records([7.0, 8.0]), "data/c.tmp": b"\0" * 8}
    files.update(overrides)
    sets = SET.format(run=1, n=3) + SET.format(run=2, n=2)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("main.xml", XML.format(sets=sets))
        for k, v in files.items():
            z.writestr(k, v)
    return path


def test_load_runs_times_values(tmp_path):
    r = load_cap(make_cap(tmp_path / "x.cap"))
    assert [run.number for run in r.runs] == [1, 2]
    t, y = r.runs[0].series["cap:Force"].view()
    assert np.allclose(t, [0.05, 0.10, 0.15]) and list(y) == [1.0, 2.0, 3.0]
    assert list(r.runs[1].series["cap:Force"].view()[1]) == [4.0, 5.0]
    assert r.skipped == 1  # the user-entered table (storage type 7)
    assert "cap:Force#2" in r.runs[0].series  # duplicate source name kept apart
    m = r.measurements["cap:Force"][1]
    assert (m.name, m.unit, m.minimum, m.maximum) == ("Force", "", 1.0, 5.0)


def test_invalid_flag_becomes_nan(tmp_path):
    bad = struct.pack("<Id", 1, 1.0) + struct.pack("<Id", 0, 99.0) + struct.pack("<Id", 1, 3.0)
    r = load_cap(make_cap(tmp_path / "x.cap", **{"data/a1.tmp": bad}))
    y = r.runs[0].series["cap:Force"].view()[1]
    assert y[0] == 1.0 and np.isnan(y[1]) and y[2] == 3.0


def test_truncated_data_file_is_skipped_with_warning(tmp_path):
    r = load_cap(make_cap(tmp_path / "x.cap", **{"data/a1.tmp": records([1.0], pad=0)}))
    assert [run.number for run in r.runs] == [1, 2] and "cap:Force" not in r.runs[0].series
    assert any("짧습니다" in w for w in r.warnings)


def test_rejects_non_cap_files(tmp_path):
    p = tmp_path / "bad.cap"
    p.write_bytes(b"hello")
    with pytest.raises(ValueError):
        load_cap(p)
    q = tmp_path / "other.cap"
    with zipfile.ZipFile(q, "w") as z:
        z.writestr("main.xml", "<Something/>")
    with pytest.raises(ValueError, match="Capstone"):
        load_cap(q)
    r = tmp_path / "noxml.cap"
    with zipfile.ZipFile(r, "w") as z:
        z.writestr("readme.txt", "x")
    with pytest.raises(ValueError):
        load_cap(r)


def test_huge_declared_count_does_not_allocate(tmp_path):
    p = tmp_path / "x.cap"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("main.xml", XML.format(sets=SET.format(run=1, n=10**12)))
    r = load_cap(p)  # warning, no crash / no memory blow-up
    assert not r.runs and r.warnings
