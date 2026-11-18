"""Recording conditions dialog: collapsible Start / Stop sections with a condition-type combo and a
description box, laid out like Capstone's 'Properties' dialog (observed on screen, not copied)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame, QLabel, QToolButton,
    QVBoxLayout, QWidget,
)

from openpasco.core.conditions import Condition, Conditions

OPS = {">": "보다 큼 (>)", "<": "보다 작음 (<)"}


class _Section(QWidget):
    """Header with an arrow that folds a body holding the type combo and its parameters."""

    def __init__(self, title, kinds, measurements, current: Condition | None, describe):
        super().__init__()
        self.kinds, self.measurements = kinds, measurements
        self.head = QToolButton(text=title, checkable=True, checked=True, objectName="cond_head")
        self.head.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.head.setArrowType(Qt.DownArrow)
        self.head.setStyleSheet("QToolButton { border: none; font-weight: bold; font-size: 14px; }")
        body = QFrame(objectName="cond_body")
        form = QFormLayout(body)
        self.type = QComboBox()
        self.type.addItem("없음", None)
        for kind, label in kinds.items():
            self.type.addItem(label, kind)
        self.meas = QComboBox()
        for key, label in measurements:
            self.meas.addItem(label, key)
        self.op = QComboBox()
        for op, label in OPS.items():
            self.op.addItem(label, op)
        self.value = QDoubleSpinBox(decimals=3, minimum=-1e9, maximum=1e9)
        self.seconds = QDoubleSpinBox(decimals=1, minimum=0.1, maximum=86400, value=10, suffix=" 초")
        form.addRow("조건 종류", self.type)
        self._rows = {"measure": [("측정값", self.meas), ("조건", self.op), ("값", self.value)],
                      "time": [("시간", self.seconds)]}
        self._form = form
        self._widgets = {w: lab for rows in self._rows.values() for lab, w in rows}
        for w, lab in self._widgets.items():
            form.addRow(lab, w)
        self.head.toggled.connect(lambda on: (body.setVisible(on),
                                              self.head.setArrowType(Qt.DownArrow if on else Qt.RightArrow)))
        self.type.currentIndexChanged.connect(self._sync)
        self.type.currentIndexChanged.connect(lambda _: describe(self.type.currentData()))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.head)
        lay.addWidget(body)
        if current:
            self.type.setCurrentIndex(max(0, self.type.findData(current.kind)))
            self.meas.setCurrentIndex(max(0, self.meas.findData(current.key)))
            self.op.setCurrentIndex(self.op.findData(current.op))
            self.value.setValue(current.value)
            if current.kind == "time":
                self.seconds.setValue(current.value)
        self._sync()

    def _sync(self):
        kind = self.type.currentData()
        for k, rows in self._rows.items():
            for lab, w in rows:
                show = k == kind
                w.setVisible(show)
                self._form.labelForField(w).setVisible(show)

    def condition(self) -> Condition | None:
        kind = self.type.currentData()
        if kind == "time":
            return Condition("time", value=self.seconds.value())
        if kind == "measure" and self.meas.currentData():
            return Condition("measure", self.meas.currentData(), self.op.currentData(), self.value.value())
        return None


class ConditionsDialog(QDialog):
    def __init__(self, parent, measurements: list[tuple[str, str]], current: Conditions):
        super().__init__(parent)
        self.setWindowTitle("기록 조건")
        self.setMinimumWidth(460)
        self.description = QLabel("항목을 선택하면 간단한 설명이 여기에 나옵니다.", wordWrap=True)
        self.description.setMinimumHeight(70)
        self.description.setAlignment(Qt.AlignTop)
        self.description.setFrameShape(QFrame.StyledPanel)
        text = {
            ("start", None): "시작 조건 없음: 기록 버튼을 누르면 바로 기록을 시작합니다.",
            ("start", "measure"): "선택한 측정값이 조건을 만족하는 순간부터 기록합니다. 시간은 그 순간이 0초입니다.",
            ("stop", None): "정지 조건 없음: 정지 버튼을 누를 때까지 기록합니다.",
            ("stop", "measure"): "선택한 측정값이 조건을 만족하면 자동으로 기록을 멈춥니다.",
            ("stop", "time"): "기록을 시작한 뒤 지정한 시간이 지나면 자동으로 멈춥니다.",
        }
        self.start = _Section("시작 조건", {"measure": "측정값 기준"}, measurements, current.start,
                              lambda k: self.description.setText(text[("start", k)]))
        self.stop = _Section("정지 조건", {"measure": "측정값 기준", "time": "시간 기준"}, measurements,
                             current.stop, lambda k: self.description.setText(text[("stop", k)]))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("확인")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.start)
        lay.addWidget(self.stop)
        lay.addStretch()
        lay.addWidget(self.description)
        lay.addWidget(buttons)

    def result_conditions(self) -> Conditions:
        return Conditions(self.start.condition(), self.stop.condition())
