# NFA Studio

Natural-language-to-automaton workbench. The authoritative specification is
`docs/NFA_Studio_Spec_v1.pdf` (v1.0, 17 pages). Read the sections a task touches
before writing code for it. This file records the decisions and corrections that
apply on top of the spec. Where the two disagree, this file wins; every such
point below says why.

## Repository layout

```
nfa-studio/
  CLAUDE.md
  docs/NFA_Studio_Spec_v1.pdf
  backend/
    pyproject.toml          ruff, mypy, pytest config
    requirements.txt
    nfa_studio/             package layout exactly as spec §3.2, plus api/app.py
    tests/
      unit/  property/  integration/
      benchmark/benchmark_v1.json   (already written; do not edit prompts)
  frontend/                 Next.js (App Router) + TypeScript + Tailwind
```

`nfa_studio/core`, `ir`, `compile`, `reference`, `verify` must never import from
`api`, `interpret/llm_adapter.py`, FastAPI or any web library (spec Figure 2).

## Commands

The developer is on Windows with VS Code. Use PowerShell syntax when giving
commands; scripts must also work on macOS/Linux.

Backend (from `backend/`):
- venv: `python -m venv .venv` then `.venv\Scripts\Activate.ps1`
- install: `pip install -r requirements.txt`
- run: `uvicorn nfa_studio.api.app:app --reload --port 8000`
- check: `pytest -q`, `ruff check .`, `ruff format --check .`, `mypy nfa_studio`

Frontend (from `frontend/`):
- run: `npm run dev` (port 3000, proxies `/v1/*` to `http://127.0.0.1:8000`)
- check: `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`
- API types: `npm run gen:api` (openapi-typescript from the running backend's
  `/openapi.json` into `src/lib/api/schema.d.ts`; commit the generated file)

Graphviz's `dot` must be on PATH. If `dot -V` fails, stop and tell the developer;
do not silently fall back to another layout engine.

## Definition of done

A task is finished only when every check command above has been run in this
session and passes. Paste the final summary lines of the output. Never write
"tests pass" for tests that were not executed (spec §14.3). If something fails,
fix the cause; do not skip, xfail, or loosen a test to make it green unless the
test itself is wrong, and then say so explicitly.

## Code style

Write the code the way a careful engineer on a small team would.

- Use the spec's vocabulary for names: `eclose`, `step`, `delta`, `final`,
  `alphabet`, `active`, `witness`, `oracle`.
- Comments explain *why* or point to the spec (`# spec §7.1: q_m has no outgoing
  edges, so the match must end the input`). Do not narrate what the next line
  does. No section banners, no emojis, no ASCII art.
- Docstrings: one line for ordinary functions; a short paragraph for algorithms.
- No dead code, commented-out code, leftover `print`, placeholder `TODO`s,
  "in a real application…" remarks, or unused imports.
- Python: type hints everywhere, frozen dataclasses for model objects, `ruff
  format` style. TypeScript: `strict` mode, no `any`, Prettier defaults.
- Small, focused modules. Prefer plain functions over classes unless state is
  real.
- README is plain and practical: what it is, how to run it, how to test it.
- Commit at the end of each phase with a short imperative subject line
  (`Add derivative-based reference DFA`).

## Core model decisions

1. **Epsilon.** Internally `EPS = ""` (cannot collide with a one-character
   symbol). Serialised and displayed as `"ε"`. `ε` is not allowed as an
   alphabet symbol.
2. **Model.** Frozen dataclass: `states: tuple[str, ...]`, `alphabet:
   tuple[str, ...]`, `delta: Mapping[tuple[str, str], frozenset[str]]`,
   `start: str`, `final: frozenset[str]`, `meanings: Mapping[str, str]`,
   `dead: frozenset[str]`, `kind: Literal["enfa", "nfa", "dfa"]`. `meanings`,
   `dead` and `kind` are display metadata and never enter the hash.
3. **Alphabet.** Normalised to sorted Unicode code-point order, unique, 1–6
   symbols, each a single printable non-whitespace character. In v1 the
   characters `( ) | * + ? \ ε` are rejected as symbols with E_SCHEMA_INVALID
   (they collide with regex syntax). "Alphabet order" everywhere means this
   sorted order.
