from tests.benchmark.run_benchmark import run


def test_rule_only_benchmark_reaches_ninety_percent() -> None:
    """spec §14.3: at least 90% of benchmark outcomes correct without the LLM tier."""
    report = run()
    failed = [
        (row["id"], row["prompt"], row["got"]) for row in report["entries"] if not row["passed"]
    ]
    assert report["score"] >= 0.9, failed


def test_with_the_llm_tier_only_unreadable_prompts_reach_the_model() -> None:
    """spec §14.3 asks for 95% with the LLM tier. A stand-in model that declines
    everything shows which entries reach the tier and that it cannot make them worse;
    the real model is measured with `run_benchmark --llm`."""

    def declines(system: str, text: str) -> str:
        return '{"error": "not_expressible", "reason": "stand-in"}'

    report = run(declines, write_report=False)
    assert [row["id"] for row in report["entries"] if row["llm_called"]] == [20]
    assert report["score"] >= 0.95
