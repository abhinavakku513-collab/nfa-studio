"""benchmark_v1 runner (spec §14.2, CLAUDE.md C12).

From backend/: `python -m tests.benchmark.run_benchmark`. Prints every entry with
pass/fail and writes tests/benchmark/report.json. The interpreter never sees which
prompts are in the benchmark; there is nothing here it could special-case.
"""

import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

from nfa_studio.interpret import interpret
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import IRDocument
from nfa_studio.reference.equivalence import language_difference
from nfa_studio.reference.to_dfa import NotTranslatable, reference_dfa
from nfa_studio.session.clarify import Asking, EditIR, Ready, open_draft
from nfa_studio.verify.ladder import bounded_length

HERE = Path(__file__).resolve().parent
BENCHMARK = HERE / "benchmark_v1.json"
REPORT = HERE / "report.json"


@dataclass(frozen=True)
class Outcome:
    kind: str
    ir: IRDocument | None = None
    topic: str | None = None
    error: str | None = None
    alternative: bool | None = None

    def describe(self) -> str:
        match self.kind:
            case "ir":
                assert self.ir is not None
                language = json.dumps(self.ir.language.model_dump(mode="json"))
                return f"ir {language}"
            case "clarification":
                return f"clarification {self.topic}"
            case "refusal":
                offered = "with alternative" if self.alternative else "no alternative"
                return f"refusal {self.error} ({offered})"
        return self.kind


def outcome_of(prompt: str) -> Outcome:
    """What the rule-only interpreter does with `prompt`."""
    try:
        result = open_draft(interpret(prompt), prompt)
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code is None:
            raise
        alternative = getattr(exc, "alternative", None)
        return Outcome("refusal", error=code, alternative=alternative is not None)
    match result:
        case Ready():
            return Outcome("ir", ir=result.ir)
        case Asking():
            return Outcome("clarification", topic=result.question.topic)
        case EditIR():
            return Outcome("edit_ir")


def same_language(expected: IRDocument, produced: IRDocument) -> bool:
    """C12: equal alphabets, then the V2 check on reference DFAs; V1 for pattern_count."""
    if expected.alphabet.symbols != produced.alphabet.symbols:
        return False
    try:
        return language_difference(reference_dfa(expected), reference_dfa(produced)) is None
    except NotTranslatable:
        symbols = expected.alphabet.symbols
        return all(
            matches(expected.language, word) == matches(produced.language, word)
            for n in range(bounded_length(len(symbols)) + 1)
            for word in map("".join, product(symbols, repeat=n))
        )


def satisfies(expect: dict[str, Any], outcome: Outcome) -> bool:
    if expect["kind"] != outcome.kind:
        return False
    if outcome.kind == "clarification":
        return bool(outcome.topic == expect["question_topic"])
    if outcome.kind == "refusal":
        return bool(
            outcome.error == expect["error"]
            and outcome.alternative == expect["alternative_offered"]
        )
    assert outcome.ir is not None
    wanted = validate_ir(
        {
            "alphabet": {"symbols": expect["alphabet"], "source": "user"},
            "language": expect["language"],
        }
    )
    present = {a.id for a in outcome.ir.assumptions}
    return same_language(wanted, outcome.ir) and set(expect["assumptions_must_include"]) <= present


def run(write_report: bool = True) -> dict[str, Any]:
    entries = json.loads(BENCHMARK.read_text(encoding="utf-8"))["entries"]
    rows = []
    for entry in entries:
        outcome = outcome_of(entry["prompt"])
        accepted = [entry["expect"], *entry.get("also_accept", [])]
        rows.append(
            {
                "id": entry["id"],
                "prompt": entry["prompt"],
                "expected": entry["expect"]["kind"],
                "got": outcome.describe(),
                "passed": any(satisfies(expect, outcome) for expect in accepted),
            }
        )
    passed = sum(row["passed"] for row in rows)
    report = {
        "benchmark": "benchmark_v1",
        "mode": "rule-only",
        "passed": passed,
        "total": len(rows),
        "score": round(passed / len(rows), 4),
        "entries": rows,
    }
    if write_report:
        REPORT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
    return report


def main() -> None:
    report = run()
    print(f"{'#':>3}  {'expected':<13} {'result':<6} got")
    for row in report["entries"]:
        result = "PASS" if row["passed"] else "FAIL"
        print(f"{row['id']:>3}  {row['expected']:<13} {result:<6} {row['got'][:90]}")
    print(f"\n{report['passed']}/{report['total']} correct ({report['score']:.1%}), rule-only")


if __name__ == "__main__":
    main()
