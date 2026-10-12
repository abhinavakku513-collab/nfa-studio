# NFA Studio

Describe a regular language in plain English and get an NFA, free of ε-moves, with its
transition table,
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

### Reading with AI help (optional)

The rules read most descriptions on their own. When they cannot, an optional tier asks
a Claude model for a reading. It is off by default and comes on only when both are set:

1. Copy `backend/.env.example` to `backend/.env` (or set the variables in your host's
   settings, as secrets).
2. Set `NFA_LLM_ENABLED=true` and `ANTHROPIC_API_KEY=<your key>`, then restart the
   backend. Optional: `NFA_LLM_MODEL` (default `claude-opus-5-5`) and
   `NFA_LLM_TIMEOUT_SECONDS` (default 20).

What it does and does not do:

- It is asked only for descriptions the rules cannot read; anything the rules read never
  leaves the server.
- Its reply must be JSON in the specification's schema. It is validated, built and put
  through the full verification ladder before anyone sees it; a reply that fails any of
  this ends in the same clear refusal the rules give.
- It refuses non-regular languages (aⁿbⁿ, palindromes, equal counts, prime lengths,
  balanced brackets) with the same `E_UNSUPPORTED_NONREGULAR` error and a suggested
  alternative.
- The confirm step labels its reading **Read with AI help**, with the same bullets, so
  you check it before building.
- Each address gets a burst of 5 model calls, then one every 12 seconds; a reading
  already made is served from the cache. Descriptions are capped at 500 characters.
- The key stays on the backend and is never logged or returned; the description is sent
  only to the Anthropic API. Never commit `.env`.

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

## Deploying

The backend runs on [Render](https://render.com) from `backend/Dockerfile`, and the
frontend on [Vercel](https://vercel.com). Both deploy from your GitHub repository, so
push it to GitHub first. Do it in this order, because each side needs the other's
address.

### 1. Backend on Render

In the Render dashboard choose **New → Web Service** and connect the repository.

| Setting | Value |
|---|---|
| Language | Docker |
| Branch | `main` |
| Root Directory | `backend` |
| Dockerfile Path | `./Dockerfile` (relative to the root directory) |
| Instance Type | Free is enough for a few friends |
| Health Check Path (under Advanced) | `/v1/health` |

Under **Environment Variables** add:

| Key | Value |
|---|---|
| `NFA_CLIENT_IP_HEADER` | `CF-Connecting-IP` |
| `NFA_CORS_ORIGINS` | `http://localhost:3000` for now; you replace it in step 3 |

Do not set `PORT`; Render sets it and the container listens on it. Create the service
and wait for the deploy to finish. Copy its address, for example
`https://nfa-studio-api.onrender.com`, and check that
`https://nfa-studio-api.onrender.com/v1/health` shows `{"status":"ok"}`.

A free service sleeps after 15 minutes without traffic and takes about a minute to
wake up, so the first visit after a quiet spell is slow.

### 2. Frontend on Vercel

In the Vercel dashboard choose **Add New → Project** and import the same repository.

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Framework Preset | Next.js (detected) |
| Build Command | leave the default (`npm run build`) |
| Install Command | leave the default (`npm install`) |

Under **Environment Variables** add, for Production:

| Key | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | the Render address from step 1, without a trailing slash |

Deploy, then copy the site's address, for example `https://nfa-studio.vercel.app`.
`NEXT_PUBLIC_API_URL` is built into the page, so if you change it later, redeploy.

### 3. Connect them

Back on Render, open the service's **Environment** page and set `NFA_CORS_ORIGINS` to
the Vercel address, for example `https://nfa-studio.vercel.app`. To keep local
development working too, list both, separated by a comma:
`https://nfa-studio.vercel.app,http://localhost:3000`. Save; Render redeploys. Open the
Vercel address and build an automaton: that is the link to send your friends.

Only the addresses listed in `NFA_CORS_ORIGINS` can use the API from a browser, so
Vercel preview deployments, which get their own addresses, will not work unless you
add them.

### What the settings do

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `NFA_CORS_ORIGINS` | backend | `http://localhost:3000` | Comma-separated sites allowed to call the API from a browser. |
| `NFA_CLIENT_IP_HEADER` | backend | unset (use the connection's address) | Header that names the visitor for the rate limit. On Render, Cloudflare sets `CF-Connecting-IP` and refuses requests that try to supply it, so it cannot be forged. `X-Forwarded-For` is never used: Render keeps whatever a client puts in it. |
| `NFA_LLM_ENABLED`, `ANTHROPIC_API_KEY` | backend | off | The optional AI tier stays off unless `NFA_LLM_ENABLED` is `true` (or `1`) and the key is set as a secret. See "Reading with AI help". |
| `NEXT_PUBLIC_API_URL` | frontend | unset (same site) | Address of the API. The browser calls it directly, so the rate limit counts each visitor separately. |
| `BACKEND_URL` | frontend | `http://127.0.0.1:8000` | Where the frontend forwards `/v1` when `NEXT_PUBLIC_API_URL` is unset, as in local development. |

To try the backend image locally:

```powershell
cd backend
docker build -t nfa-studio-api .
docker run --rm -p 8000:10000 -e PORT=10000 nfa-studio-api
# then open http://127.0.0.1:8000/v1/health
```

## Architecture

```
text ─► interpret ─► IR ─► confirm ─► compile ─► verify ─► automaton ─► table · diagram · trace
        rules, then        (user)     NFA, no ε  V0–V3     by hash id
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
- `compile/` builds the NFA: one construction per atom, Thompson's construction for
  regexes, products and complements for `and`/`or`/`not`, then ε-removal, so the
  machine shown has no ε-moves, and deterministic naming.
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

### Branches view

When a description joins two or more conditions at the top level ("contains 101 and
ends with 00"), the Diagram tab offers **Whole automaton / Branches**. Branches shows
one lane per condition, each its own small machine built by the same constructions
over the same alphabet; a `not` condition is shown as its complemented DFA, labelled
"NOT …". One tape feeds every lane, the simulator's controls and speed move them
together, each lane shows its active states and its own verdict, and the combiner at
the end ("ALL must accept" for and, "ANY accepts" for or) lights up with the result.
No lane, and nothing between the lanes, has an ε-move.

It is a picture of the parts, not a second automaton: the verified automaton and its
ladder are unchanged, and the lanes are not verified on their own. The API is
`GET /v1/automata/{id}/branches` (labels, drawings and graphs; an empty list for a
single condition) and `POST /v1/automata/{id}/branches/simulate` (every lane's active
set and verdict per step, paged like `/simulate`, and the combined verdict). A test
checks that the combined verdict equals the verified automaton's on 500 random words
for each of 10 descriptions.

The frontend (`frontend/`) is a single Next.js page. Zustand stores hold the
Describe → Confirm → Build steps, the Explore tabs and the simulator; the API client is
typed from the backend's OpenAPI document. The simulator animates the real Graphviz
geometry: one `requestAnimationFrame` controller runs a cancellable timeline per trace
step (read, move, ε layers, settle), and tokens follow the SVG edge paths by id.
