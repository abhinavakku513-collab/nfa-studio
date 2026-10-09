from nfa_studio.core.closure import eclose, eclose_state, eclose_with_pred, step
from nfa_studio.core.model import EPS
from tests.support.machines import machine

# q0 -ε-> q1 -ε-> q2 -ε-> q0 is a cycle; q2 -ε-> q3 leaves it; q4 is reached by a only.
CYCLE = machine(
    [
        ("q0", "ε", "q1"),
        ("q1", "ε", "q2"),
        ("q2", "ε", "q0"),
        ("q2", "ε", "q3"),
        ("q0", "a", "q4"),
        ("q4", "ε", "q4"),
    ],
    final={"q3"},
)


def test_eclose_terminates_on_epsilon_cycles() -> None:
    assert eclose_state(CYCLE, "q0") == {"q0", "q1", "q2", "q3"}
    assert eclose_state(CYCLE, "q1") == {"q0", "q1", "q2", "q3"}
    assert eclose_state(CYCLE, "q4") == {"q4"}


def test_eclose_is_memoised() -> None:
    assert eclose_state(CYCLE, "q2") is eclose_state(CYCLE, "q2")


def test_eclose_of_the_empty_set_is_empty() -> None:
    assert eclose(CYCLE, ()) == frozenset()


def test_step_on_the_empty_set_is_empty() -> None:
    assert step(CYCLE, frozenset(), "a") == frozenset()


def test_step_closes_after_moving() -> None:
    auto = machine([("q0", "a", "q1"), ("q1", "ε", "q2")], final={"q2"})
    assert step(auto, {"q0"}, "a") == {"q1", "q2"}
    assert step(auto, {"q0"}, "b") == frozenset()


def test_bfs_records_shortest_epsilon_chains() -> None:
    # q0 reaches q3 directly and through q1 -> q2; BFS must keep the direct edge.
    auto = machine(
        [("q0", "ε", "q1"), ("q1", "ε", "q2"), ("q2", "ε", "q3"), ("q0", "ε", "q3")],
        final={"q3"},
    )
    closure = eclose_with_pred(auto, {"q0"})
    assert closure.states == {"q0", "q1", "q2", "q3"}
    assert closure.pred == {"q1": ("q0", EPS), "q3": ("q0", EPS), "q2": ("q1", EPS)}
    assert closure.layers == (
        (("q0", EPS, "q1"), ("q0", EPS, "q3")),
        (("q1", EPS, "q2"),),
    )


def test_bfs_layers_keep_every_edge_into_a_newly_reached_state() -> None:
    auto = machine([("q0", "ε", "q2"), ("q1", "ε", "q2")], final={"q2"})
    closure = eclose_with_pred(auto, {"q0", "q1"})
    assert closure.layers == ((("q0", EPS, "q2"), ("q1", EPS, "q2")),)
    assert closure.pred == {"q2": ("q0", EPS)}


def test_bfs_on_a_cycle_matches_the_memoised_closure() -> None:
    closure = eclose_with_pred(CYCLE, {"q1"})
    assert closure.states == eclose(CYCLE, {"q1"})
    assert "q1" not in closure.pred
