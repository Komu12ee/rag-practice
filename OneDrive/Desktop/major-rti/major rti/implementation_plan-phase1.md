# Phase 1 Implementation Plan: Exemption Flagging

Based on the architectural directives for Week 2, Phase 1 focuses on building the **Information Extractor (Agent 2)**, the **Rule-Based Exemption Engine (Agent 3 - Layer A)**, and the **PIO Annotation UI**. 

This phase will *not* yet implement the LLM-based exemption analysis or legal corpus RAG (which are slated for Phase 2), ensuring we build a legally robust deterministic foundation first.

## User Review Required
> [!WARNING]
> **Legal-Consequential Interruption**
> The architecture specifies that the Information Extractor's output determines which Section 8 exemptions are evaluated. A misclassification here cascades into wrong legal advice. Therefore, the UI must force a hard stop: the PIO must manually review and confirm the extracted entities and information classification *before* the rule engine evaluates exemptions. Please confirm this UX flow is acceptable.

## Open Questions
> [!IMPORTANT]
> 1. **Database Schema Update**: The current `audit_trail` table does not have columns for exemption analysis. I plan to use SQLite `ALTER TABLE ADD COLUMN` or recreate the table (if in dev mode) to add fields like `information_type`, `rule_engine_flags`, and `pio_exemption_decision`. Is it acceptable to recreate the database for this MVP phase, or must I write a migration script?
> 2. **LLM for Extraction**: I plan to use the local Ollama `qwen2.5:3b` model to perform the structured JSON extraction for Agent 2. Is this model acceptable, or do you want to switch to a different local model?

## Proposed Changes

### 1. `db.py` (Database Schema)
Update the `AuditRecord` Pydantic model and SQLite schema to capture Phase 1 data:
- `extracted_entities` (JSON list)
- `information_type` (String enum: citizen data / internal / confidential / architecture / procurement / employee / cybersecurity)
- `rule_engine_flags` (JSON list of triggered Section 8/11 flags)
- `pio_exemption_override` (String)

### 2. `extractor.py` [NEW] (Agent 2)
Create a new module to handle LLM structured extraction.
- Define Pydantic schema for Information Extraction (entities: people, systems, dates, doc numbers; info_type).
- Use Ollama to parse the RTI text and output strict JSON matching the schema.
- Implement robust error handling for hallucinated fields.

### 3. `exemption_rules.py` [NEW] (Agent 3 - Layer A)
Create the deterministic rule engine based on the architectural matrix:
- **Section 11**: Triggered if `information_type == 'third_party_commercial'`
- **Section 8(1)(a)**: Triggered if `systems` contain security keywords or `info_type == 'cybersecurity'`
- **Section 8(1)(d)**: Triggered if `procurement_status == 'active_tender'`
- **Section 8(1)(j)**: Triggered if `personal_data == True`
- **Section 8(2) Override**: Check for corruption/human rights allegations to override 8(1) flags.

### 4. `app.py` (Streamlit UI Updates)
- Add a multi-step wizard UI or expanding expanders.
- **Step 1**: OCR & Routing (Existing).
- **Step 2**: Information Extraction. Display extracted fields and require PIO to click "Confirm Extraction" before proceeding.
- **Step 3**: Exemption Flags. Display deterministic rule triggers.
- **Annotation UI**: Add forms for the PIO to log their actual decision (for future fine-tuning data collection).

## Verification Plan
### Automated Tests
- Create `verify_extraction.py` to benchmark Agent 2 against a set of complex/ambiguous RTI texts, measuring JSON schema compliance and classification accuracy.

### Manual Verification
- Run the dashboard, upload a sample RTI containing personal data and an active tender, verify it forces manual PIO confirmation of the extraction, and properly flags Section 8(1)(j) and 8(1)(d).
