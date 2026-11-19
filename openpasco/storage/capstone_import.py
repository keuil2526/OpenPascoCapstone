"""Read-only importer for PASCO Capstone .cap files (ZIP: main.xml + data/*.tmp).

Layout was derived from sample files, not from documentation (see docs/capstone_format.md):
  - each <DataSource LongName=...> holds one <DataSet> per run (DataGroupNumber = run number)
  - interval data sets (StorageType 0 / independent StorageType 1): time = start + interval * i,
    values = the first CacheDataCount 12-byte records (uint32 valid-flag, float64) of the data file
  - user-entered tables (dependent StorageType 7 / independent 4): DataCacheDataSize records of
    (uint32 type=2, uint32 byte length, UTF-16LE text); x = row number 1..N. Trailing bytes are ignored.
  - pages: <WorkbookPage Name> > <WorkbookItem> with a CSLineGraph / CSDataTable / CSDataDigits /
    CSBarMeter child and relative Position X/Y; we keep only display kinds in reading order.
    A display's measurement = first <BundleInput BundleMeasID> that equals a DataSource EUID
    (467/467 non-null links matched in samples; the time axis points at the master time measurement).
  - other storage types are skipped and counted
Units are numeric codes. Only codes whose sample values match the unit (checked against real
files, e.g. Force ~ -10..0, Position 0..0.7, gravity ~9.8) are translated; others stay empty.
"""
import json
import struct
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from openpasco.core.data_manager import Run, Series
from openpasco.hardware.base import Measurement

MAX_XML_BYTES = 200 * 1024 * 1024
MAX_DATA_BYTES = 512 * 1024 * 1024
MAX_EXTRA_BYTES = 20 * 1024 * 1024
EXTRA = "openpasco.json"
RECORD = struct.Struct("<Id")  # uint32 valid flag, float64 value
# shortcut: only codes confirmed from sample values; extend when more are verified
UNITS = {"256": "s", "1024": "V", "1280": "m", "1536": "N", "2048": "m/s²", "2304": "m/s", "3584": "A"}


@dataclass
class ImportResult:
    runs: list[Run]
    measurements: dict[str, tuple[str, Measurement]]
    skipped: int = 0  # data sets in formats we do not read
    warnings: list[str] = field(default_factory=list)
    pages: list[tuple[str, list[tuple[str, str | None]]]] = field(default_factory=list)  # (page name, display kinds)
    layout: dict | None = None  # present only in files written by OpenPASCO (member openpasco.json)
    origin: dict = field(default_factory=dict)  # {"hardware": <Hardware xml>, "attrs": {key: DataSource attributes}}


DISPLAY_TAGS = {"CSLineGraph": "그래프", "CSDataTable": "테이블", "CSDataDigits": "숫자", "CSBarMeter": "미터"}


def _pages(root, keys: dict[str, str]) -> list:
    out = []
    for i, page in enumerate(root.iter("WorkbookPage"), 1):
        items = []
        for it in page.findall("WorkbookItem"):
            kind = next((DISPLAY_TAGS[c.tag] for c in it if c.tag in DISPLAY_TAGS), None)
            pos = it.find("Position")
            try:
                xy = (round(float(pos.get("Y")), 1), float(pos.get("X")))  # rows of similar height first
            except (AttributeError, TypeError, ValueError):
                xy = (0.0, 0.0)
            key = next((keys[b.get("BundleMeasID")] for b in it.iter("BundleInput") if b.get("BundleMeasID") in keys), None)
            if kind:
                items.append((xy, kind, key))
        out.append((page.get("Name") or f"페이지 {i}", [(k, key) for _, k, key in sorted(items, key=lambda t: t[0])]))
    return out


def _read_member(z: zipfile.ZipFile, name: str, limit: int) -> bytes:
    info = z.getinfo(name)  # KeyError if missing; members are never extracted to disk
    if info.file_size > limit:
        raise ValueError(f"{name}: 파일이 너무 큽니다")
    return z.read(info)


def _values(raw: bytes, n: int) -> np.ndarray:
    if len(raw) < n * RECORD.size:
        raise ValueError("데이터 파일이 선언된 개수보다 짧습니다")
    out = np.empty(n)
    for i in range(n):
        ok, v = RECORD.unpack_from(raw, i * RECORD.size)
        out[i] = v if ok else np.nan
    return out


def _table_values(raw: bytes, n: int) -> np.ndarray:
    out, o = np.full(n, np.nan), 0
    for i in range(n):
        if o + 8 > len(raw):
            raise ValueError("표 데이터가 선언된 개수보다 짧습니다")
        kind, size = struct.unpack_from("<II", raw, o)
        if kind != 2 or o + 8 + size > len(raw):
            raise ValueError("알 수 없는 표 형식")
        try:
            out[i] = float(raw[o + 8:o + 8 + size].decode("utf-16le").replace(",", "."))
        except ValueError:
            pass  # non-numeric cell stays NaN
        o += 8 + size
    return out


