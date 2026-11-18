"""Calculator: a table of 'name = expression' lines with units (constants like `m = 3` can be used by
later lines), a function keypad, and a status line. Laid out like Capstone's calculator panel
(observed on screen, not copied); lines that are plain numbers become constants, the rest become
calculated measurements."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QLabel, QListWidget, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from openpasco.core.calculation import CalcError, FUNCS, split_assignment, substitute

ROWS = 5
KEYS = ["sin(", "cos(", "tan(", "asin(", "acos(", "atan(", "sqrt(", "exp(", "ln(", "log10(", "abs(", "**",
        "+", "-", "*", "/", "pi", "(", ")"]


class CalcDialog(QDialog):
    def __init__(self, parent, measurement_names: list[str], create):
        """create(name, unit, expr) registers one calculation or raises CalcError."""
        super().__init__(parent)
        self.setWindowTitle("계산기")
        self.setMinimumSize(520, 560)
        self._create = create
        self.table = QTableWidget(ROWS, 2)
        self.table.setHorizontalHeaderLabels(["계산식 (이름 = 수식)", "단위"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.setColumnWidth(1, 90)
        self.table.setToolTip("예)  m = 3   ·   b = 20   ·   y = m * [위치] + b")
        self.table.cellChanged.connect(lambda *_: self.check())
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.names = QListWidget()
        self.names.addItems(measurement_names)
        self.names.setMaximumHeight(90)
        self.names.setToolTip("더블클릭하면 현재 칸에 [이름]이 들어갑니다")
        self.names.itemDoubleClicked.connect(lambda it: self.insert(f"[{it.text()}]"))

        keys = QWidget()
        grid = QGridLayout(keys)
        grid.setSpacing(4)
        for i, k in enumerate(KEYS):
            b = QPushButton(k[:-1] if len(k) > 1 and k.endswith("(") else k, toolTip=f"{k} 삽입")
            b.clicked.connect(lambda _=False, k=k: self.insert(k))
            grid.addWidget(b, i // 6, i % 6)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("적용")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("측정값 (더블클릭하여 삽입):"))
        layout.addWidget(self.names)
        layout.addWidget(keys)
        layout.addWidget(QLabel("연산 + - * / ** %  ·  상수 pi, e  ·  t = 시간  ·  함수 " + ", ".join(FUNCS),
                                wordWrap=True))
        layout.addWidget(buttons)
        self.table.setCurrentCell(0, 0)

    # --- editing ----------------------------------------------------------
    def insert(self, text: str):
        row, col = max(self.table.currentRow(), 0), 0
        item = self.table.item(row, col) or QTableWidgetItem("")
        self.table.setItem(row, col, item)
        item.setText(item.text() + text)

    def lines(self) -> list[tuple[int, str, str]]:
        """(row, text, unit) for every non-empty line."""
        out = []
        for r in range(self.table.rowCount()):
            text = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            unit = (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()
            if text:
                out.append((r, text, unit))
        return out

    def check(self) -> str | None:
        """Syntax check of the lines (no registration). Returns an error text or None."""
        try:
            for _, text, _unit in self.lines():
                split_assignment(text)
        except CalcError as e:
            self.status.setStyleSheet("color: #c62828;")
            self.status.setText(str(e))
            return str(e)
        self.status.setStyleSheet("color: #2e7d32;" if self.lines() else "")
        self.status.setText("입력 확인됨 — 적용을 누르면 계산이 만들어집니다" if self.lines() else "")
        return None

    def accept(self):
        constants: dict[str, float] = {}
        made = 0
        for row, text, unit in self.lines():
            try:
                name, rhs = split_assignment(text)
                try:
                    constants[name] = float(rhs.replace(",", "."))  # a plain number defines a constant
                    continue
                except ValueError:
                    pass
                self._create(name, unit, substitute(rhs, constants))
                made += 1
            except CalcError as e:
                self.table.setCurrentCell(row, 0)
                self.status.setStyleSheet("color: #c62828;")
                self.status.setText(f"{row + 1}번째 줄: {e}")
                return  # keep the dialog open so the user can fix it
        if not made:
            self.status.setStyleSheet("color: #c62828;")
            self.status.setText("만들 계산이 없습니다 (예: y = 2 * [위치])")
            return
        super().accept()
