"""Experiment files (.opasco = SQLite) and CSV export. No Qt; pure data in, data out."""
import csv
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np

from openpasco.core.data_manager import Run, Series
from openpasco.hardware.base import Measurement

FORMAT_VERSION = 1

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE runs(number INTEGER PRIMARY KEY, started TEXT NOT NULL);
CREATE TABLE series(run INTEGER NOT NULL REFERENCES runs(number), key TEXT NOT NULL,
                    t BLOB NOT NULL, y BLOB NOT NULL, PRIMARY KEY(run, key));
"""


def save(path, runs: list[Run], layout: dict, measurements: dict[str, tuple[str, Measurement]]):
    """Write a complete experiment. layout is JSON-serialisable (pages/displays/rate...).
    measurements: key -> (sensor name, Measurement), so files open without the hardware."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")  # atomic replace: a crash never corrupts an existing file
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    try:
        db.executescript(SCHEMA)
        meta = {
            "version": FORMAT_VERSION,
            "layout": layout,
            "measurements": {k: {"sensor": s, **asdict(m)} for k, (s, m) in measurements.items()},
        }
        db.executemany("INSERT INTO meta VALUES(?,?)", [(k, json.dumps(v)) for k, v in meta.items()])
        for run in runs:
            db.execute("INSERT INTO runs VALUES(?,?)", (run.number, run.started.isoformat()))
            for key, s in run.series.items():
                t, y = s.view()
                db.execute("INSERT INTO series VALUES(?,?,?,?)",
                           (run.number, key, np.asarray(t, "<f8").tobytes(), np.asarray(y, "<f8").tobytes()))
        db.commit()
    except BaseException:
        db.close()
        tmp.unlink(missing_ok=True)
        raise
    db.close()
    tmp.replace(path)


def load(path):
    """Return (runs, layout, measurements). Raises ValueError for files that are not valid experiments."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        meta = {k: json.loads(v) for k, v in db.execute("SELECT key, value FROM meta")}
        if meta.get("version") != FORMAT_VERSION:
            raise ValueError(f"지원하지 않는 파일 버전: {meta.get('version')}")
        runs = []
        for number, started in db.execute("SELECT number, started FROM runs ORDER BY number"):
            run = Run(number, datetime.fromisoformat(started))
            for key, t, y in db.execute("SELECT key, t, y FROM series WHERE run=?", (number,)):
                t, y = np.frombuffer(t, "<f8"), np.frombuffer(y, "<f8")
                if len(t) != len(y):
                    raise ValueError(f"손상된 데이터: 런 {number}, {key}")
                s = Series(max(len(t), 1))
                s.extend(t, y)
                run.series[key] = s
            runs.append(run)
        meas = {}
        for k, d in meta["measurements"].items():
            sensor = d.pop("sensor")
            meas[k] = (sensor, Measurement(**d))
        return runs, meta["layout"], meas
    except (sqlite3.DatabaseError, KeyError, TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"올바른 OpenPASCO 실험 파일이 아닙니다: {e}") from e
    finally:
        db.close()


def export_csv(path, run: Run, measurements: dict[str, tuple[str, Measurement]]):
    """One run -> CSV. Series with different time bases go in separate column pairs side by side."""
    keys = sorted(run.series)
    cols, headers = [], []
    for k in keys:
        t, y = run.series[k].view()
        label = measurements[k][1].label if k in measurements else k
        headers += [f"시간 ({k}) (s)", label]
        cols += [t, y]
    n = max((len(c) for c in cols), default=0)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel reads Korean correctly
        w = csv.writer(f)
        w.writerow(headers)
        for i in range(n):
            w.writerow([f"{c[i]:.9g}" if i < len(c) else "" for c in cols])
