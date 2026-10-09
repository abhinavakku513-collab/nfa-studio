# Prompts for Claude Code

Paste these into Claude Code in VS Code **one at a time, in order**. Wait for each
phase to finish and report green checks before pasting the next. The phases follow
spec §15. `CLAUDE.md` in the project root is read automatically, so the prompts stay
short and all the detailed rules live there.

Tip: start a fresh Claude Code conversation for each phase (the project rules carry
over through `CLAUDE.md`). If usage runs out mid-phase, paste the "Resume" prompt at
the bottom when you come back.

---

## Phase 0 — Foundations

```
Read CLAUDE.md fully, then read spec §1–§3 and §15 in docs/NFA_Studio_Spec_v1.pdf.

Set up the repository for Phase 0:
1. backend/: pyproject.toml (project metadata, ruff with line length 100, mypy strict
   for nfa_studio, pytest testpaths and hypothesis profile "ci" with 200 examples),
   the full empty package layout from spec §3.2 plus nfa_studio/api/app.py, and
   ir/limits.py holding every limit from spec §5.3, §7.3 and §9.3 in one place.
   requirements.txt already exists; create the venv and install it.
2. A minimal FastAPI app with GET /v1/health and GET /v1/capabilities (supported
   node types, limits from limits.py, ir_version "1.0", api version "v1").
   CORS allowed only for http://localhost:3000.
3. frontend/: create the Next.js app non-interactively (TypeScript, ESLint, Tailwind,
   App Router, src/ directory, import alias @/*, npm). Then install:
   npm install motion zustand openapi-fetch clsx lucide-react
   npm install -D openapi-typescript vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @playwright/test prettier
   Add scripts: typecheck (tsc --noEmit), test (vitest run), e2e (playwright test),
   gen:api. Add the /v1 rewrite to the backend in next.config. Set up the three fonts
   from CLAUDE.md with next/font/google.
4. .github/workflows/ci.yml running backend checks and frontend lint, typecheck,
   test, build.
5. A short README.md and a .gitignore (venv, node_modules, .next, __pycache__,
   .hypothesis, .env).
6. git init and commit.

Do not touch backend/tests/benchmark/benchmark_v1.json.
Run every check command from CLAUDE.md and show me the results. Also run `dot -V`.
```

## Phase 1 — Core model and oracle

```
Phase 1. Read spec §4, §5, §9 and Appendix B, and CLAUDE.md "Core model decisions"
plus corrections C1, C2, C3, C6.

Implement:
- core/model.py: the frozen Automaton model, model_hash, canonical JSON, trimming,
  dead-state detection.
- core/closure.py: memoised eclose and BFS eclose_with_pred.
- core/simulate.py: simulate(auto, word, witness) returning the full trace with the
  extra fields from C2 and the corrected witness from C1; E_SYMBOL_NOT_IN_ALPHABET
  with position; E_INPUT_TOO_LONG.
- core/determinize.py (with budget), core/product.py (ε-free inputs only, raise
  otherwise), ε-removal, completion with a dead state, complement guarded as in
  CLAUDE.md item 7, core/minimize.py (Hopcroft; used only for an optional view later).
- ir/schema.py (Pydantic v2 discriminated union over every node in §5.1, document
  shape from §5.2), ir/normalize.py (§5.3 rules: flatten and/or, remove double
  negation, sort commutative children, alphabet rules from CLAUDE.md item 3, every
  used symbol must be in the alphabet), spec hash.
- ir/oracle.py: matches(ir, word) evaluated directly on strings, no automata.

Tests (unit + hypothesis): ε-closure with ε-cycles; step on the empty set; empty
input; hand-built ε-NFAs vs oracle; the seven traces in spec §7.5 as fixtures;
witness property test from C1 on random Thompson-style machines; complement guard
fires on an NFA; determinize respects the state cap and time budget; normalisation
is idempotent and order-insensitive.

Run all backend checks and show the output. Commit.
```

## Phase 2 — Construction library

```
Phase 2. Read spec §7 fully and CLAUDE.md items 5–8 and C3, C6, C10.

Implement compile/atoms.py (every atom in §7.1 with its state meanings),
compile/regex_parser.py (C6 syntax, own parser, no backtracking engine),
compile/thompson.py, compile/combine.py (or, concat, star with ε edges; and via
ε-removal + product; not via the complement pipeline; avoids via a direct KMP DFA;
pattern_count per C3), compile/naming.py (§7.4 + CLAUDE.md item 6), and a top-level
compile(ir) -> Automaton that records a construction log used later for the
explanation text.

Tests: for every node type, unit tests on hand-computed strings and a hypothesis
test that simulate(compile(ir)) == oracle(ir) for random words up to length 10 over
random small IR trees (depth ≤ 3, alphabet size 2–3). Include the two worked
examples in spec §7.5 and §7.6 as exact-structure tests (same states, δ and F after
naming). Determinism tests: same IR twice → same hash; permuted and/or children →
same hash. State-limit test that triggers E_STATE_LIMIT.

Run all backend checks, show output, commit.
```

