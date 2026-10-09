"""Hopcroft minimisation, used only for the optional minimal-DFA view (spec §16)."""

from collections import deque

from nfa_studio.core.determinize import merged_meaning
from nfa_studio.core.model import Automaton, is_complete_dfa, trim


def minimize(dfa: Automaton) -> Automaton:
    """The minimal complete DFA for L(dfa), by Hopcroft's partition refinement.

    Start from {F, Q∖F} and split every block whose members disagree on whether
    symbol a leads into a splitter block. After a split, the block that was waiting
    to be a splitter is replaced by both halves; otherwise only the smaller half is
    queued, which bounds the work by O(|Σ| n log n). Each final block becomes one
    state, named q0, q1, … breadth-first from the start block in alphabet order.
    """
    if not is_complete_dfa(dfa):
        raise ValueError("minimize needs a complete DFA; determinize and complete first")
    dfa = trim(dfa)
    inverse: dict[tuple[str, str], set[str]] = {}
    for (q, a), (r,) in dfa.delta.items():
        inverse.setdefault((a, r), set()).add(q)

    accepting = frozenset(dfa.final)
    rejecting = frozenset(dfa.states) - accepting
    partition = [block for block in (accepting, rejecting) if block]
    waiting = [min(partition, key=len)] if len(partition) == 2 else []
    while waiting:
        splitter = waiting.pop()
        for a in dfa.alphabet:
            into = {q for r in splitter for q in inverse.get((a, r), ())}
            refined: list[frozenset[str]] = []
            for block in partition:
                inside, outside = block & into, block - into
                if not inside or not outside:
                    refined.append(block)
                    continue
                refined.extend((inside, outside))
                if block in waiting:
                    waiting.remove(block)
                    waiting.extend((inside, outside))
                else:
                    waiting.append(min(inside, outside, key=len))
            partition = refined

    block_of = {q: block for block in partition for q in block}

    def representative(block: frozenset[str]) -> str:
        return dfa.ordered(block)[0]

    names = {block_of[dfa.start]: "q0"}
    queue = deque([block_of[dfa.start]])
    delta: dict[tuple[str, str], frozenset[str]] = {}
    while queue:
        block = queue.popleft()
        for a in dfa.alphabet:
            (r,) = dfa.targets(representative(block), a)
            target = block_of[r]
            if target not in names:
                names[target] = f"q{len(names)}"
                queue.append(target)
            delta[(names[block], a)] = frozenset({names[target]})
    return trim(
        Automaton(
            states=tuple(names.values()),
            alphabet=dfa.alphabet,
            delta=delta,
            start="q0",
            final=frozenset(name for block, name in names.items() if block <= accepting),
            meanings={name: merged_meaning(dfa, block) for block, name in names.items()},
            kind="dfa",
        )
    )
