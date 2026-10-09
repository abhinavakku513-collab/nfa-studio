"""The clarification state machine (spec §6.3, CLAUDE.md C13).

A draft's holes become questions, asked one at a time. An answer fills its hole with
the value that option stands for; interpretation is not restarted. At most two
questions are asked for one request; if more would be needed, the partial IR goes to
the manual form instead (status edit_ir).
"""

import copy
import secrets
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import ClassVar

from nfa_studio.interpret.ambiguity import EDIT_OPTION, Hole, Lazy, Option, Topic
from nfa_studio.interpret.rule_parser import Draft
from nfa_studio.ir.limits import LIMITS
from nfa_studio.ir.normalize import validate_ir
from nfa_studio.ir.schema import IRDocument

Path = tuple[str | int, ...]


class UnknownAnswer(Exception):
    code: ClassVar[str] = "E_SCHEMA_INVALID"


@dataclass(frozen=True)
class Question:
    id: str
    topic: Topic
    text: str
    options: tuple[Option, ...]
    path: Path
    values: Mapping[str, object]


@dataclass
class Session:
    id: str
    text: str
    draft: dict[str, object]
    asked: int
    current: Question
    confidence: float


@dataclass(frozen=True)
class Ready:
    ir: IRDocument
    confidence: float


@dataclass(frozen=True)
class Asking:
    session: Session
    question: Question
    partial_ir: dict[str, object]


@dataclass(frozen=True)
class EditIR:
    partial_ir: dict[str, object]
    missing: tuple[Topic, ...]
    confidence: float


Outcome = Ready | Asking | EditIR


def open_draft(draft: Draft, text: str) -> Outcome:
    """Start on a fresh draft: ready, the first question, or the manual form."""
    ir = copy.deepcopy(draft.ir)
    return _next(ir, text, asked=0, confidence=draft.confidence, session_id=None)


def answer(session: Session, question_id: str, option_id: str) -> Outcome:
    """Merge one answer into the session's draft and move on."""
    question = session.current
    if question_id != question.id:
        raise UnknownAnswer(
            f"Question {question_id} is not the one pending; answer {question.id} first."
        )
    if option_id == EDIT_OPTION.id:
        return EditIR(partial(session.draft), (question.topic,), session.confidence)
    if option_id not in question.values:
        allowed = ", ".join(o.id for o in question.options)
        raise UnknownAnswer(
            f"'{option_id}' is not an option of {question.id}; use one of {allowed}."
        )
    _set(session.draft, question.path, copy.deepcopy(question.values[option_id]))
    clarifications = session.draft["clarifications"]
    assert isinstance(clarifications, list)
    clarifications.append({"topic": question.topic, "answer": option_id})
    return _next(session.draft, session.text, session.asked, session.confidence, session.id)


def _next(
    ir: dict[str, object], text: str, asked: int, confidence: float, session_id: str | None
) -> Outcome:
    holes = list(_holes(ir))
    if not holes:
        return Ready(validate_ir(resolve(ir)), confidence)
    if asked + len(holes) > LIMITS.max_questions:
        return EditIR(partial(ir), tuple(h.topic for _, h in holes), confidence)
    path, hole = holes[0]
    question = Question(
        f"Q{asked + 1}", hole.topic, hole.text, (*hole.options, EDIT_OPTION), path, hole.values
    )
    session = Session(
        session_id or f"s_{secrets.token_hex(8)}", text, ir, asked + 1, question, confidence
    )
    return Asking(session, question, partial(ir))


def _holes(value: object, path: Path = ()) -> Iterator[tuple[Path, Hole]]:
    """Every open choice, in document order; values held inside a hole are not searched."""
    if isinstance(value, Hole):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _holes(child, (*path, key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _holes(child, (*path, i))


def _set(root: dict[str, object], path: Path, value: object) -> None:
    target: object = root
    for key in path[:-1]:
        target = _step(target, key)
    last = path[-1]
    if isinstance(target, list):
        if not isinstance(last, int):
            raise KeyError(path)
        target[last] = value
    elif isinstance(target, dict):
        target[last] = value
    else:
        raise KeyError(path)


def _step(container: object, key: str | int) -> object:
    if isinstance(container, dict):
        return container[key]
    if isinstance(container, list) and isinstance(key, int):
        return container[key]
    raise KeyError(key)


def _alphabet(ir: dict[str, object]) -> tuple[str, ...]:
    """The draft's symbols; while the alphabet is still a question, its first reading."""
    alphabet = ir["alphabet"]
    assert isinstance(alphabet, dict)
    symbols = alphabet["symbols"]
    if isinstance(symbols, Hole):
        symbols = symbols.values[symbols.options[0].id]
    assert isinstance(symbols, list)
    return tuple(symbols)


def resolve(ir: dict[str, object]) -> dict[str, object]:
    """Plain IR JSON with every alphabet-dependent part built; there must be no holes."""
    resolved = _resolve(ir, _alphabet(ir), keep_holes=False)
    assert isinstance(resolved, dict)
    return resolved


def partial(ir: dict[str, object]) -> dict[str, object]:
    """The draft as shown to the client: open fields left out (spec §11.1 example)."""
    shown = _resolve(ir, _alphabet(ir), keep_holes=True)
    assert isinstance(shown, dict)
    return shown


_OPEN = object()


def _resolve(value: object, alphabet: tuple[str, ...], keep_holes: bool) -> object:
    if isinstance(value, Lazy):
        return _resolve(value.make(alphabet), alphabet, keep_holes)
    if isinstance(value, Hole):
        if not keep_holes:
            raise ValueError(f"unanswered {value.topic} question")
        return _OPEN
    if isinstance(value, dict):
        out = {k: _resolve(v, alphabet, keep_holes) for k, v in value.items()}
        return {k: v for k, v in out.items() if v is not _OPEN}
    if isinstance(value, list):
        return [
            None if v is _OPEN else v for v in (_resolve(x, alphabet, keep_holes) for x in value)
        ]
    return value
