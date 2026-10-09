# NFA Studio

Describe a regular language in plain English and get an ε-NFA with its transition table,
state diagram and a step-by-step simulator. Every automaton is checked against an
independently built reference before it is shown. The specification is
`docs/NFA_Studio_Spec_v1.pdf`; project rules are in `CLAUDE.md`.

## Requirements

- Python 3.11 or newer
- Node.js 24
- Graphviz, with `dot` on PATH (`dot -V` must work)

## Setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cd ..\frontend
npm install
npx playwright install chromium     # only for the end-to-end tests
```

The optional LLM tier reads descriptions the rules cannot. To switch it on, copy
`backend/.env.example` to `backend/.env`, set `NFA_LLM_ENABLED=1` and
`ANTHROPIC_API_KEY`. The key stays on the backend; never commit `.env`.

## Run

Two terminals:

```powershell
cd backend
uvicorn nfa_studio.api.app:app --reload --port 8000    # API docs: http://127.0.0.1:8000/docs
```

```powershell
cd frontend
npm run dev                         # http://localhost:3000, proxies /v1/* to the backend
```

## Test

Backend, from `backend/`:

```powershell
pytest -q
ruff check .
ruff format --check .
mypy nfa_studio
python -m tests.benchmark.run_benchmark      # benchmark_v1, rule-only; writes report.json
python -m tests.benchmark.run_benchmark --llm  # with the LLM tier; writes report-llm.json
python -m tests.benchmark.acceptance         # spec §14.3 measurements; writes acceptance.json
```

Frontend, from `frontend/`:

```powershell
npm run lint
npm run typecheck
npm run test
npm run build
npm run e2e                         # Playwright; starts both servers if they are not running
```

`npm run e2e` serves the production build, so run `npm run build` first. With the
backend running, `npm run gen:api` regenerates `src/lib/api/schema.d.ts` from the
backend's OpenAPI document; commit the result.

CI (`.github/workflows/ci.yml`) runs all of the above except the LLM benchmark and
attaches the test, benchmark and acceptance reports to each run.

## Architecture

```
text ─► interpret ─► IR ─► confirm ─► compile ─► verify ─► automaton ─► table · diagram · trace
        rules, then        (user)     ε-NFA      V0–V3     by hash id
        optional LLM
```

The backend (`backend/nfa_studio`) is a FastAPI app over a library that never imports
the web layer:

- `interpret/` turns text into the intermediate representation (IR): a rule parser, a
  non-regular detector that offers a regular alternative, an ambiguity check that asks
  at most two questions, and the optional LLM tier, whose output is validated like any
  other input.
- `ir/` holds the IR schema, its normalisation and limits, and the oracle: a direct
  membership test for a word against the IR, with no automaton involved.
- `compile/` builds the ε-NFA: one construction per atom, Thompson's construction for
  regexes, products and complements for `and`/`or`/`not`, then deterministic naming.
- `core/` is the automaton model and its algorithms: ε-closure, simulation with a
  witness path, subset construction, product and minimisation.
- `reference/` builds an independent DFA from the IR with Brzozowski derivatives.
- `verify/` is the ladder: V0 well-formed, V1 every word up to a length bound (at
  most 10) against the oracle, V2 exact equivalence with the reference, V3 random
  words. An automaton that fails is never shown.
- `render/` produces the table (JSON, CSV, Markdown, LaTeX), the DOT source, the
  Graphviz SVG and PNG, and the JSON graph. Every view carries the hash of the model it
  read, and the API refuses one that does not match the automaton id.
- `api/` exposes `/v1`, with per-address rate limits, input limits and one error shape:
  a code, a message with the reason and the next action, and details.

The frontend (`frontend/`) is a single Next.js page. Zustand stores hold the
Describe → Confirm → Build steps, the Explore tabs and the simulator; the API client is
typed from the backend's OpenAPI document. The simulator animates the real Graphviz
geometry: one `requestAnimationFrame` controller runs a cancellable timeline per trace
step (read, move, ε layers, settle), and tokens follow the SVG edge paths by id.
