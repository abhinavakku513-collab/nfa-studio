"""HTTP routes for API v1 (spec §11).

Simulation and verification take an automaton id only; the server never accepts a
client-supplied δ (spec §11). Every table and diagram passes the §10.3 hash check.
"""

import logging
from typing import Any, Final, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field

from nfa_studio.api.deps import LLM, Automata, BySpec, Sessions, StoredAutomaton, rate_limit
from nfa_studio.api.errors import ApiError, to_api_error
from nfa_studio.compile import compile
from nfa_studio.core.model import Automaton, canonical_json, display_symbol, model_hash
from nfa_studio.core.simulate import Step, simulate
from nfa_studio.interpret import interpret
from nfa_studio.ir.limits import LIMITS, Limits
from nfa_studio.ir.normalize import normalize, spec_hash
from nfa_studio.ir.schema import IR_VERSION, NODE_TYPES, Assumption, IRDocument
from nfa_studio.render import ensure_consistent
from nfa_studio.render.json_graph import diagram_graph, graph_json
from nfa_studio.render.svg import MEDIA_TYPES, render_diagram
from nfa_studio.render.table import build_table, table_csv, table_json, table_latex, table_markdown
from nfa_studio.session import clarify
from nfa_studio.verify.ladder import Report, VerificationFailed, verify

API_VERSION: Final = "v1"
logger = logging.getLogger("nfa_studio.api")


class ErrorModel(BaseModel):
    code: str
    message: str
    detail: dict[str, Any]


class ErrorBody(BaseModel):
    """Every error response (spec §11.2); `message` names the reason and the next action."""

    error: ErrorModel


# Declared so the generated client types cover failures as well as successes.
ERROR_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    status: {"model": ErrorBody} for status in (404, 413, 422, 429, 500, 504)
}

public = APIRouter(prefix=f"/{API_VERSION}")
api = APIRouter(
    prefix=f"/{API_VERSION}", dependencies=[Depends(rate_limit)], responses=ERROR_RESPONSES
)

Edge = tuple[str, str, str]


class _Request(BaseModel):
    # Unknown fields are refused, so no client-supplied δ can ride along (spec §11).
    model_config = ConfigDict(extra="forbid")


class Health(BaseModel):
    status: Literal["ok"]


class Capabilities(BaseModel):
    api_version: Literal["v1"]
    ir_version: Literal["1.0"]
    node_types: list[str]
    limits: Limits


class OptionModel(BaseModel):
    id: str
    label: str


class QuestionModel(BaseModel):
    id: str
    topic: str
    text: str
    options: list[OptionModel]


class InterpretRequest(_Request):
    text: str
    # A new interpretation replaces this earlier session, if it still exists.
    session_id: str | None = None


class AnswerRequest(_Request):
    question_id: str
    option_id: str


class InterpretResponse(BaseModel):
    status: Literal["ready", "clarification_required", "edit_ir"]
    code: Literal["E_NEEDS_CLARIFICATION"] | None = None
    session_id: str | None = None
    question: QuestionModel | None = None
    partial_ir: dict[str, Any] | None = None
    ir: IRDocument | None = None
    missing: list[str] = Field(default_factory=list)
    confidence: float


class CheckModel(BaseModel):
    level: str
    evidence: str


class VerificationModel(BaseModel):
    automaton_id: str
    level: Literal["V0", "V1", "V2", "V3"]
    badge: Literal["grey", "amber", "green"]
    checks: list[CheckModel]
    bounded_length: int
    property_runs: int
    notes: list[str]


class LogEntryModel(BaseModel):
    node: str
    text: str
    states: int


class AutomatonSummary(BaseModel):
    automaton_id: str
    kind: Literal["enfa", "nfa", "dfa"]
    state_count: int
    verification: VerificationModel
    explanation: list[LogEntryModel]
    assumptions: list[Assumption]
    warnings: list[str]


class FiveTuple(BaseModel):
    Q: list[str]
    Sigma: list[str]
    delta: list[tuple[str, str, list[str]]]
    q0: str
    F: list[str]


class AutomatonDetail(AutomatonSummary):
    five_tuple: FiveTuple
    meanings: dict[str, str]
    dead: list[str]
    spec: IRDocument


class TableRowModel(BaseModel):
    state: str
    marker: str
    start: bool
    accepting: bool
    cells: list[list[str]]


