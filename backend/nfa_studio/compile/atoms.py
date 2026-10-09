"""Atom constructions with their state meanings (spec §7.1), and the machine builder."""

from collections import deque
from collections.abc import Iterable

from nfa_studio.core.model import DEAD_MEANING, EPS, Automaton, Kind, trim
from nfa_studio.ir.schema import CountOp


class Builder:
    """Collects the states and edges of one machine under construction.

    States get integer ids in creation order (named s0, s1, …). Naming later breaks
    ties inside a destination set by these ids, so construction order alone fixes the
    final names (CLAUDE.md item 6).
    """

    def __init__(self, alphabet: tuple[str, ...]) -> None:
        self.alphabet = alphabet
        self._states: list[str] = []
        self._meanings: dict[str, str] = {}
        self._delta: dict[tuple[str, str], set[str]] = {}

    def state(self, meaning: str) -> str:
        name = f"s{len(self._states)}"
        self._states.append(name)
        self._meanings[name] = meaning
        return name

    def edge(self, q: str, a: str, r: str) -> None:
        self._delta.setdefault((q, a), set()).add(r)

    def loop_all(self, q: str) -> None:
        for a in self.alphabet:
            self.edge(q, a, q)

    def embed(self, auto: Automaton) -> dict[str, str]:
        """Copy `auto` in, keeping its state order; returns old name → new name."""
        names = {q: self.state(auto.meaning(q)) for q in auto.states}
        for (q, a), dsts in auto.delta.items():
            for r in dsts:
                self.edge(names[q], a, names[r])
        return names

    def build(self, start: str, final: Iterable[str]) -> Automaton:
        """The finished machine, trimmed, with its kind read off its structure."""
        kind: Kind = "dfa"
        for (_, a), dsts in self._delta.items():
            if a == EPS:
                kind = "enfa"
                break
            if len(dsts) > 1:
                kind = "nfa"
        return trim(
            Automaton(
                states=tuple(self._states),
                alphabet=self.alphabet,
                delta={key: frozenset(dsts) for key, dsts in self._delta.items()},
                start=start,
                final=frozenset(final),
                meanings=self._meanings,
                kind=kind,
            )
        )


def kmp_table(pattern: str, alphabet: tuple[str, ...]) -> tuple[list[dict[str, int]], int]:
    """KMP transition table and the border of the whole pattern.

    `table[k][a]` (0 ≤ k ≤ m) is the length of the longest prefix of the pattern that
    is a suffix of pattern[:k] + a. The second value is π(m), the longest proper
    border of the pattern, where an overlapping search resumes after a match (C3).
    """
    m = len(pattern)
    border = [0] * (m + 1)
    k = 0
    for i in range(1, m):
        while k and pattern[i] != pattern[k]:
            k = border[k]
        if pattern[i] == pattern[k]:
            k += 1
        border[i + 1] = k
    table: list[dict[str, int]] = []
    for k in range(m + 1):
        table.append(
            {
                a: k + 1 if k < m and pattern[k] == a else 0 if k == 0 else table[border[k]][a]
                for a in alphabet
            }
        )
    return table, border[m]


def starts_with(pattern: str, alphabet: tuple[str, ...]) -> Automaton:
    """qᵢ: the first i symbols equal pattern[:i]; a mismatch has no edge; q_m loops on Σ."""
    b = Builder(alphabet)
    chain = [b.state("nothing read yet")]
    chain += [
        b.state(f"read {pattern[:i]}, the start of {pattern}") for i in range(1, len(pattern))
    ]
    chain.append(b.state(f"started with {pattern}"))
    for i, a in enumerate(pattern):
        b.edge(chain[i], a, chain[i + 1])
    b.loop_all(chain[-1])
    return b.build(chain[0], [chain[-1]])


def ends_with(pattern: str, alphabet: tuple[str, ...]) -> Automaton:
    """q₀ loops on Σ and guesses where the final occurrence begins; q_m has no outgoing edge.

    A branch that reaches q_m survives only if the input ends there, which is why
    this machine is genuinely nondeterministic (spec §7.1).
    """
    b = Builder(alphabet)
    chain = _guessing_chain(b, pattern, f"completed {pattern} (accepts only if the input ends)")
    return b.build(chain[0], [chain[-1]])


def contains(pattern: str, alphabet: tuple[str, ...]) -> Automaton:
    """As `ends_with`, plus a loop on Σ at q_m."""
    b = Builder(alphabet)
    chain = _guessing_chain(b, pattern, f"found {pattern}")
    b.loop_all(chain[-1])
    return b.build(chain[0], [chain[-1]])


def _guessing_chain(b: Builder, pattern: str, last_meaning: str) -> list[str]:
    chain = [b.state("scanning (no commitment)")]
    chain += [
        b.state(f"guessed that {pattern} starts here; read {pattern[:i]}")
        for i in range(1, len(pattern))
    ]
    chain.append(b.state(last_meaning))
    b.loop_all(chain[0])
    for i, a in enumerate(pattern):
        b.edge(chain[i], a, chain[i + 1])
    return chain


