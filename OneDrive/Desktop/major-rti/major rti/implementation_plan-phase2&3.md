# Implementation Plan: Phase 2 & Phase 3 (RAG, Exemption Analyzer, Disclosure Balancer, and Recommendation Generator)

This plan outlines the design and implementation of the remaining analytical agents (Agents 3-B, 4, and 5) and the legal RAG engine, culminating in a fully integrated, legally grounded decision support system.

---

## Proposed Changes

### Component 1: RAG Engine & Legal Corpus

#### [NEW] [rti_act_sections.json](file:///c:/Users/hp/OneDrive/Desktop/dummy/data/rti_act_sections.json)
A structured dataset containing the official statutory text of the RTI Act 2005. It chunks sections section-by-section to preserve complete legal meaning (avoiding token-based splits):
- **Section 8(1)(a)** to **Section 8(1)(j)** (Exemptions from disclosure)
- **Section 8(2)** (Public interest override)
- **Section 9** (Infringement of copyright)
- **Section 11(1)** (Third-party information procedure)

#### [NEW] [rag_engine.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/backend/rag_engine.py)
A local RAG search engine:
- Computes embeddings for the legal chunks using Ollama `nomic-embed-text`.
- Caches embeddings to `data/rti_sections_embeddings.json`.
- Performs Cosine Similarity query matching against the cached vectors.
- Returns a list of grounded text snippets and exact section headers.

---

### Component 2: Exemption & Balancer Agents

#### [NEW] [llm_analyzer.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/backend/llm_analyzer.py)
Agent 3 (Layer B):
- Receives the RTI query, the triggered rules (from Layer A), and the RAG-retrieved statutory text.
- Prompts Qwen `qwen2.5:3b` to perform a granular analysis of why each triggered rule applies or does not apply.
- Grounding: LLM is strictly prohibited from citing any statutory section or case logic not provided in the RAG context.

#### [NEW] [disclosure_balancer.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/backend/disclosure_balancer.py)
Agent 4 (Adversarial Balancer):
- Prompts the LLM to generate two side-by-side legal cases:
  1. The strongest legal argument **FOR disclosure** (citing public interest overrides, severability under Section 10, or lack of competitive harm).
  2. The strongest legal argument **AGAINST disclosure** (citing protection of commercial secrets, privacy invasion, or state security risks).

---

### Component 3: Recommendation Engine & Dashboard Integration

#### [NEW] [recommendation_generator.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/backend/recommendation_generator.py)
Agent 5 (Synthesis Engine):
- Combines routing results, verified parameters, rules, LLM analyses, and the disclosure balance.
- Outputs a final recommendation conforming to a strict Pydantic schema (`FinalRecommendation`), containing final action (Transfer / Approve / Partially Approve / Reject), confidence band, primary reasoning (under 150 words), list of applied sections, and risks.

#### [MODIFY] [app.py](file:///c:/Users/hp/OneDrive/Desktop/dummy/frontend/app.py)
Integrate all three agents into Step 3 of the PIO Dashboard:
- Run RAG + Layer B + Balancer + Recommendation Generator after Step 2 verification.
- Render the final Recommendation Card at the top of Step 3 (displaying suggested action, confidence, reasoning, and applied sections).
- Render a side-by-side split screen showing:
  - Left panel: Legal case for disclosure.
  - Right panel: Legal case for rejection/redaction.
- Retain the PIO decision form (action, custom override, comments, disclaimer box).

---

## Verification Plan

### Automated Benchmarks
- Create a test script `notebooks/verify_phase2_3.py` to validate that:
  - The RAG engine retrieves correct sections.
  - The balancer correctly generates side-by-side arguments.
  - The recommendation schema parses successfully.

### Manual Verification
- Test end-to-end flow with a sample tender request, confirming:
  - It triggers Section 8(1)(d).
  - The LLM cites Section 8(1)(d) with exact statutory quotes.
  - Pro-disclosure and pro-exemption arguments are displayed.
  - The decision logs correctly to the hash chain.