def _read_extra(z: zipfile.ZipFile) -> dict | None:
    """OpenPASCO's own member; anything malformed is ignored so the file still opens as a plain .cap."""
    try:
        d = json.loads(_read_member(z, EXTRA, MAX_EXTRA_BYTES))
        if d.get("version") == 1 and isinstance(d.get("sources"), list) and isinstance(d.get("layout"), dict):
            return d
    except (KeyError, ValueError, AttributeError):
        pass
    return None


MAX_HARDWARE_CHARS = 1_000_000


def _saved_origin(extra) -> dict:
    """Capstone details carried through OpenPASCO files so that re-saving keeps sensors visible in Capstone."""
    o = (extra or {}).get("origin")
    return o if isinstance(o, dict) else {}


def _saved_source(extra, i: int) -> dict:
    """Text fields of the i-th source from openpasco.json, or {} (then names come from the XML)."""
    try:
        d = extra["sources"][i]
        return {k: d[k] for k in ("key", "sensor", "unit") if isinstance(d.get(k), str)}
    except (TypeError, IndexError, KeyError):
        return {}


def load_cap(path) -> ImportResult:
    path = Path(path)
    try:
        z = zipfile.ZipFile(path)
        root = ET.fromstring(_read_member(z, "main.xml", MAX_XML_BYTES))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise ValueError(f"Capstone 파일이 아니거나 손상되었습니다: {e}") from e
    if root.tag != "DSProExperiment":
        raise ValueError("Capstone 실험 파일이 아닙니다")

    extra = _read_extra(z)
    started = datetime.fromtimestamp(path.stat().st_mtime)  # file stores no verified start time
    runs: dict[int, Run] = {}
    meas: dict[str, tuple[str, Measurement]] = {}
    euid_key: dict[str, str] = {}
    attrs: dict[str, dict] = {}
    sidx = 0  # position among named sources: our writer emits them in the order of extra['sources']
    result = ImportResult([], meas)
    with z:
        for src in root.iter("DataSource"):
            name = src.get("LongName")
            if not name:
                continue
            saved = _saved_source(extra, sidx)
            sidx += 1
            key, k = saved.get("key") or f"cap:{name}", 1
            while key in meas:  # two sources with the same name
                k += 1
                key = f"{saved.get('key') or 'cap:' + name}#{k}"
            lo, hi = np.inf, -np.inf
            if src.get("EUID"):
                euid_key[src.get("EUID")] = key
            attrs[key] = dict(src.attrib)
            # code is trusted only when the display unit equals the base unit
            unit = UNITS.get(src.get("BaseUnit"), "") if src.get("BaseUnit") == src.get("DefaultUnit") else ""
            unit = saved.get("unit", unit)  # our own file knows the exact unit text
            for ds in src.findall("DataSet"):
                seg = ds.find("DataSegmentElement")
                dep = seg.find("DependentStorageElement") if seg is not None else None
                ind = seg.find("IndependentStorageElement") if seg is not None else None
                kinds = (dep.get("StorageType"), ind.get("StorageType")) if dep is not None and ind is not None else None
                if kinds not in (("0", "1"), ("7", "4")):
                    result.skipped += 1
                    continue
                try:
                    n = int(ind.get("CacheDataCount"))
                    run_no = int(ds.get("DataGroupNumber"))
                    if n < 0 or n * RECORD.size > MAX_DATA_BYTES:
                        raise ValueError("잘못된 데이터 개수")
                    raw = _read_member(z, dep.get("FileName").replace("\\", "/"), MAX_DATA_BYTES) if n else b""
                    if kinds == ("0", "1"):
                        dt, t0 = float(ind.get("IntervalCacheInterval")), float(ind.get("IntervalCacheStartValue"))
                        y, x = _values(raw, n), t0 + dt * np.arange(n)
                    else:
                        y, x = _table_values(raw, n), np.arange(1.0, n + 1)
                except (KeyError, TypeError, ValueError) as e:
                    result.warnings.append(f"{name}: 건너뜀 ({e})")
                    continue
                if n == 0:
                    continue
                run = runs.setdefault(run_no, Run(run_no, started))
                run.series[key] = Series(n)
                run.series[key].extend(x, y)
                if np.isfinite(y).any():
                    lo, hi = min(lo, np.nanmin(y)), max(hi, np.nanmax(y))
            if key in {k2 for r in runs.values() for k2 in r.series}:
                if lo == hi:
                    lo, hi = lo - 1, hi + 1
                meas[key] = (saved.get("sensor", "Capstone 파일"), Measurement(key, name, unit, float(lo), float(hi)))
    result.runs = [runs[n] for n in sorted(runs)]
    result.pages = _pages(root, euid_key)
    result.layout = extra["layout"] if extra else None
    hw = root.find("Hardware")
    hardware = ET.tostring(hw, encoding="unicode") if hw is not None else ""
    saved = _saved_origin(extra)
    if len(hardware) > MAX_HARDWARE_CHARS:
        hardware = ""
    result.origin = {"hardware": hardware or saved.get("hardware", ""),
                     "attrs": {k: v for k, v in {**saved.get("attrs", {}), **{k: a for k, a in attrs.items() if k in meas}}.items()
                               if isinstance(v, dict)}}
    return result
