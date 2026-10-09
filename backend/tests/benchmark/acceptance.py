"""Measured acceptance values over benchmark_v1 (spec §14.3).

From backend/: `python -m tests.benchmark.acceptance`. For every entry whose expected
outcome is a specification, and for every answer to each clarification entry's
question, without the LLM tier:

- construct + verify time, cold (fresh stores, empty verification cache), through
  POST /v1/automata and directly through compile + verify; the median of three runs
  per entry, then the median over entries;
- the verification level reached (V2 required; V1 where the tree has pattern_count);
- the simulator against the oracle on every word up to length 10;
- the model hash reported by every table and diagram view against the automaton id.

Prints one row per entry and the summary, and writes acceptance.json.
"""

import json
import statistics
import time
from collections.abc import Iterator
from itertools import product
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from nfa_studio.api.app import app
from nfa_studio.api.deps import (
    TokenBucket,
    get_automata,
    get_by_spec,
    get_limiter,
    get_llm,
    get_sessions,
)
from nfa_studio.compile import compile
from nfa_studio.core.simulate import simulate
from nfa_studio.ir.limits import LIMITS
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.ir.oracle import matches
from nfa_studio.ir.schema import IRDocument
from nfa_studio.session.store import TTLStore
from nfa_studio.verify import ladder

HERE = Path(__file__).resolve().parent
BENCHMARK = HERE / "benchmark_v1.json"
REPORT = HERE / "acceptance.json"
RUNS = 3
MAX_LENGTH = 10
VIEWS = [
    (kind, fmt, eps_free, show_dead)
    for kind, fmt in (("table", "json"), ("diagram", "json"))
    for eps_free in (False, True)
    for show_dead in (False, True)
]


def fresh_client() -> TestClient:
    """The app on empty stores, so nothing is served from an earlier build."""
    sessions: TTLStore[str, Any] = TTLStore(LIMITS.session_ttl_seconds)
    automata: TTLStore[str, Any] = TTLStore(LIMITS.automaton_ttl_seconds)
    by_spec: TTLStore[str, str] = TTLStore(LIMITS.automaton_ttl_seconds)
    app.dependency_overrides.update(
        {
            get_sessions: lambda: sessions,
            get_automata: lambda: automata,
            get_by_spec: lambda: by_spec,
            get_limiter: lambda: TokenBucket(10**6, 10**6),
            get_llm: lambda: None,
        }
    )
    return TestClient(app)


def words(alphabet: tuple[str, ...], longest: int) -> Iterator[str]:
    for n in range(longest + 1):
        yield from map("".join, product(alphabet, repeat=n))


def has_pattern_count(node: Any) -> bool:
    if node.type == "pattern_count":
        return True
    children = getattr(node, "children", None) or (
        [node.child] if getattr(node, "child", None) is not None else []
    )
    return any(has_pattern_count(child) for child in children)


def cold_core(doc: IRDocument) -> float:
    ladder._cache.clear()
    start = time.perf_counter()
    verify_report = ladder.verify(compile(doc).automaton, doc)
    elapsed = time.perf_counter() - start
    assert verify_report.level
    return elapsed


def cold_api(spec: dict[str, Any]) -> tuple[float, dict[str, Any], TestClient]:
    ladder._cache.clear()
    client = fresh_client()
    start = time.perf_counter()
    response = client.post("/v1/automata", json=spec)
    elapsed = time.perf_counter() - start
    return elapsed, {"status": response.status_code, **response.json()}, client


def clarified(prompt: str) -> list[tuple[str, dict[str, Any]]]:
    """The specification behind each answer to the first question (later ones: first option)."""
    client = fresh_client()
    asked = client.post("/v1/interpret", json={"text": prompt}).json()
    options = [o["id"] for o in asked["question"]["options"] if o["id"] != "edit"]
    specs = []
    for option in options:
        reply = client.post("/v1/interpret", json={"text": prompt}).json()
        answer = option
        while reply["status"] == "clarification_required":
            question = reply["question"]
            reply = client.post(
                f"/v1/interpret/{reply['session_id']}/answer",
                json={"question_id": question["id"], "option_id": answer},
            ).json()
            if reply["status"] == "clarification_required":
                answer = reply["question"]["options"][0]["id"]
        specs.append((option, reply["ir"]))
    return specs


