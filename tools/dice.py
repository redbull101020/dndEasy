"""Dependency-free, unbiased dice roller for GPT D&D Campaign Runtime."""

from __future__ import annotations

import argparse
import json
import re
import secrets
from dataclasses import asdict, dataclass


EXPRESSION_PATTERN = re.compile(
    r"^(?P<count>[1-9]\d*)d(?P<sides>[1-9]\d*)(?P<modifier>[+-]\d+)?$",
    re.IGNORECASE,
)
MAX_DICE = 100
MAX_SIDES = 10_000
MAX_ABS_MODIFIER = 10_000


@dataclass(frozen=True)
class DiceExpression:
    count: int
    sides: int
    modifier: int

    @property
    def normalized(self) -> str:
        suffix = "" if self.modifier == 0 else f"{self.modifier:+d}"
        return f"{self.count}d{self.sides}{suffix}"


@dataclass(frozen=True)
class RollResult:
    source: str
    expression: str
    mode: str
    rolls: list[int]
    kept: list[int]
    modifier: int
    total: int


def parse_expression(value: str) -> DiceExpression:
    match = EXPRESSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError("expression must use NdS, NdS+M, or NdS-M notation")

    count = int(match.group("count"))
    sides = int(match.group("sides"))
    modifier = int(match.group("modifier") or 0)

    if count > MAX_DICE:
        raise ValueError(f"dice count must not exceed {MAX_DICE}")
    if not 2 <= sides <= MAX_SIDES:
        raise ValueError(f"die sides must be between 2 and {MAX_SIDES}")
    if abs(modifier) > MAX_ABS_MODIFIER:
        raise ValueError(
            f"absolute modifier must not exceed {MAX_ABS_MODIFIER}"
        )

    return DiceExpression(count=count, sides=sides, modifier=modifier)


def roll(expression: DiceExpression, mode: str) -> RollResult:
    if mode != "normal" and (expression.count != 1 or expression.sides != 20):
        raise ValueError("advantage and disadvantage are valid only for 1d20")

    roll_count = 2 if mode in {"advantage", "disadvantage"} else expression.count
    rolls = [secrets.randbelow(expression.sides) + 1 for _ in range(roll_count)]

    if mode == "advantage":
        kept = [max(rolls)]
    elif mode == "disadvantage":
        kept = [min(rolls)]
    else:
        kept = list(rolls)

    return RollResult(
        source="python.secrets.randbelow",
        expression=expression.normalized,
        mode=mode,
        rolls=rolls,
        kept=kept,
        modifier=expression.modifier,
        total=sum(kept) + expression.modifier,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Roll an NdS expression with Python secrets and print auditable JSON."
        )
    )
    parser.add_argument("expression", help="NdS, NdS+M, or NdS-M")
    parser.add_argument(
        "--mode",
        choices=("normal", "advantage", "disadvantage"),
        default="normal",
        help="d20 selection mode; default: normal",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        expression = parse_expression(args.expression)
        result = roll(expression, args.mode)
    except ValueError as error:
        parser.error(str(error))

    print(json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