4. **Hash.** `model_hash` = `"sha256:" + hex` of canonical JSON
   (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`) of
   `{"Q": [...], "Sigma": [...], "delta": [[src, sym, [dst, ...]], ...],
   "q0": ..., "F": [...]}` with every list sorted and EPS written as `"ε"`.
   The IR specification hash uses the same canonical JSON rules.
5. **Trimming.** Unreachable states are removed before naming. States that
   cannot reach F are kept in the model and listed in `dead`; diagram and table
   hide them by default, and the "show dead state" toggle reveals them.
   Complement DFAs keep their dead state, which keeps them complete.
6. **Naming (§7.4).** BFS from the start state; at each state visit edges by
   symbol in alphabet order, then ε last; within one destination set order by
   the construction's internal integer ids (which are themselves deterministic).
   Rename to `q0, q1, …`. DFA states from subset construction are named the same
   way. Add a test that compiling the same IR twice yields the same hash, and
   that permuting the order of `and`/`or` children in the input IR does too.
7. **Complement (§4).** Only ever: ε-remove → determinize → complete with a dead
   state → swap. Add a guard that raises if `complement` receives anything not
   marked `kind="dfa"` and complete, plus a test that proves the guard fires.
8. **Budgets (§7.3).** `max_states = 200` and a 2-second budget checked with
   `time.monotonic()` inside the loops of determinize, product, complement and
   the derivative explorer (no threads, no signals; they do not work on
   Windows). Breach raises a typed exception mapped to E_STATE_LIMIT (with the
   size reached) or E_TIMEOUT.
9. **Empty language.** If no accepting state is reachable, still return the
   automaton, add the warning "This specification describes the empty language
   ∅ (no string is accepted).", and still verify it.

## Corrections and clarifications to the spec

**C1. Witness path (spec Appendix B is incomplete).** The pseudocode keeps one
predecessor per input step and therefore drops every ε edge, including the
ε-closure of the start state. That gives invalid witnesses for any Thompson
machine. Implement instead:
- a `eclose_with_pred(S)` that runs **BFS** (not DFS, so ε-chains are shortest)
  and records `pred[r] = (q, EPS)` for each newly reached state;
- for each symbol step record `pred[r] = (q, a)` for the first `q` (in naming
  order) whose `delta[(q, a)]` contains `r`, then extend through the closure;
- reconstruct backwards from the lowest-named accepting state in the final
  active set, following ε predecessors and symbol predecessors until reaching
  `q0` at step 0.
The witness is a list of `[src, label, dst]` with label `"ε"` for ε edges.
Property test: for every accepted word the witness starts at `q0`, edges are
consecutive and exist in δ, non-ε labels concatenate to the word, and it ends
in F. `eclose` (no predecessors) is still memoised per state.

**C2. Trace record (additive to §9.2).** Each step also carries
`transitions: [[q, a, r], ...]` (symbol moves taken from the previous active
set) and `epsilon_layers: [[[q, "ε", r], ...], ...]` (ε edges grouped by BFS
depth during closure). The frontend animation depends on both. Existing fields
keep their names.

**C3. pattern_count semantics.** `overlap=true` counts every start index `i`
with `w[i:i+m] == p`. `overlap=false` counts the maximum number of pairwise
disjoint occurrences, which equals a greedy leftmost scan. The automaton is the
KMP DFA of `p` paired with a counter `0..n+1` (`n+1` = "too many", saturating;
for `ge` saturate at `n`). On a full match: overlap → jump to the border state
`π(m)`; no overlap → jump to state 0. The oracle implements both semantics
directly by string scanning, never via the automaton.

**C4. When to ask about overlap.** Ask only if `p` has a non-empty proper
border (some `0 < k < m` with `p[:k] == p[-k:]`). Otherwise the answer cannot
change the language: set `overlap=false` and add the assumption "Occurrences of
p cannot overlap, so no choice is needed." This follows §6.2's rule that a
question is asked only when the answer changes the language.

**C5. Alphabet inference (§6.2).** Explicit `over {…}` → `source: "user"`.
The word "binary", or only the digits 0/1 mentioned → `{0,1}`. Only letters a/b
mentioned → `{a,b}`. Otherwise the set of symbols mentioned. If that set has a
single symbol, add its conventional partner (`0↔1`, `a↔b`). Always
`source: "inferred"`, shown as an editable chip, and recorded as an assumption.

**C6. Regex syntax (LSIR `regex`).** Juxtaposition = concatenation; `|`, `*`,
`+`, `?`, parentheses; `()` or `ε` denotes the empty string. No character
classes, no `∅`, no backreferences. Precedence: postfix > concat > union. The
production compiler (`compile/regex_parser.py`), the reference
(`reference/derivatives.py`) and the oracle must not share a parser: the
reference has its own small recursive-descent parser, and the oracle has a third
one. The oracle decides membership with a memoised matcher (for every
sub-expression and start index, the set of end indices), O(|r|·n³), building no
automaton. It does not use Python `re`: backtracking is exponential on ambiguous
repetition such as `(a|a)*b`, which V1/V3 would hit on user regexes, and spec §13
rules out a backtracking engine. IR-level `concat`/`star` in the oracle are
memoised the same way.

**C7. Reference translations (§8.1).** With `O = Σ∖{s}` written as a union:
- `starts_with p` → `p Σ*`; `ends_with p` → `Σ* p`; `contains p` → `Σ* p Σ*`;
  `avoids p` → `¬(Σ* p Σ*)`
- `symbol_parity even` → `(O* s O* s)* O*`; `odd` → `(O* s O* s)* O* s O*`
- `symbol_count eq n` → `(O* s){n} O*`; `ge n` → `(O* s){n} Σ*`;
  `le n` → `O*` followed by n copies of `(s O*)?`
- `length_mod m r` → `(Σ^m)* Σ^r`
- `literal_set` → union of the words; `and`/`or`/`not`/`concat`/`star` → `&`,
  `|`, `¬`, concatenation, `*`
- `pattern_count` → not translated; that node reaches V1 + V3 only and the
  badge says so (spec §8.2).
Smart constructors must apply: ∅ and ε identities; flatten, sort and dedupe
`|` and `&` (ACI); `¬¬r = r`; `r** = r`; `ε* = ∅* = ε`; `∅·r = r·∅ = ∅`.
Nodes are hash-consed frozen tuples. If exploration exceeds 2,000 states or
the time budget, stop and report V1 honestly.

**C8. V1 bound (§8.2).** `L` = the largest value ≤ 10 with
`Σ_{k=0..L} |Σ|^k ≤ 200 000`. Enumerate words depth-first over the word tree,
carrying the active set incrementally (never re-simulate each word from
scratch). Compare against the oracle at every node.

**C9. V3 at runtime.** 500 random words of length 0–30 vs the oracle; for
`not` nodes the double complement equals the original; the ε-free view is
equivalent to the ε-NFA. The mutation tests (flip an accepting state, redirect
an edge, drop an edge, and assert the verifier catches it with a
counterexample) live in the test suite, not at runtime.

**C10. State meanings for composites (§7).** Product state: "A: <m_p> · B:
<m_q>". Subset state: "one of: <m1> | <m2> | …". Thompson regex states:
"inside <subexpr>: <position>". Dead state: "no continuation can be accepted".
Truncate to 80 characters in the diagram; full text in the legend and on hover.

**C11. Uninterpretable text** ("strings that are good") returns
E_UNSUPPORTED_FEATURE with `detail.reason = "not_interpretable"` and three
example prompts. No new error codes are invented. The message first says what was
read and what was not ('I read the alphabet {0, 1} and "contain 101", but couldn't
find a condition in "are pretty"'), then names the closest example, which also leads
`detail.examples`. Closest means most content words in common with the whole
description, from `lexicon.EXAMPLE_CATALOG`; with nothing in common the usual first
example leads. Every catalogue entry must stay readable (a test checks it).

**C12. Benchmark scoring (§14.2).** An `ir` entry is correct when the produced
IR describes the same language as the expected IR (compile both and compare
with the V2 equivalence check, falling back to V1 for `pattern_count`), and
the listed assumptions are present. Tree identity is not required. Clarification
entries match on `question_topic`; refusal entries match on error code and on
whether an alternative was offered. The interpreter must stay general: never
special-case a benchmark prompt string. The benchmark runner prints a table of
every entry with pass/fail and writes `tests/benchmark/report.json`. Entries 1–40
are the spec's; 41–50 cover joined conditions (C16), malformed alphabets and verb
variants; 51–55 cover command words, quotes and punctuation around a description;
56–85 are free-form phrasings (C18).

**C13. Clarifier.** Exactly three must-answer topics exist in v1:
`count_exact_or_at_least`, `overlap`, `grouping` (and `alphabet` only when the
wording hints at more symbols, §6.2). At most two questions per request; if a
third would be needed, return `status: "edit_ir"` with the partial IR so the UI
shows the manual IR form. Sessions: 30-minute TTL.

**C14. LLM tier without temperature (spec §6.1, §13).** Current Claude models reject
`temperature` and the other sampling parameters with HTTP 400, so the tier sends
none. `NFA_LLM_MODEL` defaults to `claude-opus-5-5` at low effort. Reproducibility
comes from the pinned model id, the cache by normalised text, and the same
validation and normalisation as Tier 1. The IR schema goes in the prompt rather
than in structured outputs, which do not accept recursive schemas. A request for
"temperature 0" or an API-enforced schema cannot be met for these reasons; strictness
comes from validating every reply instead (C18).

**C15. Graphviz layout limit (spec §10.2).** One `dot` run gets
`render_timeout_seconds = 10`. Sparse machines lay out in about a second even near
the state cap, but dense determinized ones can take a minute; those get E_TIMEOUT
with "Use the transition table". The table, formal definition and simulator do not
need the drawing, so they keep working. Layouts are cached by DOT text. Decided
against a background render or a longer limit: either ties up a worker for a
drawing too dense to read.

**C16. Joined conditions (overrides spec §6.2 for mixed and/or).** "and", "but",
"plus", "as well as" join with AND; "or" with OR; "not", "does not" after any of
them negate the clause. AND binds tighter than OR, so "a and b or c" is read as
"(a and b) or c" without a grouping question; the confirm step shows the grouping
as nested bullets labelled AND/OR, and the user edits the IR if they meant the
other one. Decided because exercise-style sentences chain three or more conditions
and a question on each was more friction than the conventional reading. A bare
pattern that borrows the previous predicate ("ends with b or a") stays with that
clause, ahead of the AND/OR grouping. "a or b followed by c" still asks (C13).
Before the rules, `tidy` trims quotes (' " ` and curly quotes), trailing . , ; : ! ?
and brackets that wrap a whole sentence (not a regex group such as `(ab)`); then the
lead-in (`lexicon.LEAD_IN`) is stripped repeatedly, case-insensitively: please, can
you, I want/need, command words (enter, type, give me, write, make, build, create,
generate, find, show, list, construct, design, draw, input), "an NFA/DFA for/that
accepts", "the language of", "set of", and all/every/any/each. An article is taken
only with a machine noun and all/every/any/each only before strings or words, so "a
or b followed by c" and "every a is followed by b" keep their first word. The
alphabet is read as typed from `{0,1}`, `[0,1]`, `{[0,1]`, an
unclosed `{0,1`, `Σ = {0,1}`, `I = {0,1}` or "over 0 and 1".

