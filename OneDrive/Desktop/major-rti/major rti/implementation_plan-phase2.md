# Implementation Plan: Project Reorganization & Phase 2 (RAG & LLM Exemption Analyzer)

This plan details the steps to reorganize the project structure into clean directories (`backend`, `frontend`, `data`, `notebooks`), verify the new layout, and implement **Phase 2 (LLM Exemption Analyzer - Agent 3 Layer B)** with a local RAG pipeline over the RTI Act text.

---

## Proposed Changes

### Component 1: Folder Reorganization

#### [NEW] [backend/](file:///c:/Users/hp/OneDrive/Desktop/dummy/backend)
Create the `backend/` directory to house all core python modules:
- Move [db.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/db.py) ➔ `backend/db.py`
- Move [ocr.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/ocr.py) ➔ `backend/ocr.py`
- Move [routing.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/routing.py) ➔ `backend/routing.py`
  - **Modify**: Update `_DATA_DIR` from `_BASE_DIR / "data"` to `_BASE_DIR.parent / "data"` so it references the root `/data` folder.
- Move [extractor.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/extractor.py) ➔ `backend/extractor.py`
- Move [exemption_rules.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/exemption_rules.py) ➔ `backend/exemption_rules.py`

#### [NEW] [frontend/](file:///c:/Users/hp/OneDrive/Desktop/dummy/frontend)
Create the `frontend/` directory to house client-facing dashboards:
- Move [app.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/app.py) ➔ `frontend/app.py`
  - **Modify**: Insert path injection at the top of the file to add `backend/` to `sys.path`:
    ```python
    import sys
    from pathlib import Path
    backend_dir = Path(__file__).resolve().parent.parent / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    ```
  - **Modify**: Update `dept_path` from `Path(__file__).parent / "data" / ...` to `Path(__file__).resolve().parent.parent / "data" / ...` in two dropdown loading functions.

#### [NEW] [notebooks/](file:///c:/Users/hp/OneDrive/Desktop/dummy/notebooks)
Create the `notebooks/` directory to house test, scratch, and benchmarking scripts:
- Move [verify_routing.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/verify_routing.py) ➔ `notebooks/verify_routing.py`
  - **Modify**: Add `backend/` to `sys.path` dynamically.
  - **Modify**: Update `sample_rtis.json` search path to point to root `/data/sample_rtis.json`.
  - **Modify**: Update `benchmark_results.json` output path to point to root `/data/benchmark_results.json`.
- Move `verify_phase1.py` ➔ `notebooks/verify_phase1.py`
  - **Modify**: Add `backend/` to `sys.path` dynamically.
- Move [test_ocr.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/test_ocr.py) ➔ `notebooks/test_ocr.py`
  - **Modify**: Add `backend/` to `sys.path` dynamically. Update test PDF path to point to `/data/`.
- Move [quick_test.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/quick_test.py) ➔ `notebooks/quick_test.py`
  - **Modify**: Add `backend/` to `sys.path` dynamically.

#### [MODIFY] [data/](file:///c:/Users/hp/OneDrive/Desktop/dummy/data)
Clean up the root directory by moving documents to `data/`:
- Move `5_6104888577781406923.pdf` ➔ `data/5_6104888577781406923.pdf`
- Move `RTI_Intelligence_System_Architecture.docx` ➔ `data/RTI_Intelligence_System_Architecture.docx`
- Move `arch.txt` ➔ `data/arch.txt`

---

### Component 2: Phase 2 - RAG Legal Corpus & LLM Exemption Analyzer

#### [NEW] [rti_act_sections.json](file:///c:/Users/hp/OneDrive/Desktop/dummy/data/rti_act_sections.json)
Create a structured data file containing the official statutory text of the RTI Act 2005 (Sections 8(1)(a)-(j), 8(2), 9, 11). This will act as our ground-truth legal corpus.

#### [NEW] [rag_engine.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/backend/rag_engine.py)
Create a RAG module that:
1. Embeds each statutory section of the RTI Act using Ollama `nomic-embed-text`.
2. Caches embeddings to `data/rti_sections_embeddings.json` (similar to department embeddings).
3. Performs dense cosine similarity search of the RTI text query against the section embeddings.
4. Returns the top-k relevant statutory passages and citations.

#### [NEW] [llm_analyzer.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/backend/llm_analyzer.py)
Create the LLM-based Exemption Analyzer (Agent 3 - Layer B):
1. Input: RTI text, triggered Layer A rules, and RAG-retrieved statutory text.
2. Prompts Qwen `qwen2.5:3b` to perform a rigorous analysis of the flagged exemptions.
3. Strict Grounding Constraint: The LLM is prohibited from citing any statutory section or case logic not provided in the RAG context.
4. Output Schema:
   - `section`: section number (e.g. `8(1)(j)`)
   - `is_applicable`: boolean
   - `confidence_score`: float
   - `legal_argument_pro_disclosure`: reasoning for disclosure
   - `legal_argument_pro_exemption`: reasoning for exemption (adversarial balance)
   - `exact_quotes`: list of exact statutory sentences used

#### [MODIFY] [app.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/frontend/app.py)
Integrate Phase 2 output into Step 3 of the PIO Dashboard:
- Run RAG + LLM Analyzer on the verified metadata.
- Display pro-disclosure and pro-exemption legal arguments side-by-side in custom card components to enable balanced, adversarial judgment (human final decision).

---

## Verification Plan

### Reorganization Verification
- Execute `notebooks/quick_test.py` to verify imports and db connections work under the new folder layout.
- Execute `notebooks/verify_routing.py` to confirm the department classifier still runs successfully.
- Run `streamlit run frontend/app.py` to verify the UI launches and navigates pages.

### Phase 2 Verification
- Execute a new benchmark script `notebooks/verify_phase2.py` checking LLM analyzer compliance against personal, tender, and cybersecurity inputs. Validate that the RAG model returns exact quotes.
- Manual dashboard audit: Check that side-by-side disclosure arguments are clear and professional.
