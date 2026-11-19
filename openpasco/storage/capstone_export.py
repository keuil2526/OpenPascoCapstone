"""Writer for Capstone .cap files (ZIP: main.xml + data/*.tmp).

Layout is reproduced from what the importer reads plus the surrounding structure observed in sample
files (see docs/capstone_format.md); it is checked by opening the result in Capstone itself.
Only recorded time series are written; OpenPASCO-only settings are not stored.
"""
import json
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from openpasco.core.data_manager import Run
from openpasco.hardware.base import Measurement
from openpasco.storage.capstone_import import RECORD, UNITS

UNIT_CODES = {u: c for c, u in UNITS.items()}  # reverse of the importer's table (verified units only)
VERSION = "2.6.0"  # an older Capstone version: newer Capstones open older files without warnings


def _id() -> str:
    return "{" + str(uuid.uuid4()) + "}"


def _data_bytes(y: np.ndarray) -> bytes:
    return b"".join(RECORD.pack(1 if np.isfinite(v) else 0, 0.0 if not np.isfinite(v) else float(v)) for v in y)


def _interval(t: np.ndarray):
    """(start, interval) when t is evenly spaced, else None (Capstone stores interval data)."""
    if len(t) < 2:
        return (float(t[0]) if len(t) else 0.0), 1.0
    dt = (t[-1] - t[0]) / (len(t) - 1)
    return (float(t[0]), float(dt)) if np.allclose(t, t[0] + dt * np.arange(len(t)), rtol=1e-6, atol=1e-9) else None


EXTRA = "openpasco.json"  # our own ZIP member: layout, calculations, original keys (Capstone ignores it)


def build(runs: list[Run], measurements: dict[str, tuple[str, Measurement]], layout: dict | None = None,
          origin: dict | None = None):
    """Return (main.xml bytes, {member name: data bytes}, warnings)."""
    sources, warnings = [], []
    files: dict[str, bytes] = {}
    root = ET.Element("DSProExperiment")
    ET.SubElement(root, "Header", Version=VERSION, ArgumentSeparator=",", LanguageID="409", Language="enu",
                  DigitCharacters="", ImportedFileName="", DecimalSeparator=".")
    origin = origin or {}
    try:  # the Hardware section of a file that came from Capstone: it is what lists sensors in Capstone
        if origin.get("hardware"):
            root.append(ET.fromstring(origin["hardware"]))
    except ET.ParseError:
        warnings.append("하드웨어 정보를 읽을 수 없어 건너뜀")
    repo = ET.SubElement(root, "DataRepository")
    ET.SubElement(repo, "MasterTimeMeasurement", LongName="Time", MeasurementName="Time", SymbolName="t",
                  BaseUnit="256", DefaultUnit="256", EUID=_id(), Visible="TRUE", GenericType="1")
    run_ids = {r.number: _id() for r in runs}
    counter = 0
    for key, (sensor, m) in measurements.items():
        sources.append({"key": key, "sensor": sensor, "name": m.name, "unit": m.unit,
                        "minimum": m.minimum, "maximum": m.maximum})
        kept = origin.get("attrs", {}).get(key)  # original attributes (EUID links it to the Hardware section)
        if isinstance(kept, dict) and all(isinstance(v, str) for v in kept.values()):
            src = ET.SubElement(repo, "DataSource", kept)
        else:
            src = ET.SubElement(repo, "DataSource", LongName=m.name, ShortName=m.name, MeasurementName=m.name,
                                EUID=_id(), Visible="TRUE", DataMeasSourceType="1000", MeasurementIsVirtual="FALSE",
                                BaseUnit=UNIT_CODES.get(m.unit, "0"), DefaultUnit=UNIT_CODES.get(m.unit, "0"),
                                DefaultMinimumDisplayValue=repr(m.minimum), DefaultMaximumDisplayValue=repr(m.maximum))
        for r in runs:
            s = r.series.get(key)
            if s is None:
                continue
            t, y = s.view()
            if len(t) == 0:
                continue
            iv = _interval(t)
            if iv is None:  # e.g. Bluetooth polling: Capstone stores interval data, so use the mean interval
                warnings.append(f"{m.name} (런 {r.number}): 시간 간격이 일정하지 않아 평균 간격으로 저장")
                iv = (float(t[0]), float((t[-1] - t[0]) / (len(t) - 1)))
            counter += 1
            name = f"data/Z_{uuid.uuid4().hex[:11]}_{counter}.tmp"
            files[name] = _data_bytes(y)
            ds = ET.SubElement(src, "DataSet", DataGroupNumber=str(r.number), DataGroup="1", Name="",
                               DataSetIndVarType="1", DataSetReadOnly="TRUE", DataSetID=run_ids[r.number],
                               DataHasBeenDeleted="FALSE", ZeroOffsetValue="0")
            seg = ET.SubElement(ds, "DataSegmentElement")
            ET.SubElement(seg, "DependentStorageElement", DataCacheDataSize=str(len(y)), DataOffsetValue="0",
                          FileName=name, CacheEpsilon="1e-09", StorageType="0")
            ET.SubElement(seg, "IndependentStorageElement", IntervalCacheInterval=repr(iv[1]),
                          IntervalCacheStartValue=repr(iv[0]), CacheDataCount=str(len(y)),
                          CacheEpsilon="1e-09", StorageType="1")
    ws = ET.SubElement(root, "Workspace")
    wb = ET.SubElement(ws, "Workbook", CurrentPage="0", PageFormat="5")
    ET.SubElement(wb, "WorkbookPage", Name="Page #1", PageID="1", EUID=_id())
    ET.indent(root)
    files[EXTRA] = json.dumps({"version": 1, "sources": sources, "layout": layout or {}, "origin": origin},
                              ensure_ascii=False).encode()
    return ET.tostring(root, encoding="utf-8", xml_declaration=False), files, warnings


def save_cap(path, runs: list[Run], measurements, layout: dict | None = None, origin: dict | None = None) -> list[str]:
    """Write path atomically; returns warnings about data that could not be stored exactly."""
    xml, files, warnings = build(runs, measurements, layout, origin)
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("main.xml", xml)
        for name, data in files.items():
            z.writestr(name, data)
    tmp.replace(path)
    return warnings
