"""Product construction for intersection (spec §4, §7.2)."""

from collections import deque

from nfa_studio.core.model import Automaton, has_epsilon, trim
from nfa_studio.ir.limits import Budget


def product(left: Automaton, right: Automaton, budget: Budget | None = None) -> Automaton:
    """Machine for L(left) ∩ L(right): δ((p, q), a) = δ_A(p, a) × δ_B(q, a).

    Both inputs must be ε-free; an ε move of one component has no partner symbol in
    the other. Only reachable pairs are built, breadth-first with symbols in alphabet
    order and each target set in (left, right) naming order, named q0, q1, … .
    """
    for side, auto in (("left", left), ("right", right)):
        if has_epsilon(auto):
            raise ValueError(f"product needs ε-free inputs; the {side} machine has ε edges")
    if left.alphabet != right.alphabet:
        raise ValueError(f"alphabets differ: {left.alphabet} and {right.alphabet}")
    budget = budget or Budget()

    def order(pair: tuple[str, str]) -> tuple[int, int]:
        return left.index[pair[0]], right.index[pair[1]]

    start = (left.start, right.start)
    names = {start: "q0"}
    queue = deque([start])
    delta: dict[tuple[str, str], frozenset[str]] = {}
    while queue:
        budget.check(len(names))
        pair = queue.popleft()
        p, q = pair
        for a in left.alphabet:
            targets = sorted(
                ((r, s) for r in left.targets(p, a) for s in right.targets(q, a)), key=order
            )
            for target in targets:
                if target not in names:
                    names[target] = f"q{len(names)}"
                    budget.check(len(names))
                    queue.append(target)
            if targets:
                delta[(names[pair], a)] = frozenset(names[t] for t in targets)
    return trim(
        Automaton(
            states=tuple(names.values()),
            alphabet=left.alphabet,
            delta=delta,
            start="q0",
            final=frozenset(
                name for (p, q), name in names.items() if p in left.final and q in right.final
            ),
            meanings={
                name: f"A: {left.meaning(p)} · B: {right.meaning(q)}"
                for (p, q), name in names.items()
            },
            kind="dfa" if left.kind == right.kind == "dfa" else "nfa",
        )
    )
