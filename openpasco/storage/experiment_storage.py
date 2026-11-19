"""CSV export of one run. Experiment files are .cap only (see capstone_export / capstone_import). No Qt."""
import csv

from openpasco.core.data_manager import Run
from openpasco.hardware.base import Measurement


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
