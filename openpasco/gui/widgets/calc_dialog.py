"""Dialog for defining a calculated measurement."""
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QListWidget, QVBoxLayout,
)

from openpasco.core.calculation import CalcError, FUNCS


class CalcDialog(QDialog):
    def __init__(self, parent, measurement_names: list[str], create):
        """create(name, unit, expr) registers the calculation or raises CalcError."""
        super().__init__(parent)
        self.setWindowTitle("계산 추가")
        self.setMinimumWidth(460)
        self._create = create
        self.name = QLineEdit(placeholderText="예: 운동에너지")
        self.unit = QLineEdit(placeholderText="예: J (선택)")
        self.expr = QLineEdit(placeholderText="예: 0.5 * 2 * [속도] ** 2")
        self.names = QListWidget()
        self.names.addItems(measurement_names)
        self.names.setMaximumHeight(110)
        self.names.setToolTip("더블클릭하면 수식에 [이름]이 들어갑니다")
        self.names.itemDoubleClicked.connect(lambda it: self.expr.insert(f"[{it.text()}]"))
        self.error = QLabel("")
        self.error.setStyleSheet("color: #c62828;")
        self.error.setWordWrap(True)

        form = QFormLayout()
        form.addRow("이름", self.name)
        form.addRow("단위", self.unit)
        form.addRow("수식", self.expr)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("사용할 수 있는 측정값 (더블클릭하여 삽입):"))
        layout.addWidget(self.names)
        help_ = QLabel("연산: + - * / ** %  ·  상수: pi, e  ·  t = 시간  ·  함수: "
                       + ", ".join(FUNCS) + "(…)")
        help_.setWordWrap(True)
        layout.addWidget(help_)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def accept(self):
        try:
            self._create(self.name.text().strip(), self.unit.text().strip(), self.expr.text())
        except CalcError as e:
            self.error.setText(str(e))
            return  # keep the dialog open so the user can fix it
        super().accept()
