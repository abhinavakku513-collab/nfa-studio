from tests.benchmark.run_benchmark import run


def test_rule_only_benchmark_reaches_ninety_percent() -> None:
    """spec §14.3: at least 90% of benchmark outcomes correct without the LLM tier."""
    report = run()
    failed = [
        (row["id"], row["prompt"], row["got"]) for row in report["entries"] if not row["passed"]
    ]
    assert report["score"] >= 0.9, failed
