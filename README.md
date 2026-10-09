# NFA Studio

Describe a regular language in plain English and get an ε-NFA with its transition table,
state diagram and a step-by-step simulator. Every automaton is checked against an
independently built reference before it is shown. The specification is
`docs/NFA_Studio_Spec_v1.pdf`; project rules are in `CLAUDE.md`.

## Requirements

- Python 3.11 or newer
- Node.js 24
- Graphviz, with `dot` on PATH (`dot -V` must work)

## Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn nfa_studio.api.app:app --reload --port 8000
```

API docs are at http://127.0.0.1:8000/docs.

Checks:

```powershell
pytest -q
ruff check .
ruff format --check .
mypy nfa_studio
```

## Frontend

```powershell
cd frontend
npm install
npm run dev                         # http://localhost:3000, proxies /v1/* to the backend
```

Checks: `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`.

With the backend running, `npm run gen:api` regenerates `src/lib/api/schema.d.ts` from
the backend's OpenAPI document. Commit the result.