def avoids(pattern: str, alphabet: tuple[str, ...]) -> Automaton:
    """KMP DFA for "does not contain pattern", with an explicit dead state (spec §7.2).

    State k means the longest suffix read so far that is a prefix of the pattern has
    length k. Reaching k = m means the pattern occurred, which no continuation can
    undo. Built directly, this avoids determinizing contains(pattern).
    """
    m = len(pattern)
    table, _ = kmp_table(pattern, alphabet)
    b = Builder(alphabet)
    progress = [b.state(_kmp_meaning(pattern, k)) for k in range(m)]
    dead = b.state(DEAD_MEANING)
    for k in range(m):
        for a in alphabet:
            nxt = table[k][a]
            b.edge(progress[k], a, dead if nxt == m else progress[nxt])
    b.loop_all(dead)
    return b.build(progress[0], progress)


def _kmp_meaning(pattern: str, k: int) -> str:
    if k == 0:
        return f"no part of {pattern} matched"
    return f"last {k} symbol{'s' if k > 1 else ''} match {pattern[:k]}, the start of {pattern}"


def symbol_parity(symbol: str, even: bool, alphabet: tuple[str, ...]) -> Automaton:
    """Two states, even and odd; the counted symbol toggles them, other symbols loop."""
    b = Builder(alphabet)
    states = {
        True: b.state(f"even number of {symbol} so far"),
        False: b.state(f"odd number of {symbol} so far"),
    }
    for parity, q in states.items():
        for a in alphabet:
            b.edge(q, a, states[not parity] if a == symbol else q)
    return b.build(states[True], [states[even]])


def symbol_count(symbol: str, op: CountOp, n: int, alphabet: tuple[str, ...]) -> Automaton:
    """cᵢ = i occurrences seen, i ≤ n; other symbols loop.

    eq and le give an occurrence beyond n no edge, so that branch dies; ge saturates
    at c_n, which loops on every symbol.
    """
    b = Builder(alphabet)
    counters = [b.state(f"seen {symbol} {i} time{'' if i == 1 else 's'}") for i in range(n)]
    counters.append(
        b.state(f"seen {symbol} at least {n} times" if op == "ge" else f"seen {symbol} {n} times")
    )
    for i, q in enumerate(counters):
        for a in alphabet:
            if a != symbol:
                b.edge(q, a, q)
            elif i < n:
                b.edge(q, a, counters[i + 1])
    if op == "ge":
        b.loop_all(counters[n])
    final = {"eq": [counters[n]], "ge": [counters[n]], "le": counters}[op]
    return b.build(counters[0], final)


def length_mod(m: int, r: int, alphabet: tuple[str, ...]) -> Automaton:
    """rᵢ = length mod m is i; every symbol moves rᵢ to r_(i+1) mod m."""
    b = Builder(alphabet)
    residues = [b.state(f"length mod {m} is {i}") for i in range(m)]
    for i, q in enumerate(residues):
        for a in alphabet:
            b.edge(q, a, residues[(i + 1) % m])
    return b.build(residues[0], [residues[r]])


def literal_set(words: tuple[str, ...], alphabet: tuple[str, ...]) -> Automaton:
    """A trie: each state is a prefix read so far; word ends accept."""
    b = Builder(alphabet)
    root = b.state("nothing read yet")
    nodes = {"": root}
    for word in sorted(words):
        for i in range(1, len(word) + 1):
            prefix = word[:i]
            if prefix not in nodes:
                nodes[prefix] = b.state(f"read {prefix}")
                b.edge(nodes[word[: i - 1]], word[i - 1], nodes[prefix])
    return b.build(root, [nodes[w] for w in words])


def pattern_count(
    pattern: str, op: CountOp, n: int, overlap: bool, alphabet: tuple[str, ...]
) -> Automaton:
    """The KMP DFA of the pattern paired with an occurrence counter (C3).

    State (k, c): k pattern symbols are matched in progress and c occurrences have
    been counted. On a full match the counter goes up and k becomes π(m) with overlap
    or 0 without. Once the count is decided the KMP part no longer matters, so the
    saturated count is one state: for ge, "at least n", which loops on Σ; for eq and
    le, "more than n", a dead state.
    """
    m = len(pattern)
    table, resume = kmp_table(pattern, alphabet)
    saturation = n if op == "ge" else n + 1
    b = Builder(alphabet)
    if op == "ge":
        saturated = f"at least {n} occurrences of {pattern}"
    else:
        saturated = f"more than {n} occurrences of {pattern}; {DEAD_MEANING}"

    def meaning(key: tuple[int, int]) -> str:
        k, c = key
        if c == saturation:
            return saturated
        return f"{c} occurrence{'' if c == 1 else 's'} of {pattern}; {_kmp_meaning(pattern, k)}"

    def canonical(key: tuple[int, int]) -> tuple[int, int]:
        return (0, saturation) if key[1] == saturation else key

    start = canonical((0, 0))
    names = {start: b.state(meaning(start))}
    queue = deque([start])
    while queue:
        key = queue.popleft()
        k, c = key
        for a in alphabet:
            if c == saturation:
                target = key
            else:
                nxt = table[k][a]
                target = canonical((resume if overlap else 0, c + 1) if nxt == m else (nxt, c))
            if target not in names:
                names[target] = b.state(meaning(target))
                queue.append(target)
            b.edge(names[key], a, names[target])
    # For ge the counter never passes n, so c == n is exactly c >= n.
    final = [q for (_, c), q in names.items() if (c <= n if op == "le" else c == n)]
    return b.build(names[start], final)
