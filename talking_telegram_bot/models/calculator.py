from dataclasses import dataclass


@dataclass(frozen=True)
class CalculatorResponse:
    expression: str
    result: str
    approximation: str | None