class TableModel(BaseModel):
    model_hash: str
    eps_free: bool
    columns: list[str]
    rows: list[TableRowModel]
    hidden_dead_states: list[str]


class GraphNodeModel(BaseModel):
    id: str
    name: str
    start: bool
    accepting: bool
    dead: bool
    meaning: str
    short_meaning: str


class GraphEdgeModel(BaseModel):
    id: str
    source: str
    target: str
    symbols: list[str]
    label: str
    epsilon: bool


class StartEdgeModel(BaseModel):
    id: str
    target: str


class IdMapModel(BaseModel):
    states: dict[str, str]
    transitions: dict[str, str]


class GraphModel(BaseModel):
    model_hash: str
    eps_free: bool
    start_edge: StartEdgeModel
    nodes: list[GraphNodeModel]
    edges: list[GraphEdgeModel]
    id_map: IdMapModel
    hidden_dead_states: list[str]


class SimulateRequest(_Request):
    word: str
    witness: bool = True
    page: int = Field(default=1, ge=1)


class StepModel(BaseModel):
    index: int
    symbol: str | None
    moved: list[str]
    after: list[str]
    accepting_present: bool
    final_accepted: bool | None
    transitions: list[Edge]
    epsilon_layers: list[list[Edge]]


class SimulateResponse(BaseModel):
    automaton_id: str
    word: str
    valid: bool
    accepted: bool
    witness: list[Edge] | None
    steps: list[StepModel]
    page: int
    pages: int
    total_steps: int


class BatchRequest(_Request):
    words: list[str]


class BatchResult(BaseModel):
    word: str
    valid: bool
    accepted: bool | None
    error: ErrorModel | None


class BatchResponse(BaseModel):
    automaton_id: str
    results: list[BatchResult]


class VerifyRequest(_Request):
    level: Literal["V0", "V1", "V2", "V3"] = "V3"


class VerifyResponse(VerificationModel):
    requested: str
    reached: bool


@public.get("/health")
def health() -> Health:
    """Liveness and readiness."""
    return Health(status="ok")


@public.get("/capabilities")
def capabilities() -> Capabilities:
    """Supported node types, limits and versions."""
    return Capabilities(
        api_version=API_VERSION,
        ir_version=IR_VERSION,
        node_types=list(NODE_TYPES),
        limits=LIMITS,
    )


@api.post("/interpret")
def interpret_text(body: InterpretRequest, sessions: Sessions, llm: LLM) -> InterpretResponse:
    """Text in; a confirmed-ready IR, one clarification question, or the manual form."""
    if len(body.text) > LIMITS.max_text_len:
        raise ApiError(
            "E_INPUT_TOO_LONG",
            f"The description has {len(body.text)} characters; the limit is "
            f"{LIMITS.max_text_len}. Shorten it.",
            {"length": len(body.text), "limit": LIMITS.max_text_len},
        )
    if body.session_id:
        sessions.delete(body.session_id)
    return _respond(clarify.open_draft(interpret(body.text, llm), body.text), sessions)


@api.post("/interpret/{session_id}/answer")
def answer_question(session_id: str, body: AnswerRequest, sessions: Sessions) -> InterpretResponse:
    """Merge one clarification answer into the session's partial IR."""
    session = sessions.get(session_id)
    if session is None:
        raise ApiError(
            "E_SESSION_NOT_FOUND",
            f"No clarification session {session_id} exists, or it expired after "
            f"{LIMITS.session_ttl_seconds / 60:g} minutes. Send the description again.",
            {"session_id": session_id},
        )
    outcome = clarify.answer(session, body.question_id, body.option_id)
    if not isinstance(outcome, clarify.Asking):
        sessions.delete(session_id)
    return _respond(outcome, sessions)


def _respond(outcome: clarify.Outcome, sessions: Sessions) -> InterpretResponse:
    match outcome:
        case clarify.Ready():
            return InterpretResponse(status="ready", ir=outcome.ir, confidence=outcome.confidence)
        case clarify.Asking():
            sessions.put(outcome.session.id, outcome.session)
            question = outcome.question
            return InterpretResponse(
                status="clarification_required",
                code="E_NEEDS_CLARIFICATION",
                session_id=outcome.session.id,
                question=QuestionModel(
                    id=question.id,
                    topic=question.topic,
                    text=question.text,
                    options=[OptionModel(id=o.id, label=o.label) for o in question.options],
                ),
                partial_ir=outcome.partial_ir,
                confidence=outcome.session.confidence,
            )
        case clarify.EditIR():
            return InterpretResponse(
                status="edit_ir",
                partial_ir=outcome.partial_ir,
                missing=list(outcome.missing),
                confidence=outcome.confidence,
            )


