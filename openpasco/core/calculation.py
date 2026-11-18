"""User-defined calculations: a small, safe expression language over measurements.

Syntax: [측정값 이름] refers to a measurement, `t` is time, plus + - * / ** %, parentheses,
numbers, constants pi and e, and the functions in FUNCS. Anything else is rejected: expressions
are parsed with `ast` and walked node by node; nothing is ever passed to eval().
"""
import ast
import re
from typing import Callable

import numpy as np

MAX_LENGTH = 500
FUNCS = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan, "asin": np.arcsin, "acos": np.arccos,
    "atan": np.arctan, "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
    "sqrt": np.sqrt, "exp": np.exp, "ln": np.log, "log10": np.log10, "abs": np.abs,
    "floor": np.floor, "ceil": np.ceil, "round": np.round,
}
CONSTS = {"pi": np.pi, "e": np.e}
_BINOPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.true_divide,
           ast.Pow: np.power, ast.Mod: np.mod}
_REF = re.compile(r"\[([^\[\]]+)\]")


class CalcError(ValueError):
    """Bad expression or missing data; the message is meant for the user."""


def parse(expr: str) -> tuple[ast.Expression, list[str]]:
    """Return (syntax tree, referenced measurement names in order of first use)."""
    if not expr.strip():
        raise CalcError("수식이 비어 있습니다")
    if len(expr) > MAX_LENGTH:
        raise CalcError(f"수식이 너무 깁니다 (최대 {MAX_LENGTH}자)")
    names: list[str] = []

    def sub(m):
        n = m.group(1).strip()
        if n not in names:
            names.append(n)
        return f"_v{names.index(n)}"

    outside = _REF.sub("", expr)
    if re.search(r"_", outside):
        raise CalcError("밑줄(_)은 [측정값 이름] 안에서만 쓸 수 있습니다")
    try:
        tree = ast.parse(_REF.sub(sub, expr).strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError) as e:
        where = f" ({e.offset}번째 글자 근처)" if isinstance(e, SyntaxError) and e.offset else ""
        raise CalcError(f"수식 문법 오류{where}: 괄호, 연산자, 빠진 값을 확인하세요") from e
    return tree, names


def _eval(node, env):
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in CONSTS:
            return CONSTS[node.id]
        raise CalcError(f"알 수 없는 이름: {node.id} (측정값은 [이름]처럼 대괄호로 씁니다)")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand, env)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        if node.func.id not in FUNCS:
            raise CalcError(f"지원하지 않는 함수: {node.func.id}")
        if len(node.args) != 1:
            raise CalcError(f"{node.func.id}()에는 인수가 하나 필요합니다")
        return FUNCS[node.func.id](_eval(node.args[0], env))
    raise CalcError("지원하지 않는 수식 요소입니다")


def evaluate(expr: str, resolve: Callable[[str], tuple[np.ndarray, np.ndarray] | None]):
    """Evaluate expr -> (t, y). resolve(name) gives a measurement's (t, y) or None.
    The first referenced measurement sets the time base; others are interpolated onto it
    (NaN outside their time range)."""
    tree, names = parse(expr)
    if not names:
        raise CalcError("수식에 측정값을 [이름]으로 하나 이상 넣어야 합니다")
    series = []
    for n in names:
        s = resolve(n)
        if s is None or len(s[0]) == 0:
            raise CalcError(f"'{n}' 데이터가 없습니다")
        series.append(s)
    base = series[0][0]
    env = {"t": base}
    for i, (t, y) in enumerate(series):
        if i == 0 or (len(t) == len(base) and np.array_equal(t, base)):
            env[f"_v{i}"] = np.asarray(y, float)
        else:
            yi = np.interp(base, t, y)
            yi[(base < t[0]) | (base > t[-1])] = np.nan
            env[f"_v{i}"] = yi
    try:
        with np.errstate(all="ignore"):  # 1/0 -> inf, sqrt(-1) -> nan, like a calculator
            y = _eval(tree, env)
    except (TypeError, ValueError, RecursionError) as e:
        raise CalcError(f"계산 오류: {e}") from e
    return base, np.broadcast_to(np.asarray(y, float), base.shape).copy()


_NAME = re.compile(r"^\s*([^\W\d]\w*)\s*=(?!=)\s*(.*?)\s*$")
_BRACKET = re.compile(r"(\[[^\[\]]*\])")


def split_assignment(line: str) -> tuple[str, str]:
    """'name = rhs' -> (name, rhs); raises CalcError when the line is not an assignment."""
    m = _NAME.match(line)
    if not m or not m.group(2):
        raise CalcError("'이름 = 수식' 형태로 입력하세요")
    name = m.group(1)
    if name == "t" or name in CONSTS or name in FUNCS:
        raise CalcError(f"'{name}'은(는) 예약된 이름이라 쓸 수 없습니다")
    return name, m.group(2)


def substitute(expr: str, constants: dict[str, float]) -> str:
    """Replace bare constant names by their values; text inside [ ] (measurement names) is untouched."""
    if not constants:
        return expr
    pat = re.compile(r"(?<![\w.])(" + "|".join(map(re.escape, sorted(constants, key=len, reverse=True))) + r")(?![\w(])")
    return "".join(part if part.startswith("[") else pat.sub(lambda m: f"({constants[m.group(1)]!r})", part)
                   for part in _BRACKET.split(expr))