## Phase 3 — Verification ladder

```
Phase 3. Read spec §8 and CLAUDE.md C7, C8, C9.

Implement reference/derivatives.py (own regex AST and parser, smart constructors,
nullable, derivative, hash-consing), reference/to_dfa.py (BFS exploration with the
2,000-state and time caps), reference/equivalence.py, verify/counterexample.py
(shortest counterexample by product BFS on complete DFAs, as in §8.3),
verify/ladder.py (V0–V3 with the evidence strings and badge colours in §8.2; results
cached by automaton id).

Mutation tests: take compiled automata for at least 10 different IRs, apply each
mutation (flip an accepting state, redirect an edge, delete an edge, add a stray ε
edge), and assert the ladder reports failure with a counterexample that really
distinguishes the two languages (check it with the oracle). This is the Phase 3 exit
criterion from §15.

Run all backend checks, show output, commit.
```

## Phase 4 — Rendering

```
Phase 4. Read spec §10 and the "Diagram contract" section of CLAUDE.md.

Implement render/table.py (json, csv, md, tex; ε column only when ε edges exist;
→, *, →* markers; sorted destination sets or ∅; ε-free toggle; dead states hidden
unless requested), render/dot.py (exact ids, classes and attributes from the diagram
contract), render/svg.py (Graphviz dot → SVG, PNG, DOT), render/json_graph.py.
Each renderer returns the model hash it read; implement the §10.3 consistency check.

Tests: golden DOT and SVG files for the §7.5 and §7.6 machines and one Thompson
regex machine (normalise Graphviz version comments before comparing); every SVG
contains s-q0, start-edge and the expected e-*/ee-* ids; table/diagram hash equals
the automaton id; LaTeX export escapes ε and ∅ correctly.

Run all backend checks, show output, commit.
```

## Phase 5 — Interpretation, clarification, API

```
Phase 5. Read spec §6 and §11, and CLAUDE.md C4, C5, C11, C12, C13.

Implement interpret/lexicon.py, interpret/rule_parser.py (tokenise, normalise
unicode such as aⁿbⁿ and curly quotes, match the lexicon, build IR with a confidence
score), interpret/ambiguity.py (the §6.2 table, with C4 for overlap),
interpret/nonregular.py (the §6.4 table with alternatives), session/store.py
(in-memory TTL), session/clarify.py (merge answers into the partial IR, at most two
questions, then status edit_ir).

Then the full API from §11 in api/routes.py, api/errors.py (exact codes and HTTP
statuses in §11.2, every message names the reason and the next action, §12.1),
api/deps.py, and a simple per-IP token-bucket rate limiter written in the project
(no extra package). Simulation and verification accept only automaton ids.

Write tests/benchmark/run_benchmark.py following C12 and a pytest wrapper that
fails below 90% rule-only. Integration tests for interpret → answer → automata →
table → diagram → simulate → batch → verify, plus the negative cases in §14.1.

Run all backend checks and the benchmark, show the benchmark table, commit.
```

## Phase 6 — LLM tier (optional)

Skip this phase if you do not have an Anthropic API key. Everything else works
without it.

```
Phase 6. Read spec §6.1 and §13.

Implement interpret/llm_adapter.py behind the env var NFA_LLM_ENABLED=1, using the
anthropic Python SDK (uncomment it in requirements.txt and install). Read
ANTHROPIC_API_KEY and NFA_LLM_MODEL from the environment via python-dotenv and a
backend/.env file (add .env.example; never log or return the key). Put the JSON
schema of the IR in the prompt, request JSON only, use temperature 0, parse the reply
as data and send it through exactly the same validation and normalisation as Tier 1.
Called only when Tier 1 confidence is below the threshold. Cache by normalised text.

Tests with a fake client: prompt-injection strings ("ignore the schema and…"),
malformed JSON, schema-violating JSON, oversized IR — all must end in a proper error
code, never an unvalidated IR. Re-run the benchmark with and without the tier.

Run all backend checks, show output, commit.
```

