from __future__ import annotations

from sympy import (
    Abs,
    E,
    I,
    Max,
    Min,
    Symbol,
    binomial,
    ceiling,
    diff,
    exp,
    factorial,
    floor,
    gcd,
    integrate,
    lcm,
    limit,
    log,
    oo,
    pi,
    simplify,
    sin,
    cos,
    tan,
    asin,
    acos,
    atan,
    sinh,
    cosh,
    tanh,
    sqrt,
)
from sympy import Function, Integer, Float, Rational, N
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from talking_telegram_bot.models.calculator import CalculatorResponse

_TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)
_ALLOWED_NAMES = {
    "Abs": Abs,
    "E": E,
    "I": I,
    "Integer": Integer,
    "Float": Float,
    "Function": Function,
    "Max": Max,
    "Min": Min,
    "Mod": lambda a, b: a % b,
    "N": N,
    "Rational": Rational,
    "Symbol": Symbol,
    "acos": acos,
    "asin": asin,
    "atan": atan,
    "binomial": binomial,
    "ceiling": ceiling,
    "cos": cos,
    "cosh": cosh,
    "diff": diff,
    "exp": exp,
    "factorial": factorial,
    "floor": floor,
    "gcd": gcd,
    "integrate": integrate,
    "lcm": lcm,
    "limit": limit,
    "ln": log,
    "log": log,
    "oo": oo,
    "pi": pi,
    "simplify": simplify,
    "sin": sin,
    "sinh": sinh,
    "sqrt": sqrt,
    "tan": tan,
    "tanh": tanh,
}


class CalculatorServiceError(RuntimeError):
    """Raised when a calculator expression can not be evaluated safely."""


class CalculatorService:
    def calculate(self, raw_expression: str) -> CalculatorResponse:
        expression = raw_expression.strip()
        if not expression:
            raise CalculatorServiceError("Calculator expression is empty.")
        try:
            parsed_expression = parse_expr(
                expression,
                local_dict=_ALLOWED_NAMES,
                global_dict={"__builtins__": {}},
                transformations=_TRANSFORMATIONS,
                evaluate=True,
            )
        except Exception as exc:
            raise CalculatorServiceError("Calculator expression is invalid.") from exc
        simplified_result = simplify(parsed_expression)
        approximation = self._build_approximation(simplified_result)
        return CalculatorResponse(
            expression=expression,
            result=str(simplified_result),
            approximation=approximation,
        )

    def _build_approximation(self, result) -> str | None:
        if not getattr(result, "is_number", False):
            return None
        if getattr(result, "is_Integer", False):
            return None
        approximation = str(N(result, 50))
        if approximation == str(result):
            return None
        return approximation