def measure(label: str, prompt: str, spec: dict[str, Any]) -> dict[str, Any]:
    doc = validate_ir(spec)
    core = statistics.median(cold_core(doc) for _ in range(RUNS))
    api_runs = [cold_api(spec) for _ in range(RUNS)]
    api = statistics.median(seconds for seconds, _, _ in api_runs)
    _, built, client = api_runs[-1]
    row: dict[str, Any] = {
        "id": label,
        "prompt": prompt,
        "built": built["status"] == 200,
        "construct_verify_api_ms": round(api * 1000, 1),
        "construct_verify_core_ms": round(core * 1000, 1),
    }
    if not row["built"]:
        row["error"] = built.get("error")
        return row

    automaton_id = built["automaton_id"]
    level = built["verification"]["level"]
    bounded_only = has_pattern_count(doc.language)
    row.update(
        states=built["state_count"],
        kind=built["kind"],
        level=level,
        level_ok=level == "V2" or (bounded_only and level == "V1"),
    )

    auto = compile(doc).automaton
    checked = disagreements = 0
    for word in words(tuple(doc.alphabet.symbols), MAX_LENGTH):
        checked += 1
        if simulate(auto, word).accepted != matches(doc.language, word):
            disagreements += 1
    row.update(words_checked=checked, simulation_agrees=disagreements == 0)

    hashes = []
    for kind, fmt, eps_free, show_dead in VIEWS:
        query = f"format={fmt}&eps_free={str(eps_free).lower()}&show_dead={str(show_dead).lower()}"
        view = client.get(f"/v1/automata/{automaton_id}/{kind}?{query}").json()
        hashes.append(view["model_hash"] == automaton_id)
    for fmt in ("svg", "dot"):
        # The server refuses (E_VERIFY_FAILED) to send a drawing of another model.
        hashes.append(client.get(f"/v1/automata/{automaton_id}/diagram?format={fmt}").is_success)
    row.update(views_checked=len(hashes), hashes_match=all(hashes))
    return row


def main() -> None:
    cases: list[tuple[str, str, dict[str, Any]]] = []
    for entry in json.loads(BENCHMARK.read_text(encoding="utf-8"))["entries"]:
        expect = entry["expect"]
        if expect["kind"] == "ir":
            spec = {
                "alphabet": {"symbols": expect["alphabet"], "source": "user"},
                "language": expect["language"],
            }
            cases.append((str(entry["id"]), entry["prompt"], spec))
        elif expect["kind"] == "clarification":
            for option, spec in clarified(entry["prompt"]):
                cases.append((f"{entry['id']}/{option}", entry["prompt"], spec))
    rows = []
    print(f"{'#':>10}  {'level':<5} {'states':>6} {'api ms':>8} {'core ms':>8} {'words':>6}  ok")
    for label, prompt, spec in cases:
        row = measure(label, prompt, spec)
        rows.append(row)
        ok = row.get("level_ok") and row.get("simulation_agrees") and row.get("hashes_match")
        print(
            f"{label:>10}  {row.get('level', '-'):<5} {row.get('states', 0):>6} "
            f"{row['construct_verify_api_ms']:>8} {row['construct_verify_core_ms']:>8} "
            f"{row.get('words_checked', 0):>6}  {'yes' if ok else 'NO'}  {prompt[:44]}"
        )
    app.dependency_overrides.clear()

    built = [r for r in rows if r["built"]]
    summary = {
        "entries": len(rows),
        "built": len(built),
        "median_construct_verify_api_ms": round(
            statistics.median(r["construct_verify_api_ms"] for r in rows), 1
        ),
        "median_construct_verify_core_ms": round(
            statistics.median(r["construct_verify_core_ms"] for r in rows), 1
        ),
        "max_construct_verify_api_ms": max(r["construct_verify_api_ms"] for r in rows),
        "level_ok": sum(bool(r.get("level_ok")) for r in built),
        "simulation_agrees": sum(bool(r.get("simulation_agrees")) for r in built),
        "words_checked": sum(r.get("words_checked", 0) for r in built),
        "hashes_match": sum(bool(r.get("hashes_match")) for r in built),
        "views_checked": sum(r.get("views_checked", 0) for r in built),
    }
    REPORT.write_text(
        json.dumps({"summary": summary, "entries": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    n = summary["built"]
    print(
        f"\nmedian construct + verify: {summary['median_construct_verify_api_ms']} ms through "
        f"the API, {summary['median_construct_verify_core_ms']} ms in the core "
        f"(max {summary['max_construct_verify_api_ms']} ms), {len(rows)} automata, no LLM"
    )
    print(f"built and verified: {n}/{len(rows)}")
    print(f"V2, or V1 for pattern_count: {summary['level_ok']}/{n}")
    print(
        f"simulation = oracle on every word up to length {MAX_LENGTH}: "
        f"{summary['simulation_agrees']}/{n} ({summary['words_checked']} words)"
    )
    print(
        f"table and diagram hash = automaton id: {summary['hashes_match']}/{n} "
        f"({summary['views_checked']} views)"
    )


if __name__ == "__main__":
    main()
