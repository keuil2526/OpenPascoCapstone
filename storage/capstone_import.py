"""Read-only importer for PASCO Capstone .cap files (ZIP: main.xml + data/*.tmp).

Layout was derived from sample files, not from documentation (see docs/capstone_format.md):
  - each <DataSource LongName=...> holds one <DataSet> per run (DataGroupNumber = run number)
  - interval data sets (StorageType 0 / independent StorageType 1): time = start + interval * i,
    values = the first CacheDataCount 12-byte records (uint32 valid-flag, float64) of the data file
  - other storage types (user-entered tables, StorageType 7/4) are skipped and counted
Units are stored by Capstone as numeric codes with no table we can verify, so unit is left empty.
"""
import struct
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from core.data_manager import Run, Series
from hardware.base import Measurement

MAX_XML_BYTES = 200 * 1024 * 1024
MAX_DATA_BYTES = 512 * 1024 * 1024
RECORD = struct.Struct("<Id")  # uint32 valid flag, float64 value


@dataclass
class ImportResult:
    runs: list[Run]
    measurements: dict[str, tuple[str, Measurement]]
    skipped: int = 0  # data sets in formats we do not read
    warnings: list[str] = field(default_factory=list)


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


def load_cap(path) -> ImportResult:
    path = Path(path)
    try:
        z = zipfile.ZipFile(path)
        root = ET.fromstring(_read_member(z, "main.xml", MAX_XML_BYTES))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise ValueError(f"Capstone 파일이 아니거나 손상되었습니다: {e}") from e
    if root.tag != "DSProExperiment":
        raise ValueError("Capstone 실험 파일이 아닙니다")

    started = datetime.fromtimestamp(path.stat().st_mtime)  # file stores no verified start time
    runs: dict[int, Run] = {}
    meas: dict[str, tuple[str, Measurement]] = {}
    result = ImportResult([], meas)
    with z:
        for src in root.iter("DataSource"):
            name = src.get("LongName")
            if not name:
                continue
            key, k = f"cap:{name}", 1
            while key in meas:  # two sources with the same name
                k += 1
                key = f"cap:{name}#{k}"
            lo, hi = np.inf, -np.inf
            for ds in src.findall("DataSet"):
                seg = ds.find("DataSegmentElement")
                dep = seg.find("DependentStorageElement") if seg is not None else None
                ind = seg.find("IndependentStorageElement") if seg is not None else None
                if dep is None or ind is None or dep.get("StorageType") != "0" or ind.get("StorageType") != "1":
                    result.skipped += 1
                    continue
                try:
                    n = int(ind.get("CacheDataCount"))
                    dt, t0 = float(ind.get("IntervalCacheInterval")), float(ind.get("IntervalCacheStartValue"))
                    run_no = int(ds.get("DataGroupNumber"))
                    if n < 0 or n * RECORD.size > MAX_DATA_BYTES:
                        raise ValueError("잘못된 데이터 개수")
                    y = _values(_read_member(z, dep.get("FileName").replace("\\", "/"), MAX_DATA_BYTES), n)
                except (KeyError, TypeError, ValueError) as e:
                    result.warnings.append(f"{name}: 건너뜀 ({e})")
                    continue
                if n == 0:
                    continue
                run = runs.setdefault(run_no, Run(run_no, started))
                run.series[key] = Series(n)
                run.series[key].extend(t0 + dt * np.arange(n), y)
                if np.isfinite(y).any():
                    lo, hi = min(lo, np.nanmin(y)), max(hi, np.nanmax(y))
            if key in {k2 for r in runs.values() for k2 in r.series}:
                if lo == hi:
                    lo, hi = lo - 1, hi + 1
                meas[key] = ("Capstone 파일", Measurement(key, name, "", float(lo), float(hi)))
    result.runs = [runs[n] for n in sorted(runs)]
    return result