@api.post("/automata")
def create_automaton(spec: IRDocument, automata: Automata, by_spec: BySpec) -> AutomatonSummary:
    """Construct and verify from a confirmed IR; identical specifications are built once."""
    doc = normalize(spec)
    key = spec_hash(doc)
    cached = by_spec.get(key)
    stored = automata.get(cached) if cached else None
    if stored is None:
        compiled = compile(doc)
        try:
            report = verify(compiled.automaton, doc)
        except VerificationFailed as exc:
            # spec §8.2: a failed check is logged with the IR for the developers.
            logger.error("%s for %s", exc, canonical_json(doc.model_dump(mode="json")))
            raise
        stored = StoredAutomaton(compiled.automaton, doc, compiled, report)
        automaton_id = model_hash(compiled.automaton)
        automata.put(automaton_id, stored)
        by_spec.put(key, automaton_id)
    return _summary(stored)


@api.get("/automata/{automaton_id}")
def get_automaton(automaton_id: str, automata: Automata) -> AutomatonDetail:
    """Five-tuple, δ, explanation, assumptions and verification report."""
    stored = _stored(automaton_id, automata)
    auto = stored.automaton
    summary = _summary(stored)
    return AutomatonDetail(
        **summary.model_dump(),
        five_tuple=FiveTuple(
            Q=list(auto.states),
            Sigma=list(auto.alphabet),
            delta=[
                (q, display_symbol(a), list(auto.ordered(dsts)))
                for (q, a), dsts in sorted(
                    auto.delta.items(), key=lambda item: (auto.index[item[0][0]], item[0][1])
                )
            ],
            q0=auto.start,
            F=list(auto.ordered(auto.final)),
        ),
        meanings=dict(auto.meanings),
        dead=list(auto.ordered(auto.dead)),
        spec=stored.spec,
    )


TABLE_MEDIA: Final = {"csv": "text/csv", "md": "text/markdown", "tex": "application/x-tex"}


@api.get(
    "/automata/{automaton_id}/table",
    response_model=TableModel,
    responses={200: {"content": {media: {} for media in TABLE_MEDIA.values()}}},
)
def get_table(
    automaton_id: str,
    automata: Automata,
    format: Literal["json", "csv", "md", "tex"] = "json",
    eps_free: bool = False,
    show_dead: bool = False,
) -> Any:
    """Transition table as JSON, CSV, Markdown or LaTeX (spec §10.1)."""
    stored = _stored(automaton_id, automata)
    table = build_table(stored.automaton, eps_free=eps_free, show_dead=show_dead)
    ensure_consistent(automaton_id, table)
    if format == "json":
        return table_json(table)
    text = {"csv": table_csv, "md": table_markdown, "tex": table_latex}[format](table)
    return Response(text, media_type=f"{TABLE_MEDIA[format]}; charset=utf-8")


@api.get(
    "/automata/{automaton_id}/diagram",
    response_model=GraphModel,
    responses={200: {"content": {media: {} for media in MEDIA_TYPES.values()}}},
)
def get_diagram(
    automaton_id: str,
    automata: Automata,
    format: Literal["svg", "png", "dot", "json"] = "svg",
    eps_free: bool = False,
    show_dead: bool = False,
) -> Any:
    """Diagram as SVG, PNG, DOT or the JSON graph used by the client (spec §10.2)."""
    stored = _stored(automaton_id, automata)
    if format == "json":
        graph = diagram_graph(stored.automaton, show_dead=show_dead, eps_free=eps_free)
        ensure_consistent(automaton_id, graph)
        return graph_json(graph)
    diagram = render_diagram(stored.automaton, format, show_dead=show_dead, eps_free=eps_free)
    ensure_consistent(automaton_id, diagram)
    return Response(diagram.content, media_type=diagram.media_type)


