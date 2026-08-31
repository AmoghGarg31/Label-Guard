# LabelGuard

Evidence-first packaged-label screening with Gemini Vision extraction and a deterministic compliance rule engine.

LabelGuard is a full-stack prototype for reading visible declarations from packaged-commodity labels, validating the extracted evidence, and producing an auditable screening result. Gemini is used only as the image reader. It cannot assign compliance outcomes: every accepted field passes deterministic validation, and the backend rule engine alone produces `PASS`, `FAIL`, `UNCERTAIN`, and the final `overall_status`.

> LabelGuard is decision-support software, not legal certification. The included rules and citations must be reviewed by a qualified Legal Metrology professional before regulatory, enforcement, or production use.

## Contents

- [Key features](#key-features)
- [Trust boundary](#trust-boundary)
- [Architecture](#architecture)
- [Technology](#technology)
- [Repository structure](#repository-structure)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Using LabelGuard](#using-labelguard)
- [API](#api)
- [Testing and verification](#testing-and-verification)
- [Deployment](#deployment)
- [Data and security](#data-and-security)
- [Current limitations](#current-limitations)
- [Publishing to GitHub](#publishing-to-github)

## Key features

- Single Gemini visual extraction path with no local OCR fallback.
- Fast, quality, and ordered fallback model routing.
- Sliding-window Gemini request limiting and concurrency control.
- Deterministic validation for MRP, net quantity, manufacture date, consumer care, business roles, common name, and country of origin.
- Protection against common false positives, including unit price as MRP, nutrition `per 100 g` as net quantity, and expiry/use-by dates as manufacture dates.
- Original-image evidence boxes and field-level provenance.
- Versioned deterministic rules and auditable findings.
- Human correction, independent review, and chronological audit history.
- Searchable history, review queue, analytics, CSV/JSON exports, and PDF reports.
- Responsive Next.js interface with upload and device-camera capture.

## Trust boundary

The following rules are architectural guarantees:

1. Gemini reads visible image content and returns structured candidates only.
2. Gemini cannot return or control a finding status or overall verdict.
3. Candidates without acceptable semantics or evidence geometry fail closed.
4. Conflicting values are not guessed; they require manual review.
5. Missing evidence becomes `UNCERTAIN`, not an automatic failure.
6. Only [`backend/rules.py`](backend/rules.py) assigns `PASS`, `FAIL`, `UNCERTAIN`, and `overall_status`.
7. Human corrections rerun the same deterministic rules while preserving the original automated result.

## Architecture

```text
Package image
    │
    ▼
Deterministic file validation and image-quality analysis
    │
    ▼
Model router ── standard image → fast model
    │           difficult image → quality model
    │           routeable failure → ordered fallback models
    ▼
Single Gemini Vision reader
    │
    ▼
Deterministic candidate validation
    ├─ declaration anchors and role separation
    ├─ datatype and semantic validation
    ├─ MRP versus unit-price rejection
    ├─ net quantity versus nutrition rejection
    ├─ date-purpose separation
    ├─ conflict handling
    └─ evidence-box validation
    │
    ▼
Versioned deterministic rule engine
    │
    ├─ PASS / FAIL / UNCERTAIN
    └─ overall_status
    │
    ▼
SQLite record, evidence view, review workflow, exports and PDF
```

The normal inspection uses one visual extraction request. A transient provider error can retry the same reader and route to another configured model; those are availability attempts, not separate extraction layers. Optional post-verdict AI explanation is disabled by default.

## Technology

| Layer | Technology |
|---|---|
| Frontend | Next.js 15.5, React 19, TypeScript 5.9, Tailwind CSS 3 |
| Backend | FastAPI, Pydantic 2, Uvicorn |
| Image handling | Pillow, OpenCV |
| Visual extraction | Google Gen AI SDK / Gemini Vision |
| Rule engine | Versioned deterministic Python engine with JSON rule definitions |
| Persistence | SQLite and local media storage |
| Reports | ReportLab PDF generation |
| Testing | Pytest, TypeScript, ESLint, Next.js production build |

## Repository structure

```text
LabelGuard/
├── backend/
│   ├── app.py                  # FastAPI routes and inspection orchestration
│   ├── gemini_vision.py        # Gemini schema, routing, retries and limiter
│   ├── evidence_reconciler.py  # Deterministic candidate trust boundary
│   ├── extractor.py            # Field-specific deterministic extraction logic
│   ├── rules.py                # Sole automated verdict authority
│   ├── database.py             # SQLite persistence and migrations
│   ├── report.py               # PDF report generation
│   ├── rules/                  # Versioned declaration rules
│   ├── tests/                  # Backend and architecture regressions
│   ├── data/                   # Local runtime data; ignored by Git
│   ├── .env.example            # Safe backend configuration template
│   └── Dockerfile
├── frontend/
│   ├── app/                    # Next.js routes
│   ├── components/             # Reusable UI components
│   └── lib/                    # API client, contracts and helpers
├── samples/                    # Synthetic demonstration fixtures
├── scripts/dev.mjs             # Cross-platform root development launcher
├── docs/                       # Deployment, security and verification reports
├── .github/workflows/ci.yml    # Backend/frontend/Docker CI gates
├── render.yaml                 # Single-instance Render backend blueprint
└── package.json                # Root development and build commands
```

## Quick start

### Prerequisites

- Node.js 20.9 or newer
- npm
- Python 3.12
- A Gemini API key with access to at least one configured model
- Git, if you plan to publish the project

### Windows PowerShell

```powershell
cd C:\path\to\LabelGuard

py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

Copy-Item backend\.env.example backend\.env
# Open backend\.env and set GEMINI_API_KEY. Keep GEMINI_ENABLED=true.

npm --prefix frontend ci
npm run dev
```

### macOS or Linux

```bash
cd /path/to/LabelGuard

python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt

cp backend/.env.example backend/.env
# Open backend/.env and set GEMINI_API_KEY. Keep GEMINI_ENABLED=true.

npm --prefix frontend ci
npm run dev
```

Open:

- Application: `http://localhost:3000`
- API health: `http://localhost:8000/system/status`
- Interactive API documentation: `http://localhost:8000/docs`

The root launcher starts both applications. Next.js hot reload remains enabled. For optional backend hot reload, set `LABELGUARD_BACKEND_RELOAD=true` before starting the command.

## Configuration

Backend secrets belong only in `backend/.env` or the hosting provider's secret manager. Never expose a Gemini key through a `NEXT_PUBLIC_*` variable.

| Variable | Default | Purpose |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated exact frontend origins accepted by FastAPI. |
| `LABELGUARD_DATA_DIR` | `data` from the backend directory | SQLite, uploads, evidence and report storage. |
| `UPLOAD_RATE_LIMIT_PER_MINUTE` | `30` | Per-client inspection upload throttle. |
| `GEMINI_ENABLED` | `true` in the example | Enables the required Gemini image reader. |
| `GEMINI_API_KEY` | empty | Backend-only Gemini credential. |
| `GEMINI_MODEL` | `gemini-3.7-flash` | Primary/backward-compatible model. |
| `GEMINI_FAST_MODEL` | `gemini-3.7-flash` | Preferred model for normal-quality images. |
| `GEMINI_QUALITY_MODEL` | `gemini-3.1-pro-preview` | Preferred model for difficult images. |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.6-flash,gemini-2.5-flash` | Ordered route for model/provider failures. |
| `GEMINI_TIMEOUT_SECONDS` | `45` | Per-provider-call timeout. |
| `GEMINI_RATE_LIMIT_PER_MINUTE` | `10` | Process-local sliding-window provider-attempt limit. |
| `GEMINI_MAX_CONCURRENT_REQUESTS` | `2` | Maximum concurrent Gemini calls per backend process. |
| `GEMINI_MAX_ATTEMPTS_PER_MODEL` | `2` | Transient attempts before routing to the next model. |
| `GEMINI_EXPLANATION_ENABLED` | `false` | Optional post-verdict non-visual explanation call. |
| `GEMINI_EXPLANATION_MODEL` | fast model | Model used only for optional explanation. |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Browser-visible backend URL. Configure in the frontend environment when hosted. |

Model availability can differ by account and region. Update the configured model names if the API key does not have access to the defaults.

## Using LabelGuard

1. Open **New inspection**.
2. Upload or capture a clear label image, up to 10 MB.
3. Choose whether the package is domestic, imported, or unknown.
4. Optionally enter the commodity category.
5. Submit the image and wait for the routed Gemini extraction.
6. Review extracted declarations, confidence, evidence boxes, findings and image quality.
7. Correct a field only after checking the original image. Corrections are attributed and rerun deterministic rules.
8. Record an independent reviewer disposition when required.
9. Export history or open the generated PDF report.

If Gemini is disabled, unconfigured, rate-limited or unavailable, the inspection returns an explicit error. LabelGuard does not silently switch to OCR or fabricate a result.

## Application routes

| Route | Purpose |
|---|---|
| `/` | Database-backed dashboard and readiness summary |
| `/inspections/new` | Upload, camera capture and inspection |
| `/inspections/[id]` | Evidence, declarations, findings, correction, review and report |
| `/review` | Human review queue |
| `/history` | Searchable history and exports |
| `/analytics` | Descriptive inspection and review metrics |
| `/rules` | Active deterministic rule metadata |
| `/system` | Database, Gemini route/limit and rule-engine diagnostics |

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/inspect` | Inspect and persist one package image |
| `GET` | `/inspection/{id}` | Return complete inspection detail |
| `GET` | `/inspection/{id}/image` | Return the original image |
| `GET` | `/inspection/{id}/evidence-image` | Return the evidence-overlay image |
| `POST` | `/inspection/{id}/correct` | Save an attributed correction and rerun rules |
| `POST` | `/inspection/{id}/review` | Record independent human review |
| `GET` | `/inspection/{id}/audit` | Return corrections, reviews and audit events |
| `GET` | `/history` | Return filterable history |
| `GET` | `/review-queue` | Return items requiring review |
| `GET` | `/analytics` | Return descriptive aggregate metrics |
| `GET` | `/rules` | Return active validated rule metadata |
| `GET` | `/report/{id}` | Generate or return the PDF report |
| `GET` | `/exports/history.csv` | Export spreadsheet-safe history |
| `GET` | `/exports/history.json` | Export JSON history |
| `GET` | `/system/status` | Return readiness, routing and limiter status without secrets |

Legacy `/api/...` aliases remain for compatibility. New integrations should use the canonical endpoints above.

## Testing and verification

### Windows PowerShell

```powershell
cd C:\path\to\LabelGuard

backend\.venv\Scripts\python.exe -m pytest backend\tests -q `
  --basetemp tmp\pytest-readme -p no:cacheprovider

npm run typecheck
npm run lint
npm run build
npm audit
npm --prefix frontend audit
```

### macOS or Linux

```bash
cd /path/to/LabelGuard

backend/.venv/bin/python -m pytest backend/tests -q \
  --basetemp tmp/pytest-readme -p no:cacheprovider

npm run typecheck
npm run lint
npm run build
npm audit
npm --prefix frontend audit
```

The latest complete local verification passed:

- 194 backend tests
- frontend TypeScript checking
- frontend ESLint with zero warnings
- Next.js production build
- root and frontend npm security audits with zero known vulnerabilities
- Python dependency audit with no known vulnerabilities
- live `npm run dev` backend/frontend smoke test
- real Pintola regression with correct MRP, net quantity, manufacture date and consumer-care evidence

One non-blocking third-party Starlette/httpx deprecation warning remains in the backend test environment.

GitHub Actions repeats backend tests, Python and npm dependency audits, frontend typecheck/lint/build, and the backend Docker build for pushes to `main` and pull requests.

## Demo fixtures

The `samples/` directory contains synthetic demonstration labels. Regenerate them with:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\generate_demo_labels.py
```

See [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md) for the recommended demonstration sequence.

## Deployment

The repository supports a single-instance prototype deployment:

- Backend: Docker-based Render service using the root `render.yaml` blueprint and a persistent `/var/data` disk.
- Frontend: Vercel project with `frontend` selected as the root directory.
- Required backend secret: `GEMINI_API_KEY`.
- Required frontend variable: `NEXT_PUBLIC_API_BASE_URL` pointing to the Render backend.
- Required backend CORS value: the exact Vercel origin, without a trailing slash.

Do not autoscale the current Render service while SQLite and local filesystem media are in use. Follow [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the complete deployment and smoke-test procedure.

## Data and security

- `backend/.env` is ignored by Git and must never be committed.
- SQLite databases, uploaded images, generated evidence, reports, backups and temporary files are ignored.
- The configured Gemini API key is never returned by `/system/status`.
- Uploaded package imagery is sent to the configured Gemini service.
- Image uploads are decoded and validated rather than trusted by filename or browser MIME type alone.
- Spreadsheet exports are protected against formula injection.
- Schema initialization is additive; do not delete the database or uploads as a troubleshooting shortcut.
- Use only synthetic or authorized imagery during development and demonstration.

Before the first commit, verify ignored secrets and runtime data:

```powershell
git check-ignore backend\.env backend\data\labelguard.sqlite3
```

Both paths should be printed, confirming that Git will ignore them.

## Current limitations

- No authentication, authorization or tenant isolation.
- SQLite and local filesystem media support only a trusted single-instance prototype.
- Gemini availability, latency, quota, model access and external data processing remain provider constraints.
- Model routing and request limiting are process-local; horizontal scaling requires shared circuit state and a distributed limiter such as Redis or an API gateway.
- Category-specific exemptions and legal interpretations are not inferred automatically.
- The included legal-rule corpus is a prototype baseline, not exhaustive legal authority.
- Ambiguous, conflicting, unanchored or unreadable declarations intentionally require manual review.

## Publishing to GitHub

Create an empty GitHub repository without adding a GitHub-generated README, license or `.gitignore`. Then run the commands below from the LabelGuard root, replacing the URL with your repository URL.

```powershell
cd C:\Users\amogh\OneDrive\Desktop\LabelGuard

git init
git add .
git status
git diff --cached --name-only
git commit -m "Initial commit: LabelGuard Gemini-only extraction"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Before committing, confirm that `backend/.env`, databases, uploaded images and other runtime files do not appear in the staged-file list.

For later updates:

```powershell
git add .
git commit -m "Describe your change"
git push
```

If an `origin` remote already exists, update it instead of adding another:

```powershell
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
```

## Further documentation

- [`docs/GEMINI_ONLY_IMPLEMENTATION_REPORT.md`](docs/GEMINI_ONLY_IMPLEMENTATION_REPORT.md)
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md)
- [`docs/SECURITY_AUDIT.md`](docs/SECURITY_AUDIT.md)

