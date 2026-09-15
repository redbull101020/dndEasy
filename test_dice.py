"""Regression tests for the dependency-free dice roller."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import dice


class SourceSafetyTests(unittest.TestCase):
    def test_runtime_source_has_expected_minimal_attack_surface(self) -> None:
        script = Path(__file__).with_name("dice.py")
        tree = ast.parse(script.read_text(encoding="utf-8"))
        imported_modules: set[str] = set()
        called_names: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called_names.add(node.func.id)

        self.assertLessEqual(
            imported_modules,
            {"__future__", "argparse", "dataclasses", "json", "re", "secrets"},
        )
        self.assertTrue(
            called_names.isdisjoint({"__import__", "compile", "eval", "exec", "open"})
        )


class ParseExpressionTests(unittest.TestCase):
    def test_parses_and_normalizes_supported_notation(self) -> None:
        cases = {
            "1d20": "1d20",
            "2D6+3": "2d6+3",
            " 4d8-2 ": "4d8-2",
            "1d20+0": "1d20",
        }

        for raw, normalized in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(dice.parse_expression(raw).normalized, normalized)

    def test_rejects_malformed_or_injection_like_input(self) -> None:
        invalid = (
            "",
            "d20",
            "0d20",
            "1d1",
            "101d6",
            "1d10001",
            "1d20+10001",
            "1d20-10001",
            "1d20;whoami",
            "1d20 && whoami",
            "1d20$(whoami)",
            "1d20`whoami`",
            "1d20/../../SAVE.md",
            "١d٢٠",
        )

        for raw in invalid:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    dice.parse_expression(raw)

    def test_rejects_non_text_input(self) -> None:
        with self.assertRaises(ValueError):
            dice.parse_expression(None)  # type: ignore[arg-type]


class RollTests(unittest.TestCase):
    def test_normal_roll_keeps_every_die_once(self) -> None:
        expression = dice.parse_expression("3d6+2")

        with patch.object(dice.secrets, "randbelow", side_effect=(0, 3, 5)):
            result = dice.roll(expression, "normal")

        self.assertEqual(result.rolls, [1, 4, 6])
        self.assertEqual(result.kept, [1, 4, 6])
        self.assertEqual(result.total, 13)

    def test_advantage_keeps_higher_d20(self) -> None:
        expression = dice.parse_expression("1d20+5")

        with patch.object(dice.secrets, "randbelow", side_effect=(2, 17)):
            result = dice.roll(expression, "advantage")

        self.assertEqual(result.rolls, [3, 18])
        self.assertEqual(result.kept, [18])
        self.assertEqual(result.total, 23)

    def test_disadvantage_keeps_lower_d20(self) -> None:
        expression = dice.parse_expression("1d20-1")

        with patch.object(dice.secrets, "randbelow", side_effect=(6, 14)):
            result = dice.roll(expression, "disadvantage")

        self.assertEqual(result.rolls, [7, 15])
        self.assertEqual(result.kept, [7])
        self.assertEqual(result.total, 6)

    def test_rejects_selection_mode_for_non_d20_expression(self) -> None:
        with self.assertRaises(ValueError):
            dice.roll(dice.parse_expression("2d6"), "advantage")

    def test_rejects_unknown_mode_when_called_as_library(self) -> None:
        with self.assertRaises(ValueError):
            dice.roll(dice.parse_expression("1d20"), "choose-best-for-story")

    def test_revalidates_programmatically_constructed_expression(self) -> None:
        invalid = dice.DiceExpression(count=0, sides=20, modifier=0)

        with self.assertRaises(ValueError):
            dice.roll(invalid, "normal")

    def test_rejects_non_integer_or_boolean_programmatic_fields(self) -> None:
        invalid_expressions = (
            dice.DiceExpression(count=1.5, sides=20, modifier=0),  # type: ignore[arg-type]
            dice.DiceExpression(count=True, sides=20, modifier=0),
            dice.DiceExpression(count=1, sides=20, modifier=False),
        )

        for expression in invalid_expressions:
            with self.subTest(expression=expression):
                with self.assertRaisesRegex(ValueError, "must be integers"):
                    dice.roll(expression, "normal")

    def test_rejects_wrong_programmatic_expression_object(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a DiceExpression"):
            dice.roll("1d20", "normal")  # type: ignore[arg-type]

    def test_reports_random_source(self) -> None:
        with patch.object(dice.secrets, "randbelow", return_value=9):
            result = dice.roll(dice.parse_expression("1d20"), "normal")

        self.assertEqual(result.source, "python.secrets.randbelow")


class CliTests(unittest.TestCase):
    def test_cli_emits_machine_readable_json(self) -> None:
        script = Path(__file__).with_name("dice.py")
        completed = subprocess.run(
            [sys.executable, "-B", str(script), "1d2+1"],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["expression"], "1d2+1")
        self.assertEqual(payload["mode"], "normal")
        self.assertEqual(len(payload["rolls"]), 1)
        self.assertIn(payload["rolls"][0], (1, 2))
        self.assertEqual(payload["total"], payload["rolls"][0] + 1)

    def test_cli_rejects_shell_metacharacters_without_executing_them(self) -> None:
        script = Path(__file__).with_name("dice.py")
        completed = subprocess.run(
            [sys.executable, "-B", str(script), "1d20;whoami"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("expression must use", completed.stderr)


if __name__ == "__main__":
    unittest.main()
