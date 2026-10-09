import re

import pytest

from nfa_studio.compile.regex_parser import (
    Alt,
    Cat,
    Eps,
    RegexSyntaxError,
    Rep,
    Sym,
    parse_regex,
    render,
)

a, b, c = Sym("a"), Sym("b"), Sym("c")


@pytest.mark.parametrize(
    ("expr", "tree"),
    [
        ("a", a),
        ("ab", Cat((a, b))),
        ("a|b", Alt((a, b))),
        # postfix > concatenation > union
        ("ab*", Cat((a, Rep(b, "*")))),
        ("a|bc", Alt((a, Cat((b, c))))),
        ("(a|b)c", Cat((Alt((a, b)), c))),
        ("(ab)*", Rep(Cat((a, b)), "*")),
        ("a+?", Rep(Rep(a, "+"), "?")),
        ("a**", Rep(Rep(a, "*"), "*")),
        ("()", Eps()),
        ("ε", Eps()),
        ("(ε|a)b", Cat((Alt((Eps(), a)), b))),
        ("((a))", a),
        ("a|b|c", Alt((a, b, c))),
    ],
)
def test_parse(expr: str, tree: object) -> None:
    assert parse_regex(expr) == tree


@pytest.mark.parametrize(
    ("expr", "position", "problem"),
    [
        ("(a", 1, "'(' is never closed"),
        ("a)", 2, "unmatched ')'"),
        (")", 1, "unmatched ')'"),
        ("*a", 1, "'*' has nothing to apply to"),
        ("a|*", 3, "'*' has nothing to apply to"),
        ("a|", 3, "empty alternative"),
        ("(|a)", 2, "empty alternative"),
    ],
)
def test_syntax_errors_name_the_position(expr: str, position: int, problem: str) -> None:
    with pytest.raises(RegexSyntaxError, match=re.escape(f"position {position}: {problem}")):
        parse_regex(expr)


@pytest.mark.parametrize(
    ("expr", "text"),
    [
        ("(ab)*", "(ab)*"),
        ("((a)(b))", "ab"),
        ("(a|b)(a|b)", "(a|b)(a|b)"),
        ("a|(bc)", "a|bc"),
        ("(a*)*", "(a*)*"),
        ("()", "ε"),
    ],
)
def test_render_uses_only_the_parentheses_precedence_needs(expr: str, text: str) -> None:
    assert render(parse_regex(expr)) == text
    assert parse_regex(render(parse_regex(expr))) == parse_regex(expr)
