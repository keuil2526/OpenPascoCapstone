"""Analysis drawn on the graph itself, the way Capstone does it: shaded bands, lines with boxed labels,
leader lines to data points, dashed crosshairs. All items live in data coordinates and are removed together."""
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class Marks:
    def __init__(self, plot: pg.PlotWidget, color="#1f2bff"):
        self.plot = plot
        self.color = color
        self.items: list = []

    def clear(self):
        for item in self.items:
            self.plot.removeItem(item)
        self.items = []

    def _add(self, item):
        self.plot.addItem(item, ignoreBounds=True)  # analysis must not rescale the graph
        self.items.append(item)
        return item

    def _rgba(self, alpha):
        c = QColor(self.color)
        c.setAlpha(alpha)
        return c

    def line(self, xs, ys, width=1, style=Qt.SolidLine, color=None):
        pen = pg.mkPen(color or self._rgba(200), width=width, style=style)
        return self._add(pg.PlotDataItem(xs, ys, pen=pen))

    def band(self, x0, x1, y0, y1, alpha=60):
        """Shaded rectangle (Capstone's statistics / selection box)."""
        lo = self._add(pg.PlotDataItem([x0, x1], [y0, y0], pen=pg.mkPen(self._rgba(160), width=1)))
        hi = self._add(pg.PlotDataItem([x0, x1], [y1, y1], pen=pg.mkPen(self._rgba(160), width=1)))
        self._add(pg.FillBetweenItem(lo, hi, brush=pg.mkBrush(self._rgba(alpha)))).setZValue(-2)  # under the curve

    def area(self, t, y, alpha=60):
        """Shade between the curve and y = 0 (Capstone's area tool)."""
        hidden = pg.mkPen(self._rgba(0))  # a curve with pen=None has no path to fill against
        top = self._add(pg.PlotDataItem(t, y, pen=hidden))
        base = self._add(pg.PlotDataItem(t, [0] * len(t), pen=hidden))
        self._add(pg.FillBetweenItem(top, base, brush=pg.mkBrush(self._rgba(alpha)))).setZValue(-2)

    def label(self, text, x, y, anchor=(0, 1)):
        """Text in a white box with a border in the curve's colour."""
        item = pg.TextItem(text, color="#222222", anchor=anchor, border=pg.mkPen(self.color, width=1.5),
                           fill=pg.mkBrush("#ffffff"))
        item.setPos(x, y)
        return self._add(item)

    def callout(self, text, target, box):
        """Boxed text at `box` with a leader line to the data point `target`, which gets a bracket marker."""
        self.line([box[0], target[0]], [box[1], target[1]])
        self.label(text, *box)
        self._add(pg.ScatterPlotItem([target[0]], [target[1]], symbol="s", size=14, brush=None,
                                     pen=pg.mkPen(self.color, width=1.5)))

    def crosshair(self, x, y):
        pen = pg.mkPen("#222222", width=1, style=Qt.DashLine)
        self._add(pg.InfiniteLine(pos=x, angle=90, pen=pen))
        self._add(pg.InfiniteLine(pos=y, angle=0, pen=pen))


def box_position(view_range, point, dx=0.06, dy=0.12):
    """Where to put a callout box for `point`: up and towards the middle of the view, so it stays visible."""
    (x0, x1), (y0, y1) = view_range
    px, py = point
    bx = px + dx * (x1 - x0) if px < (x0 + x1) / 2 else px - dx * (x1 - x0) - 0.15 * (x1 - x0)
    by = py + dy * (y1 - y0) if py < (y0 + y1) / 2 else py - dy * (y1 - y0)
    return bx, by