@api.post("/automata/{automaton_id}/simulate")
def simulate_word(automaton_id: str, body: SimulateRequest, automata: Automata) -> SimulateResponse:
    """One word: the full trace, paginated 200 steps at a time, and a witness if accepted."""
    stored = _stored(automaton_id, automata)
    trace = simulate(stored.automaton, body.word, witness=body.witness)
    size = LIMITS.trace_page_size
    pages = (len(trace.steps) + size - 1) // size
    if body.page > pages:
        raise ApiError(
            "E_SCHEMA_INVALID",
            f"Page {body.page} does not exist; the trace has {pages} pages. Ask for page 1 "
            f"to {pages}.",
            {"errors": [f"page: at most {pages}"]},
        )
    shown = trace.steps[(body.page - 1) * size : body.page * size]
    return SimulateResponse(
        automaton_id=automaton_id,
        word=body.word,
        valid=True,
        accepted=trace.accepted,
        witness=[_edge(e) for e in trace.witness] if trace.witness is not None else None,
        steps=[_step(s) for s in shown],
        page=body.page,
        pages=pages,
        total_steps=len(trace.steps),
    )


@api.post("/automata/{automaton_id}/simulate/batch")
def simulate_batch(automaton_id: str, body: BatchRequest, automata: Automata) -> BatchResponse:
    """Up to 100 words; a word that cannot be read gets its own error, not the batch."""
    stored = _stored(automaton_id, automata)
    if len(body.words) > LIMITS.max_batch_size:
        raise ApiError(
            "E_INPUT_TOO_LONG",
            f"The batch has {len(body.words)} words; the limit is {LIMITS.max_batch_size}. "
            "Split it into smaller batches.",
            {"length": len(body.words), "limit": LIMITS.max_batch_size},
        )
    results = []
    for word in body.words:
        try:
            accepted = simulate(stored.automaton, word, witness=False).accepted
        except Exception as exc:
            error = to_api_error(exc)
            results.append(
                BatchResult(
                    word=word,
                    valid=False,
                    accepted=None,
                    error=ErrorModel(code=error.code, message=error.message, detail=error.detail),
                )
            )
        else:
            results.append(BatchResult(word=word, valid=True, accepted=accepted, error=None))
    return BatchResponse(automaton_id=automaton_id, results=results)


@api.post("/automata/{automaton_id}/verify")
def verify_automaton(
    automaton_id: str, automata: Automata, body: VerifyRequest | None = None
) -> VerifyResponse:
    """Re-run verification (cached by automaton and specification) and say if `level` is met."""
    stored = _stored(automaton_id, automata)
    report = verify(stored.automaton, stored.spec)
    requested = (body or VerifyRequest()).level
    return VerifyResponse(
        **_verification(report).model_dump(),
        requested=requested,
        reached=any(check.level == requested for check in report.checks),
    )


def _stored(automaton_id: str, automata: Automata) -> StoredAutomaton:
    stored = automata.get(automaton_id)
    if stored is None:
        raise ApiError(
            "E_AUTOMATON_NOT_FOUND",
            f"No automaton {automaton_id} exists, or it expired after "
            f"{LIMITS.automaton_ttl_seconds / 60:g} minutes. Build it again with "
            "POST /v1/automata.",
            {"automaton_id": automaton_id},
        )
    return stored


def _verification(report: Report) -> VerificationModel:
    return VerificationModel(
        automaton_id=report.automaton_id,
        level=report.level,
        badge=report.badge,
        checks=[CheckModel(level=c.level, evidence=c.evidence) for c in report.checks],
        bounded_length=report.bounded_length,
        property_runs=report.property_runs,
        notes=list(report.notes),
    )


def _summary(stored: StoredAutomaton) -> AutomatonSummary:
    auto: Automaton = stored.automaton
    return AutomatonSummary(
        automaton_id=model_hash(auto),
        kind=auto.kind,
        state_count=len(auto.states),
        verification=_verification(stored.report),
        explanation=[
            LogEntryModel(node=e.node, text=e.text, states=e.states) for e in stored.compiled.log
        ],
        assumptions=list(stored.spec.assumptions),
        warnings=list(stored.compiled.warnings),
    )


def _edge(edge: Edge) -> Edge:
    q, a, r = edge
    return (q, display_symbol(a), r)


def _step(step: Step) -> StepModel:
    return StepModel(
        index=step.index,
        symbol=step.symbol,
        moved=list(step.moved),
        after=list(step.after),
        accepting_present=step.accepting_present,
        final_accepted=step.final_accepted,
        transitions=[_edge(e) for e in step.transitions],
        epsilon_layers=[[_edge(e) for e in layer] for layer in step.epsilon_layers],
    )
