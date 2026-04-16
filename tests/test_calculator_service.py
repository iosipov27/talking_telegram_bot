from __future__ import annotations

import unittest

from talking_telegram_bot.services.calculator_service import (
    CalculatorService,
    CalculatorServiceError,
)


class CalculatorServiceTestCase(unittest.TestCase):
    def test_calculate_returns_exact_and_approximate_results(self) -> None:
        service = CalculatorService()

        response = service.calculate("sqrt(2)")

        self.assertEqual(response.expression, "sqrt(2)")
        self.assertEqual(response.result, "sqrt(2)")
        self.assertTrue(response.approximation is not None)
        assert response.approximation is not None
        self.assertTrue(response.approximation.startswith("1.4142135623"))

    def test_calculate_supports_complex_expressions(self) -> None:
        service = CalculatorService()

        response = service.calculate("integrate(sin(x), (x, 0, pi)) + 2^5")

        self.assertEqual(response.result, "34")
        self.assertIsNone(response.approximation)

    def test_calculate_rejects_empty_expression(self) -> None:
        service = CalculatorService()

        with self.assertRaises(CalculatorServiceError):
            service.calculate("   ")

    def test_calculate_rejects_invalid_expression(self) -> None:
        service = CalculatorService()

        with self.assertRaises(CalculatorServiceError):
            service.calculate(")(")