**C17. Branches view (additive to spec §10, §12).** A visualisation over the same IR,
never a replacement for the verified automaton. `compile/branches.py` splits the
normalised language at a top-level `and`/`or`; each child is compiled alone with
`compile()` over the document's alphabet, so a lane is exactly what that condition
builds on its own. A `not` child is its complemented DFA, labelled "NOT " plus its
child's wording. Labels use the confirm screen's wording (`Reading.tsx`); keep the
two in step. A single condition has no lanes (empty list, `combiner: null`). The
branch trace runs `simulate()` on every lane and combines the verdicts with all/any;
it is paged with `trace_page_size` like `/simulate`. The lanes are not put through
the ladder; `tests/unit/test_branches.py` checks on 500 random words for each of 10
descriptions that the combined verdict equals the verified automaton's. On the
client, the Branches view shares the simulator store and its one animation clock,
so the word box, controls, speed and reduced-motion handling are the main view's;
the lanes read their active sets for the step the clock has settled on. Lane SVG ids
get a `lane<i>-` prefix so several drawings can share the page.

**C18. Any phrasing, never a silently wrong automaton.** Rule tier: the paraphrase
suite (`tests/unit/test_paraphrases.py`) holds at least 8 phrasings for each of the 15
node types and must stay at 100%; add a phrasing there with every new rule, worded
differently from any benchmark prompt (C12). Direct inputs are read as such: a regex,
a braced or listed set of words ("{0, 10, 110}", "0, 10 and 110", "strings like ab,
abab"), "strings of a's and b's", and "Σ = {a,b}: …". Spelling: a description the rules
cannot read as typed is read once more with misspelled words of five or more letters
(three or more distinct, not made of alphabet symbols) replaced by the closest word in
`lexicon.VOCABULARY`; the reading carries a `spelling_corrected` assumption naming each
change and loses `SPELLING_PENALTY` confidence per word. A readable description is never
respelled. LLM tier (on only when `NFA_LLM_ENABLED` is true and `ANTHROPIC_API_KEY` is
set): asked only when the rules cannot read the text or read it below the confidence
threshold; its reply is validated, compiled and put through the ladder before it is
returned, and any failure becomes the C11 refusal, never an error the user must decode.
`{"error": "not_regular", "kind": …}` maps to `nonregular.refusal(kind)`, the same
E_UNSUPPORTED_NONREGULAR with an alternative. Its readings carry `llm_interpreted`, and
the confirm step shows "Read with AI help" above the usual bullets. Model calls have
their own per-address limit (`deps.LLM_RATE_*`, cached readings free), a 20 s timeout
with one retry, and the 500-character cap. Tests use `tests/support/mock_llm.py`; no test
needs the network. The benchmark's rule+LLM score with the real model comes from
`run_benchmark --llm` with a key; CI measures rule-only and a declining stand-in.

**C19. No ε-moves in what is built (overrides the spec's ε-NFA output).** The
constructions still join their parts with ε edges (Thompson, union, concatenation,
star), but `compile()` ends with ε-removal, so every automaton that is verified,
shown, simulated, exported or drawn as a Branches lane has no ε edge, for one
condition or many. ε-removal is δ′(q, a) = δ(ECLOSE({q}), a) with q accepting iff
ECLOSE({q}) ∩ F ≠ ∅; targets are not closed, so states entered only by ε become
unreachable and are trimmed before naming. The explanation logs it as an
`epsilon_removal` step. Decided by the developer: ε-NFAs are another team's topic.
The model, closure and ε-free view code still handle ε edges (hand-built machines,
the mutation tests' stray-ε mutant); the empty word ε as an input is unaffected.

## Diagram contract (§10.2)

The server renders DOT → SVG with Graphviz and gives every element a stable id
so the client can animate the real Graphviz geometry:

- graph: `rankdir=LR`, `bgcolor="transparent"`, `nodesep=0.5`, `ranksep=0.7`
- start arrow: node `__start` with `shape=none, label="", width=0, height=0`,
  edge `__start -> q0` with `id="start-edge"`
- states: `shape=circle` (accepting: `doublecircle`), `id="s-<name>"`,
  `class="state"` (+ `accepting`, `dead`), `tooltip` = meaning
- edges: one per (src, dst) for symbol labels merged as `"a, b"`, `id="e-<src>-<dst>"`;
  a separate dashed edge for ε, `id="ee-<src>-<dst>"`, label `ε`
- labels escaped for DOT; fonts are overridden by CSS on the client
- `GET /diagram?format=json` returns nodes, edges and the id map used above

Graphviz emits these `id` values on the SVG `<g>` groups; the client reads the
edge `<path>` inside each group and moves tokens along it with
`getTotalLength()` / `getPointAtLength()`.

## Frontend and animation brief

Stack: Next.js App Router, TypeScript strict, Tailwind, `motion` (import from
`motion/react`), `zustand` for client state, `openapi-fetch` with generated
types, `lucide-react` icons. Fonts via `next/font/google`: Inter (UI),
JetBrains Mono (tape, tables, IR), Noto Sans Math (fallback for ε δ Σ ∅ and
subscripts). Glyph check (§12.2): a test renders `ε δ Σ ∅ q₀ →*` and asserts
the font family resolves.

Look: calm, academic, high contrast, light and dark themes. Neutral slate
surfaces, one accent (teal) for active states, amber for the witness path, red
only for errors and dying branches. No gradients-for-decoration, no glassmorphism.

Screens follow §12.1: Describe → Confirm → Build → Explore → Simulate, in one
page with a left column (description, assumptions, clarifications, verification
badge) and a right column with tabs Diagram · Table · Formal definition ·
Explanation, and the simulator docked under the diagram.

Simulation animation, per step:
1. **Read** — the tape head slides to the next cell; the consumed cell dims.
2. **Move** — for every `[q, a, r]` in `transitions`, a small token travels
   along `e-q-r` (self-loops follow their loop path). Tokens start together,
   duration `450ms / speed`, ease-in-out.
3. **ε-closure** — for each layer in `epsilon_layers`, tokens travel the dashed
   `ee-*` edges, layer after layer (`250ms / speed` each), with a soft ripple on
   each state reached.
4. **Settle** — new active states fill with the accent and a bold outline (colour
   never carries meaning alone); states that dropped out fade back over 200ms
   with a brief red outline flash. Empty set → a "No active states — the input
   is rejected from here on" notice over the diagram.
5. **Verdict** on the last step — accepted: the accepting states in the active
   set get a ring pulse and the witness path draws itself in amber with
   `stroke-dashoffset`; rejected: a short horizontal shake of the verdict chip.
   The verdict chip always shows an icon and the word.

Controls: play/pause, step back/forward, jump to start/end, scrubber, speed
0.25×–4×, keyboard (Space, ←, →, Home, End), history list of tested words.
Stepping backward and scrubbing jump without token animation (crossfade only).
Drive tokens with `requestAnimationFrame`, cancel in-flight animations on any
control change, and never use `setInterval` for playback. With
`prefers-reduced-motion`, skip tokens and ripples and change states instantly.
An `aria-live` region announces each step ("Step 3: read a, active {q0, q1}").
Traces longer than 200 steps are paginated (§9.3) and the animation skips to
instant mode above 500 symbols.
