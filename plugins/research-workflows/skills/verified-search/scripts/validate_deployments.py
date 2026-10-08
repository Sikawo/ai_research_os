#!/usr/bin/env python3
"""Validate exact Verified Search paste-ready blocks and independent budgets."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIED_SEARCH = ROOT / "references"


class ValidationError(RuntimeError):
    """Raised when a deployment artifact is not safe to label paste-ready."""


@dataclass(frozen=True)
class DeploymentSpec:
    name: str
    path: Path
    heading: str
    platform_hard_limit: int | None
    release_budget: int
    reported_count_required: bool


DEPLOYMENTS = (
    DeploymentSpec(
        name="Custom GPT Instructions",
        path=VERIFIED_SEARCH / "custom_gpt_instructions.md",
        heading="Paste-Ready Instructions",
        platform_hard_limit=8_000,
        release_budget=7_500,
        reported_count_required=False,
    ),
    DeploymentSpec(
        name="Compact Custom Instructions",
        path=VERIFIED_SEARCH / "custom_instructions_free.md",
        heading="Paste-Ready Text",
        platform_hard_limit=None,
        release_budget=1_400,
        reported_count_required=True,
    ),
    DeploymentSpec(
        name="Full Custom Instructions",
        path=VERIFIED_SEARCH / "custom_instructions_full.md",
        heading="Paste-Ready Text",
        platform_hard_limit=None,
        release_budget=5_000,
        reported_count_required=True,
    ),
)


def extract_paste_ready_block(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\n\n```text\n(.*?)\n```(?:\n|$)",
        flags=re.MULTILINE | re.DOTALL,
    )
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise ValidationError(
            f"expected exactly one fenced block under '## {heading}', found {len(matches)}"
        )
    return matches[0]


def extract_reported_count(text: str) -> int | None:
    matches = re.findall(r"Character count: `([0-9][0-9,]*)`", text)
    if not matches:
        return None
    if len(matches) != 1:
        raise ValidationError(f"expected at most one reported character count, found {len(matches)}")
    return int(matches[0].replace(",", ""))


def validate_deployment(spec: DeploymentSpec) -> int:
    text = spec.path.read_text(encoding="utf-8")
    block = extract_paste_ready_block(text, spec.heading)
    count = len(block)

    if spec.platform_hard_limit is not None and count > spec.platform_hard_limit:
        raise ValidationError(
            f"{spec.name} block is {count:,} characters; hard limit is "
            f"{spec.platform_hard_limit:,}"
        )
    if count > spec.release_budget:
        raise ValidationError(
            f"{spec.name} block is {count:,} characters; release budget is "
            f"{spec.release_budget:,}"
        )

    reported = extract_reported_count(text)
    if spec.reported_count_required and reported is None:
        raise ValidationError(f"{spec.name} must report its exact character count")
    if reported is not None and reported != count:
        raise ValidationError(
            f"{spec.name} reports {reported:,} characters but exact block count is {count:,}"
        )
    return count


def main() -> int:
    failures: list[str] = []
    for spec in DEPLOYMENTS:
        try:
            count = validate_deployment(spec)
        except (OSError, ValidationError) as error:
            failures.append(f"FAIL: {spec.name}: {error}")
        else:
            limit_note = (
                f"hard limit {spec.platform_hard_limit:,}"
                if spec.platform_hard_limit is not None
                else "no universal platform hard limit asserted"
            )
            print(
                f"PASS: {spec.name}: {count:,} characters "
                f"(budget {spec.release_budget:,}; {limit_note})"
            )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
