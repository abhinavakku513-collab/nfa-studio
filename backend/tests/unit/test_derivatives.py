import pytest

from nfa_studio.reference.derivatives import Algebra, Re


@pytest.fixture
def rx() -> Algebra:
    return Algebra()


def matches(rx: Algebra, r: Re, word: str) -> bool:
    for a in word:
        r = rx.derivative(r, a)
    return r.nullable


def test_interning_makes_equal_structure_identical(rx: Algebra) -> None:
    assert rx.cat(rx.sym("a"), rx.sym("b")) is rx.cat(rx.sym("a"), rx.sym("b"))
    assert rx.parse("(ab)*") is rx.star(rx.word("ab"))


def test_empty_and_epsilon_identities(rx: Algebra) -> None:
    a = rx.sym("a")
    assert rx.cat(rx.empty, a) is rx.empty
    assert rx.cat(a, rx.empty) is rx.empty
    assert rx.cat(rx.eps, a) is a
    assert rx.cat(a, rx.eps) is a
    assert rx.alt(rx.empty, a) is a
    assert rx.inter(rx.top, a) is a
    assert rx.inter(rx.empty, a) is rx.empty
    assert rx.alt(rx.top, a) is rx.top


def test_union_and_intersection_are_flattened_sorted_and_deduplicated(rx: Algebra) -> None:
    a, b, c = rx.sym("a"), rx.sym("b"), rx.sym("c")
    assert rx.alt(a, b) is rx.alt(b, a)
    assert rx.alt(a, rx.alt(b, c)) is rx.alt(rx.alt(c, a), b)
    assert rx.alt(a, a) is a
    assert rx.inter(a, rx.inter(b, a)) is rx.inter(b, a)


def test_negation_and_star_rules(rx: Algebra) -> None:
    a = rx.sym("a")
    assert rx.neg(rx.neg(a)) is a
    assert rx.star(rx.star(a)) is rx.star(a)
    assert rx.star(rx.eps) is rx.eps
    assert rx.star(rx.empty) is rx.eps


def test_concatenation_associates_to_the_right(rx: Algebra) -> None:
    a, b, c = rx.sym("a"), rx.sym("b"), rx.sym("c")
    assert rx.cat(rx.cat(a, b), c) is rx.cat(a, rx.cat(b, c))


def test_nullable(rx: Algebra) -> None:
    a = rx.sym("a")
    assert rx.eps.nullable and not rx.empty.nullable and not a.nullable
    assert rx.star(a).nullable
    assert not rx.cat(rx.star(a), a).nullable
    assert rx.alt(a, rx.eps).nullable
    assert not rx.inter(rx.star(a), a).nullable
    assert rx.neg(a).nullable


def test_derivatives(rx: Algebra) -> None:
    a, b = rx.sym("a"), rx.sym("b")
    assert rx.derivative(a, "a") is rx.eps
    assert rx.derivative(a, "b") is rx.empty
    ab_star = rx.star(rx.cat(a, b))
    assert rx.derivative(ab_star, "a") is rx.cat(b, ab_star)
    assert rx.derivative(rx.neg(a), "a") is rx.neg(rx.eps)


@pytest.mark.parametrize(
    ("expr", "yes", "no"),
    [
        ("(ab)*", ["", "ab", "abab"], ["a", "aba"]),
        ("a+b?", ["a", "aab", "ab"], ["", "b", "abb"]),
        ("(a|ε)b", ["b", "ab"], ["", "aab"]),
        ("()", [""], ["a"]),
        ("a|bc*", ["a", "b", "bcc"], ["ac", ""]),
        ("(a*)*", ["", "aaa"], ["b"]),
    ],
)
def test_reference_parser(rx: Algebra, expr: str, yes: list[str], no: list[str]) -> None:
    r = rx.parse(expr)
    assert all(matches(rx, r, w) for w in yes)
    assert not any(matches(rx, r, w) for w in no)


def test_complement_and_intersection_semantics(rx: Algebra) -> None:
    has_aa = rx.parse("(a|b)*aa(a|b)*")
    ends_b = rx.parse("(a|b)*b")
    both = rx.inter(rx.neg(has_aa), ends_b)
    assert matches(rx, both, "abab")
    assert not matches(rx, both, "aab")
    assert not matches(rx, both, "aba")


@pytest.mark.parametrize("expr", ["(a", "a)", "*a", "a|", "a|*", "(|a)"])
def test_reference_parser_rejects_malformed_regexes(rx: Algebra, expr: str) -> None:
    with pytest.raises(ValueError):
        rx.parse(expr)
