# RTI Legal Research & Precedent Support System

An internal legal-intelligence application for assisting Indian government officers with RTI Act, 2005 research, precedent lookup, statutory analysis, and draft reply generation.

This project is currently tailored for the Chhattisgarh Infotech Promotion Society (CHiPS) RTI workflow, but the architecture is general enough to support other public authorities after updating department data, corpus files, templates, and deployment settings.

> Important: This system provides legal research and drafting assistance only. The final decision under the RTI Act, 2005 remains the responsibility of the concerned Public Information Officer (PIO).

The application must not be treated as an automated decision-making system. It should not decide "approve", "reject", "transfer", "partial disclosure", or "full disclosure" on behalf of the PIO. Its role is to help the PIO understand the request, relevant RTI Act provisions, comparable cases, legal observations, disclosure arguments, exemption arguments, and draft reply language.

---

## Table Of Contents

1. [What This Project Does](#what-this-project-does)
2. [Current Product Flow](#current-product-flow)
3. [Repository Structure](#repository-structure)
4. [Technology Stack](#technology-stack)
5. [Prerequisites](#prerequisites)
6. [Fresh Setup On Windows](#fresh-setup-on-windows)
7. [Running The Application](#running-the-application)
8. [Backend API](#backend-api)
9. [Frontend App](#frontend-app)
10. [Legal Corpus And Indexing](#legal-corpus-and-indexing)
11. [Testing And Verification](#testing-and-verification)
12. [Environment Variables](#environment-variables)
13. [Data And Generated Files](#data-and-generated-files)
14. [Troubleshooting](#troubleshooting)
15. [Product And Legal Guardrails](#product-and-legal-guardrails)
16. [MVP Scope And Phase 2 Direction](#mvp-scope-and-phase-2-direction)

---

## What This Project Does

The system helps a PIO process an RTI application without forcing the officer through intermediate manual checkpoints during the first analysis run.

At a high level it can:

- Accept an RTI application as pasted text.
- Accept an uploaded document and extract text using document parsing or OCR.
- Run a full backend pipeline after submission without user interruption.
- Show a ChatGPT/Claude-style processing screen while the pipeline runs.
- Extract legal research parameters from the application.
- Identify relevant RTI Act sections and possible exemption/disclosure issues.
- Retrieve similar CIC/SIC/court-style precedent chunks where indexed locally.
- Generate a draft RTI reply for PIO review.
- Let the user open "Edit & Refine" only after the draft is generated.
- Re-run only the drafting stage after edited parameters, instead of re-running OCR, routing, extraction, and statutory analysis.
- Export reports and draft response files.
- Log assistance records and preserve an audit trail.

The current application is a local desktop/development MVP. It is not yet a production NIC-style deployment.

---

## Current Product Flow

The React UI follows this working flow:

```text
1. Intake
   User pastes RTI text or uploads a file.

2. Processing
   The system runs OCR/document parsing, routing context, extraction,
   statutory review, legal research synthesis, and drafting without stopping.

3. Result
   The user sees the final assisted draft reply and legal research context.

4. Edit & Refine
   Only after seeing the result, the user may edit AI-extracted parameters.

5. Regenerate
   Regeneration after editing re-runs the draft generation stage only.

6. Assistance Record
   The user can log that the generated material was reviewed as assistance.
```

This is intentionally different from older "decision support" flows. The UI should frame the product as:

```text
Legal Research & Precedent Support
```

not as:

```text
Automated Decision Support
```

---

## Repository Structure

```text
.
|-- backend/
|   |-- main.py                  FastAPI API server used by React
|   |-- document_parser.py       Upload/document parsing wrapper
|   |-- ocr.py                   PDF/image OCR helpers
|   |-- routing.py               Department/routing context logic
|   |-- extractor.py             RTI parameter extraction
|   |-- exemption_rules.py       Deterministic RTI exemption flags
|   |-- llm_analyzer.py          LLM-assisted statutory analysis
|   |-- disclosure_balancer.py   Arguments for and against disclosure
|   |-- response_letter.py       Draft RTI reply generation/export helpers
|   |-- export_report.py         Analysis report generation
|   |-- audit_logger.py          Assistance/audit logging helpers
|   |-- db.py                    SQLite audit persistence
|   |-- sarvam_client.py         Sarvam chat-completions client
|   |-- requirements.txt         Backend dependencies
|   `-- README.md                Backend-specific notes
|
|-- frontend-react/
|   |-- src/
|   |   |-- App.tsx              Main React shell and header/navigation
|   |   |-- lib/stepMachine.ts   Intake/processing/result/refine flow
|   |   |-- components/          UI components and screens
|   |   `-- index.css            Tailwind/base styles
|   |-- package.json             Node scripts and dependencies
|   |-- vite.config.ts           Vite config, API proxy to backend:8002
|   `-- README.md                Frontend notes
|
|-- src/
|   |-- pipeline/                Legal extraction, segmentation, chunking
|   |-- pipelines/               CLI indexing and query orchestrators
|   |-- retrieval/               BM25/vector/hybrid retrieval
|   |-- rag/                     Context assembly for legal reasoning
|   |-- engine/                  RTI analysis orchestration
|   |-- generation/              Response package templates
|   |-- storage/                 Metadata persistence
|   `-- README.md                Legal retrieval pipeline notes
|
|-- data/
|   |-- chunks/                  Generated legal chunk JSONL files
|   |-- extracted/               Extracted text from PDFs/documents
|   |-- indexes/                 BM25 index and doc map
|   |-- metadata/                Extracted case metadata JSON
|   |-- db/                      Local SQLite case metadata
|   `-- vectorstore/             Local Chroma/vector data if enabled
|
|-- scratch/
|   |-- start_backend.py         Starts FastAPI backend on port 8002
|   |-- test_api_server.py       Simple API smoke test
|   `-- backend_persistent.log   Backend log created by start_backend.py
|
|-- tests/
|   `-- test_integration.py      Phase 1 integration tests
|
|-- requirements.txt             Legal retrieval/indexing dependencies
`-- README.md                    This file
```

---

## Technology Stack

### Frontend

- React 18
- TypeScript
- Vite
- Tailwind CSS
- Radix UI primitives
- Lucide React icons

### Backend

- FastAPI
- Pydantic
- SQLite
- python-docx
- PyMuPDF
- pdfplumber
- pytesseract
- Pillow
- requests

### Legal Retrieval Pipeline

- BM25 via `rank_bm25`
- ChromaDB vector store
- Sentence Transformers for local embeddings
- Optional Ollama/Qwen for local reasoning paths
- Sarvam AI for cloud LLM-backed extraction, analysis, and drafting paths

---

## Prerequisites

Install these before running the full project:

1. Python 3.10 or newer
2. Node.js 18 or newer
3. npm
4. Git
5. Optional: Ollama, if you want local model support
6. Optional: Tesseract OCR, if you want scanned image/PDF OCR
7. Optional: Poppler, if PDF-to-image OCR paths are used

For the current local project path, PowerShell examples assume:

```powershell
cd "C:\Users\hp\OneDrive\Desktop\major-rti\major rti"
```

If your project is stored somewhere else, replace the path in the commands.

---

## Fresh Setup On Windows

### 1. Clone Or Open The Project

```powershell
cd "C:\Users\hp\OneDrive\Desktop\major-rti"
cd "major rti"
```

### 2. Create A Python Virtual Environment

If you do not already have a virtual environment:

```powershell
python -m venv backend\.venv
```

Activate it:

```powershell
backend\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
backend\.venv\Scripts\Activate.ps1
```

You can also use Anaconda Python directly, as many local scripts in this repo have been run with:

```powershell
c:\Users\hp\anaconda3\python.exe
```

### 3. Install Backend Dependencies

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 4. Install Legal Retrieval Dependencies

```powershell
backend\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you use Anaconda instead:

```powershell
c:\Users\hp\anaconda3\python.exe -m pip install -r backend\requirements.txt
c:\Users\hp\anaconda3\python.exe -m pip install -r requirements.txt
```

### 5. Install Frontend Dependencies

```powershell
cd frontend-react
npm install
cd ..
```

### 6. Optional Local Models

Install Ollama from:

```text
https://ollama.com
```

Then pull local models if needed:

```powershell
ollama pull nomic-embed-text
ollama pull qwen2.5:3b
ollama pull qwen2.5:14b
```

Regex-only indexing and basic API tests do not require Ollama.

---

## Running The Application

The main app is the React + FastAPI workflow.

You need two terminals.

### Terminal 1: Start Backend

From the repository root:

```powershell
c:\Users\hp\anaconda3\python.exe run.py --provider mock
```

Choose the provider for the kind of work you are doing:

```powershell
# Production behavior: Sarvam API, real retrieval, real drafting
c:\Users\hp\anaconda3\python.exe run.py --provider sarvam

# Local LLM behavior: Ollama qwen, no Sarvam API cost
c:\Users\hp\anaconda3\python.exe run.py --provider ollama --model qwen2.5:14b

# Frontend/workflow testing: deterministic fake AI responses
c:\Users\hp\anaconda3\python.exe run.py --provider mock
```

The backend runs at:

```text
http://127.0.0.1:8002
```

The script writes logs to:

```text
scratch/backend_persistent.log
```

Health check:

```text
http://127.0.0.1:8002/api/health
```

AI provider status:

```text
http://127.0.0.1:8002/api/ai/status
```

Expected response:

```json
{
  "status": "ok"
}
```

### Terminal 2: Start Frontend

From the repository root:

```powershell
cd frontend-react
npm run dev
```

The frontend runs at:

```text
http://localhost:3000
```

The Vite proxy sends `/api/...` requests to:

```text
http://localhost:8002
```

### Normal Browser Flow

1. Open `http://localhost:3000`.
2. Paste an RTI application or upload a supported file.
3. Submit the application.
4. Wait on the processing screen.
5. Review the generated draft reply.
6. Optionally click `Edit & Refine`.
7. Regenerate the draft after edits.
8. Log/download assistance outputs if needed.

---

## Backend API

The FastAPI application lives in:

```text
backend/main.py
```

Important endpoints:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/health` | GET | Basic backend health check |
| `/api/ocr` | POST | Extract text from uploaded document |
| `/api/route` | POST | Get department/routing context |
| `/api/extract` | POST | Extract structured RTI parameters |
| `/api/evaluate_exemptions` | POST | Run statutory/legal research synthesis |
| `/api/generate_draft` | POST | Generate or regenerate draft RTI reply |
| `/api/download_analysis` | POST | Download analysis report |
| `/api/download_response` | POST | Download draft response |
| `/api/log_decision` | POST | Log assistance/audit record |
| `/api/audit_trail` | GET | Read recent audit trail records |
| `/api/system_status` | GET | Check database/OCR/Ollama status |
| `/api/legal_sections` | GET | Return local RTI Act section reference data |

### API Smoke Test

Start the backend first, then run:

```powershell
backend\.venv\Scripts\python.exe scratch\test_api_server.py
```

or:

```powershell
c:\Users\hp\anaconda3\python.exe scratch\test_api_server.py
```

This checks health, route, extract, legal evaluation, and logging endpoints.

---

## Frontend App

The main React app is in:

```text
frontend-react/src/App.tsx
```

The step flow is controlled by:

```text
frontend-react/src/lib/stepMachine.ts
```

Important screens:

| File | Purpose |
| --- | --- |
| `frontend-react/src/components/steps/InputStep.tsx` | Text/file intake |
| `frontend-react/src/components/steps/ProcessingStep.tsx` | Thinking/progress screen during backend pipeline |
| `frontend-react/src/components/steps/ResultStep.tsx` | Assisted draft reply and legal research output |
| `frontend-react/src/components/steps/RefineStep.tsx` | Post-result edit/refine screen |
| `frontend-react/src/components/steps/CompletedStep.tsx` | Assistance record completion screen |

Build the frontend:

```powershell
cd frontend-react
npm run build
```

Preview a production build:

```powershell
cd frontend-react
npm run preview
```

---

## Legal Corpus And Indexing

The corpus pipeline under `src/` converts CIC/SIC/legal source files into metadata, chunks, BM25 indexes, and optional vector indexes.

Main indexing file:

```text
src/pipelines/index_pipeline.py
```

### Common Fast Indexing Command

Use this when you want to process the local dummy CIC case corpus and rebuild BM25 without waiting for vector embeddings:

```powershell
c:\Users\hp\anaconda3\python.exe src\pipelines\index_pipeline.py --source data\dummy-cic-case --mode regex-only --force --skip-embeddings
```

What the flags mean:

| Flag | Meaning |
| --- | --- |
| `--source data\dummy-cic-case` | Folder containing source PDFs or extracted text |
| `--mode regex-only` | Use deterministic extraction instead of local LLM extraction |
| `--force` | Reprocess already indexed cases and overwrite metadata/chunk JSONL |
| `--skip-embeddings` | Skip Chroma/vector embeddings and rebuild BM25 only |

Use `--skip-embeddings` if Sentence Transformers cannot download a model or if you only need BM25 search.

### Rebuild BM25 Only

```powershell
c:\Users\hp\anaconda3\python.exe src\pipelines\index_pipeline.py --rebuild-index
```

### Full Indexing With Embeddings

Only use this when local embedding dependencies are installed and the sentence-transformers model is cached or network access is available:

```powershell
c:\Users\hp\anaconda3\python.exe src\pipelines\index_pipeline.py --source data\dummy-cic-case --mode regex-only --force
```

If the run repeatedly tries to access HuggingFace and fails, use:

```powershell
--skip-embeddings
```

### Query Pipeline

Run a local legal retrieval query from the command line:

```powershell
c:\Users\hp\anaconda3\python.exe src\pipelines\query_pipeline.py --text "Please provide file notings. If denied under Section 8(1)(j), provide reasons." --type exemption_check --department-hint "Revenue Department"
```

The output includes:

- `analysis`
- `responses.internal_note`
- `responses.pio_recommendation`
- `responses.draft_rti_reply`

Note: Some legacy names still contain `recommendation` because they are older data models. Product-facing UI should present legal research and draft assistance, not final decision automation.

---

## Testing And Verification

### Backend Import Check

```powershell
backend\.venv\Scripts\python.exe -c "import backend.main; print('backend import ok')"
```

### API Smoke Test

Backend must be running first:

```powershell
backend\.venv\Scripts\python.exe scratch\test_api_server.py
```

### Legal Extractor Regression Tests

This checks the legal extractor, including protection against reading dates as RTI sections:

```powershell
c:\Users\hp\anaconda3\python.exe src\pipeline\legal_extractor.py --test
```

### Integration Tests

```powershell
backend\.venv\Scripts\python.exe -m pytest tests\test_integration.py -v --no-llm
```

If your corpus path is different:

```powershell
$env:CIC_DECISIONS_DIR="data\dummy-cic-case"
backend\.venv\Scripts\python.exe -m pytest tests\test_integration.py -v --no-llm
```

### Frontend Build Test

```powershell
cd frontend-react
npm run build
```

---

## Environment Variables

The project supports provider switching for development and production:

| Mode | Command | AI behavior |
| --- | --- | --- |
| Production | `python run.py --provider sarvam` | Uses Sarvam API. Requires `SARVAM_API_KEY`. |
| Local LLM | `python run.py --provider ollama --model qwen2.5:14b` | Uses local Ollama. No Sarvam API cost. |
| Mock | `python run.py --provider mock` | Uses deterministic fake responses. No external AI calls. |

The selected mode is stored in `RTI_AI_PROVIDER`, and the model is stored in `RTI_AI_MODEL`.

### Sarvam

Set your key in the shell before starting the backend:

```powershell
$env:SARVAM_API_KEY="your_key_here"
```

Optional overrides:

```powershell
$env:SARVAM_MODEL="sarvam-105b"
$env:SARVAM_API_URL="https://api.sarvam.ai/v1/chat/completions"
```

Do not commit real API keys to the repository.

### Ollama / Qwen

```powershell
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
c:\Users\hp\anaconda3\python.exe run.py --provider ollama --model qwen2.5:14b
```

Ollama default API URL:

```text
http://localhost:11434
```

---

## Data And Generated Files

Common generated paths:

| Path | Meaning |
| --- | --- |
| `scratch/backend_persistent.log` | Backend runtime log from `scratch/start_backend.py` |
| `rti_audit.db` | Root audit database used by some older code paths |
| `backend/rti_audit.db` | Backend audit database if created by backend modules |
| `audit_log/` | File-based audit output, if enabled |
| `data/extracted/` | Extracted text and extraction metadata |
| `data/metadata/` | Extracted case metadata JSON |
| `data/chunks/` | Legal chunk JSONL files |
| `data/indexes/bm25_index.pkl` | BM25 index |
| `data/indexes/bm25_docmap.json` | BM25 chunk lookup map |
| `data/db/cases.db` | SQLite case metadata store |
| `data/vectorstore/` | Chroma/vector store data |

Generated data may be large. Do not delete corpus or generated indexes unless you are intentionally rebuilding.

---

## Troubleshooting

### Frontend Loads But API Calls Fail

Check that the backend is running on port `8002`:

```text
http://127.0.0.1:8002/api/health
```

Also check:

```text
frontend-react/vite.config.ts
```

The proxy should point to:

```text
http://localhost:8002
```

### Backend Starts But Browser Shows Old Results

Restart both servers:

```powershell
# Stop backend terminal with Ctrl+C
# Stop Vite terminal with Ctrl+C

backend\.venv\Scripts\python.exe scratch\start_backend.py

cd frontend-react
npm run dev
```

Then hard-refresh the browser.

### `ModuleNotFoundError`

Install both dependency files:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### OCR Does Not Work For Scanned PDFs

Install Tesseract OCR and ensure it is on PATH.

On Windows, verify:

```powershell
tesseract --version
```

If Tesseract is unavailable, digital PDFs and text input can still work through non-OCR paths.

### Indexing Is Too Slow

Use regex-only mode and skip embeddings:

```powershell
c:\Users\hp\anaconda3\python.exe src\pipelines\index_pipeline.py --source data\dummy-cic-case --mode regex-only --force --skip-embeddings
```

### Sentence Transformers Tries To Download And Fails

This happens when the embedding model is not cached and network access is blocked. Use:

```powershell
--skip-embeddings
```

BM25 will still be rebuilt.

### Bad Sections Like `10`, `20`, `11` Appear From Dates

Run the latest extractor and force-refresh chunks:

```powershell
c:\Users\hp\anaconda3\python.exe src\pipeline\legal_extractor.py --test
c:\Users\hp\anaconda3\python.exe src\pipelines\index_pipeline.py --source data\dummy-cic-case --mode regex-only --force --skip-embeddings
```

The extractor should only treat explicit references like `Section 8(1)(j)` or `u/s 6(3)` as RTI sections.

### Port Already In Use

Find the process using the port:

```powershell
netstat -ano | findstr :8002
```

Stop it from Task Manager or use a different port in:

```text
scratch/start_backend.py
frontend-react/vite.config.ts
```

---

## Product And Legal Guardrails

These are non-negotiable design rules for this system:

1. The system is a legal research and drafting assistant, not a decision engine.
2. The first submitted RTI application should run through the full pipeline without user interruption.
3. The user should see only the processing screen until the generated draft/result is ready.
4. Extracted parameters can be edited only after the generated result is shown.
5. Regeneration after edits must re-run only the drafting stage.
6. UI labels must avoid final-decision language as the primary output.
7. The final PIO responsibility disclaimer must be visible in the result flow.
8. All generated text must be treated as assistance and reviewed by the officer.
9. Legal reasoning should be grounded in the RTI Act, indexed precedents, circulars, and local source material.
10. Audit records should preserve what the system generated and what the user logged.

Recommended disclaimer text:

```text
This system provides legal research and drafting assistance only. The final decision under the RTI Act, 2005 remains the responsibility of the concerned PIO.
```

---

## MVP Scope And Phase 2 Direction

### MVP

The current MVP should focus on:

- Text intake and file upload intake.
- Full uninterrupted processing after submit.
- Processing/thinking UI.
- RTI Act, 2005 statutory analysis.
- Extracted RTI parameters.
- Legal research synthesis.
- Draft RTI reply generation.
- Post-result edit/refine flow.
- Draft-only regeneration after edits.
- Basic audit/assistance logging.
- Word/report downloads.
- Local CIC chunk indexing and BM25 retrieval.

### Phase 2

Phase 2 can add:

- More complete CIC decision corpus.
- SIC decision corpus.
- High Court judgment corpus.
- Supreme Court judgment corpus.
- Departmental circulars and guidelines.
- Better precedent ranking and citation display.
- Role-based workflows for PIO, FAA, and Admin.
- Case assignment and workload tracking.
- Stronger audit dashboards.
- Production authentication.
- Deployment hardening.
- Offline model packaging.
- More robust multilingual OCR and Hindi drafting.

---

## Role-Based User Types

### PIO

Primary user. Can submit RTI applications, review generated legal research, edit/refine extracted parameters after generation, regenerate drafts, download outputs, and log assistance records.

### FAA

Reviewer. Can inspect prior assistance records, draft replies, legal reasoning, and audit history for appeal-stage review. Should not alter original PIO assistance records except through a separate review record.

### Admin

System manager. Can manage corpus updates, department mappings, users, audit exports, indexing jobs, configuration, and health monitoring.

---

## Quick Command Reference

From the project root:

```powershell
# Start backend
backend\.venv\Scripts\python.exe scratch\start_backend.py

# Start frontend
cd frontend-react
npm run dev

# Backend smoke test
backend\.venv\Scripts\python.exe scratch\test_api_server.py

# Legal extractor tests
c:\Users\hp\anaconda3\python.exe src\pipeline\legal_extractor.py --test

# Fast corpus refresh
c:\Users\hp\anaconda3\python.exe src\pipelines\index_pipeline.py --source data\dummy-cic-case --mode regex-only --force --skip-embeddings

# Frontend build
cd frontend-react
npm run build
```

---

## Current Status Notes

- The active UI is `frontend-react`.
- The active backend startup script is `scratch/start_backend.py`.
- The backend port used by the frontend proxy is `8002`.
- The product language has been shifted from decision support to legal research and precedent support.
- Some older backend/model names still contain terms like `recommendation` for compatibility. These should be hidden or reframed at the UI/product layer unless refactored carefully.
- The corpus pipeline can rebuild BM25 without embeddings using `--skip-embeddings`.
- For local development, prefer non-destructive re-indexing and avoid deleting source PDFs or extracted corpus data.