## Phase 7a — Frontend shell, Describe and Confirm

```
Phase 7a. Read spec §12 and the "Frontend and animation brief" in CLAUDE.md.
Start the backend, run npm run gen:api, and use only the generated types.

Build the single-page layout: header with the app name and theme toggle; left
column with the Describe step (text box, example chips taken from /v1/capabilities
or a local list of general examples, editable alphabet chip) and the Confirm step
(plain-English reading of the IR as editable chips, assumptions panel with toggles,
clarification questions as button groups, manual IR form for status edit_ir); a
build progress strip (compiled → verified) and the verification badge (grey, amber,
green with icon and text, level and L). Every API error shows its reason and the
suggested next action.

Make it look deliberate: consistent 4/8px spacing scale, clear type hierarchy,
focus rings, light and dark themes. Keyboard operable end to end.

Run lint, typecheck, test, build; show output; commit.
```

## Phase 7b — Diagram, Table, Formal definition, Explanation

```
Phase 7b. Build the Explore tabs.

Diagram: fetch the SVG, inline it safely (it comes from our own server, but still
strip <script> and on* attributes), override fonts with CSS, add pan and zoom
(wheel + buttons + reset), a legend panel with state meanings, the "show dead state"
and "ε-free version" toggles, and SVG/PNG/DOT export (PNG drawn client-side from the
SVG on a canvas so the bundled fonts are used). Hovering a state shows its meaning.

Table: render from /table?format=json with →, *, →* markers and an ε column only when
present; exports for CSV, Markdown, LaTeX, JSON.

Formal definition: Q, Σ, δ (as a compact list), q₀, F typeset with the math font.
Explanation: the construction log as readable sentences, including when the machine
is a DFA produced by subset construction or complement (§7.3), and the assumptions.

Component tests with vitest for the table markers and the glyph check from CLAUDE.md.
Run lint, typecheck, test, build; show output; commit.
```

## Phase 7c — Simulator and animations

```
Phase 7c. Implement the simulator exactly as described in "Simulation animation"
in CLAUDE.md, using the transitions and epsilon_layers fields of the trace.

Build: input box with live validation against Σ (show the bad position), the tape,
the control bar, the scrubber, speed control, keyboard shortcuts, the history list
with verdicts and re-run, batch test (paste up to 100 words, results table), witness
toggle, paginated traces over 200 steps, an aria-live region, and reduced-motion mode.

Engineering requirements: one animation controller module that owns a
requestAnimationFrame loop and a cancellable timeline per step; a token component
that follows an SVG path element by id; ripple and dropout effects as small
components; no setInterval; no layout thrash (measure path lengths once per diagram).
Test the controller with fake timers: cancellation on step change, correct phase
order (read → move → ε layers → settle), instant mode under reduced motion.

Then write a Playwright test that runs five prompts end to end (describe → confirm →
build → simulate an accepted and a rejected word) against both servers: "binary
strings ending in 01", "strings over {a,b} not containing aa", "(ab)* over {a,b}",
"strings over {a,b} with an even number of a's that end with b", and "strings over
{a,b} that contain aba twice" (answer the overlap question).

Run lint, typecheck, test, build and e2e; show output; commit.
```

## Phase 8 — Hardening

```
Phase 8. Go through spec §12.2, §13 and §14.3 as a checklist.

- Audit every error message for reason + next action.
- Accessibility pass: keyboard path through all five steps, focus order, labels,
  text alternatives for diagram nodes, contrast in both themes.
- Confirm limits are enforced at the API boundary (oversized text, 10 000-symbol
  words, 100-word batches, rate limits) with tests.
- Measure median construct + verify time over the benchmark (target < 1 s without
  the LLM) and print it.
- Run the full benchmark and record the report.
- Update README with setup, run, test and a short architecture section.

Produce a final table of every acceptance criterion in §14.3 with the measured
value and pass/fail, based only on commands you actually ran in this session.
Commit.
```

---

## Useful extra prompts

**When something fails**

```
This failed: <paste the error or describe what you saw>. Find the root cause, fix
it, add a regression test that would have caught it, and re-run every check from
CLAUDE.md. Do not weaken existing tests.
```

**Resume after a break**

```
Read CLAUDE.md, run git log --oneline and all check commands, tell me which phase we
are in and what is left in it, then continue.
```

**Code review before submission**

```
Review the whole repository against CLAUDE.md "Code style": remove narrating
comments, dead code, unused imports, leftover prints, inconsistent naming, and
anything that reads like filler. Keep behaviour identical and re-run every check.
```
