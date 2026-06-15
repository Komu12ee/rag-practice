# RTI Intelligence System — React Frontend Implementation Plan
**For: CHiPS PIO Officer Dashboard, Chhattisgarh**
**Audience: 1–2 government PIO officers. Not technical users.**
**Design directive: Looks like an official government tool, not an AI product.**

---

## Design Philosophy: What This Must Feel Like

This is a **decision-support register** — the mental model is closer to a government file noting system or a court docket than a SaaS dashboard. Every screen should feel like a printed form that happens to be digital: structured, labelled, quiet, authoritative.

**What to avoid entirely:**
- Glowing gradients on data fields
- Animated card entrances / shimmer loaders
- Emoji overload (max 1 emoji per section header, none inside data rows)
- "AI" language in the UI copy (no "Smart", "Intelligent", "Powered by AI")
- Dark glassmorphism cards that look like a crypto dashboard

**What to aim for:**
- Generous whitespace, clear label-above-value hierarchy
- A muted navy/slate colour palette with one functional accent (amber for warnings, green for approve, red for reject)
- Dense-but-readable: think a well-designed government gazette or legal form
- Every interactive element does exactly one thing and is labelled in plain Hindi-English that a non-technical officer can read without training

---

## Token System

```
COLOUR
  --surface-0:   #F7F8FA   (page background, light mode)
  --surface-1:   #FFFFFF   (card background)
  --surface-2:   #EEF0F4   (input background, table stripe)
  --border:      #D1D5DB   (all borders)
  --text-primary:#111827   (headings, values)
  --text-label:  #6B7280   (field labels, captions)
  --accent-navy: #1E3A5F   (header bar, primary buttons)
  --accent-amber:#B45309   (warnings, override state)
  --status-green:#15803D   (approve)
  --status-red:  #B91C1C   (reject)
  --status-grey: #6B7280   (pending)

  DARK MODE (toggle)
  --surface-0:   #0D1117
  --surface-1:   #161B22
  --surface-2:   #21262D
  --border:      #30363D
  --text-primary:#E6EDF3
  --text-label:  #8B949E
  --accent-navy: #388BFD   (becomes blue accent in dark)

TYPOGRAPHY
  Display/Headers: "DM Sans" 600–700  (clean, institutional, not techy)
  Body/Labels:     "Inter" 400–500
  Monospace (IDs, hashes): "JetBrains Mono" 400

  Scale:
    page-title:  24px / 700
    section-hd:  16px / 600, letter-spacing: 0.02em, UPPERCASE
    field-label: 11px / 500, UPPERCASE, color: --text-label
    field-value: 14px / 400, color: --text-primary
    caption:     12px / 400, color: --text-label

SPACING (8px grid)
  Card padding:  24px
  Row gap:       16px
  Section gap:   32px
  Border-radius: 6px (cards), 4px (badges), 2px (inputs)
  — No large border-radius. Rounded corners look app-like; sharp corners look official.

SIGNATURE ELEMENT
  A left-border accent stripe on active/flagged cards (4px solid --accent-amber or --status-red).
  This is the only visual "alert" mechanism — no pulsing, no glow. Just the stripe.
```

---

## Implementation Plan by Component

---

### PHASE 1 — App Shell (Do First)

#### `App.tsx` — Header + Navigation + Shell

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  [GOV LOGO]  RTI Intelligence System — CHiPS    [●DB][●LLM]  [☀/🌙]  │
├──────────────────────────────────────────────────────│
│  [Analysis] [RTI Reference] [Audit Trail●3] [Status] │  ← Tab bar
├──────────────────────────────────────────────────────│
│  Case: RTI/CHiPS/2026/A1267B6B   09 Jun 2026   [New Case]            │
└──────────────────────────────────────────────────────┘
```

**Rules:**
- Header bar: `--accent-navy` background, white text. No gradient.
- Tab bar: plain white/surface-0 background, bottom-border indicator for active tab (3px --accent-navy). No pill tabs.
- Case ID row: small secondary bar, monospace font, subtle surface-2 background.
- DB/LLM status: two small dots with text — "● DB" / "● LLM" — in header top-right. Green dot = online, red = offline. No label on mobile.
- Theme toggle: a single icon button (sun/moon). No animation on toggle.
- "New Case" button: outlined, not filled. Clicking shows a simple confirm dialog: "Start a new case? Current analysis will be cleared." with Confirm / Cancel.
- Pending badge on Audit Trail tab: a small red number badge if records with PENDING status exist. Fetch on mount from `/api/audit_trail?limit=200`.

**Copy rules:**
- Tab labels: "New Analysis" / "RTI Act" / "Audit Trail" / "System"
- No subtitle text in the header bar — the title alone is enough.

---

### PHASE 2 — New Analysis Flow (Highest Priority)

The entire analysis flow is a **3-step linear wizard**. The step indicator is the primary navigation mechanism for this page.

#### Step Indicator Component

```
Step 1: Input & Routing  ──►  Step 2: Review Parameters  ──►  Step 3: Decision
     ✅ Complete                    ● Active                         ○ Pending
```

**Rules:**
- Horizontal bar, full width. Steps connected by a line.
- Completed: checkmark + navy text. Active: bold + navy underline. Pending: grey.
- NO sticky positioning — it scrolls naturally. Sticky adds complexity and obscures content.
- Do not animate step transitions. Just re-render.

---

#### Step 1 — Input & Routing (`InputStep.tsx`)

**Layout:**
```
┌─ RTI Application Input ──────────────────────────────┐
│  ○ Paste Text   ○ Upload File                        │
│                                                      │
│  [                                                 ] │
│  [         Text area / File drop zone              ] │
│  [                                                 ] │
│                                        [Analyse →]   │
└──────────────────────────────────────────────────────┘
```

**Rules:**
- Two radio options at top. One visible input below (swap on toggle).
- File drop zone: dashed border, "Drop PDF, DOCX, or image here, or click to browse". No icons beyond that.
- "Analyse" button: filled, `--accent-navy`, right-aligned.
- While loading: replace button with a plain spinner + "Analysing…" text. No progress bars, no step-by-step toast messages.
- Legal Notice Banner (see `LegalBanner.tsx` below): appears ABOVE the input card, dismissible.

---

#### `LegalBanner.tsx`

**Full state:**
```
┌─ ⚠ Legal Notice ──────────────────────────────── [✓ Understood] ┐
│  This system generates advisory recommendations only. All        │
│  routing and disclosure decisions remain the PIO's sole          │
│  responsibility under RTI Act 2005, Section 5.                   │
└──────────────────────────────────────────────────────────────────┘
```
- Amber left-border stripe (4px). No red. Red = error; this is a notice.
- "✓ Understood" button collapses it to a one-line strip.

**Dismissed state:**
```
┌─ ⚠ Advisory system — all decisions are the PIO's legal responsibility ──────┐
```
- Single line, surface-2 background, amber text. Always visible but unobtrusive.
- Store dismissal in `localStorage` key `rti_banner_dismissed` so it persists across sessions.

---

#### Step 2 — Review & Routing (`ReviewStep.tsx`)

This is the most complex step. Decompose into sub-sections rendered in this order:

**2A — Recommended Department Card**
```
┌─ RECOMMENDED DEPARTMENT ──────────────────── ● Strong Evidence ─┐
│  Ministry of Information Technology (CHiPS)                      │
│  मानक इन्टरनेट प्रोटोकॉल कार्यालय                              │
│                                                                  │
│  ▶ View Routing Reasoning  (collapsed by default)                │
│  ▶ View Alternative Departments  (collapsed by default)          │
│  ▶ View Extracted Text  (collapsed by default)                   │
└──────────────────────────────────────────────────────────────────┘
```
- Department name: 20px/700, navy.
- Confidence badge: small pill, top-right. Green = Strong Evidence, Amber = Moderate, Red = Low.
- Three collapsibles below. All closed by default. Use `<details><summary>` with CSS chevron.

**Routing Reasoning (inside collapsible):**
- Each step on its own row: `[icon] Step label: value`
- Alternating surface-0/surface-2 rows. NO colored cards per step — that's the noise to eliminate.
- The emoji icon is enough to differentiate step types. No coloured backgrounds per step.

**Alternative Departments (inside collapsible):**
- A simple table: Department | Score | Reason
- `<table>` with `border-collapse: collapse`, 1px --border rows. No card per department.

**OCR Status:**
- One line below the department card:  `✓ OCR: Good (94%)` in green, or `⚠ OCR: Low (61%) — verify extracted text` in amber.
- No separate banner for this. It's a status line, not a warning box.

---

**2B — Routing Verification**
```
┌─ ROUTING VERIFICATION ───────────────────────────────────────────┐
│  Is this routing correct?                                        │
│                                                                  │
│  [✓ Confirm AI Routing]        [✎ Override Department]           │
└──────────────────────────────────────────────────────────────────┘
```
- Two equal-width buttons. Confirm = green outlined → fills green on click. Override = amber outlined → fills amber on click.
- When Override is selected, expand below (not a modal, inline):
```
│  Correct Department: [dropdown ▾]                                │
│  Reason for correction:                                          │
│  [                                                             ] │
```
- No warning text. The amber button colour is the signal.

---

**2C — Parameter Review (Modal Dialog)**

Triggered by a single button: `[🔍 Review & Confirm Extracted Parameters]` — amber, full-width, below the routing section.

**The modal:**
```
┌─ Review Extracted Parameters ──────────── [✕] ─┐
│                                                 │
│  CLASSIFICATION                                 │
│  Information Type   [OTHER          ▾]          │
│  Procurement Status [None           ▾]          │
│                                                 │
│  ENTITIES & SYSTEMS                             │
│  Key Entities                                   │
│  [Suresh Kumar Makam, Shridhar Diwan…         ] │
│  IT Systems Mentioned                           │
│  [                                            ] │
│                                                 │
│  RISK FLAGS                                     │
│  ☑ Contains personal private information        │
│  ☐ Contains corruption / HR violations          │
│                                                 │
│  Explanation                                    │
│  [General public information query…           ] │
│                                                 │
│  [Cancel]                [✓ Confirm & Continue →]│
└─────────────────────────────────────────────────┘
```
- Use a real `<dialog>` element (native HTML) with `showModal()` / `close()`. No library needed.
- Backdrop: `rgba(0,0,0,0.4)`. No blur.
- Section headers inside modal: 11px UPPERCASE labels, same as field labels.
- After confirm: show a summary strip between the amber button and the "Next Step" button:
  `Type: OTHER  ·  Personal Data: Yes  ·  Procurement: None`
  In surface-2, 12px, monospace-ish.

**After both routing and parameters are confirmed:**
Show one primary button at bottom of page: `[Continue to Exemption Analysis →]` — navy, right-aligned.

---

### PHASE 3 — Exemption Analysis & Decision (`ExemptionStep.tsx`)

**Layout (top to bottom):**

1. **Synthesized Recommendation Card** — always visible, at the top
2. Confirmed Parameters — collapsible, closed by default
3. Deterministic Exemption Flags — collapsible, closed by default
4. Target Jurisdiction — collapsible, closed by default
5. Adversarial Balancer — collapsible, closed by default
6. PIO Decision Form — always visible, at the bottom

---

**Synthesized Recommendation Card:**
```
┌─ AI RECOMMENDATION ─────────────────────── ● Strong Evidence ──┐
│                                                                  │
│  APPROVE — DISCLOSE ENTIRE RECORD                                │
│                                                                  │
│  The request seeks aggregate statistical data, not personal      │
│  information. Section 8(1)(j) is inapplicable. Public interest  │
│  in transparency outweighs speculative security concerns.        │
│                                                                  │
│  Suggested action: Disclose within 30 days under Section 7(1).  │
│                                                                  │
│  Statutory Citations: None triggered                             │
└──────────────────────────────────────────────────────────────────┘
```
- APPROVE: green left-border stripe + green heading. REJECT: red. PARTIAL: amber.
- Recommendation text: 20px/700. Plain, no gradient text effect.
- "Suggested action" row: italic, smaller, below a thin divider line.

---

**Deterministic Exemption Flags (collapsible):**
- Each flag: one row. `Section 8(1)(j) — Personal Information & Privacy` + `FLAGGED` badge on right.
- FLAGGED = red badge. NOT APPLICABLE = green badge.
- Below each flagged section: the reasoning + recommended action in plain text, indented.

---

**Adversarial Disclosure Balancer (collapsible):**

Add a single tilt line ABOVE the collapsible toggle:
`Balance assessment: Tilts toward disclosure` (green) or `Tilts toward exemption` (amber).

Inside the collapsible:
```
┌─ Legal Case for Disclosure ──┐  ┌─ Legal Case for Exemption ─┐
│  [paragraph text]            │  │  [paragraph text]           │
│                              │  │                             │
│  REFUSAL / REJECTION RISK    │  │  DISCLOSURE / LEAKAGE RISK  │
│  [risk text]                 │  │  [risk text]                │
└──────────────────────────────┘  └─────────────────────────────┘

KEY BALANCING FACTORS
[paragraph]
```
- Two columns, equal width, with a vertical divider between.
- Section labels (REFUSAL / REJECTION RISK): 11px uppercase, amber for risk items.
- No decorative lock/unlock icons. The text is sufficient.

---

**PIO Decision Form (`PIOLogForm.tsx`):**

```
┌─ PIO DECISION ────────────────────────────────────────────────────┐
│                                                                   │
│  Final Decision                                                   │
│  [Approve ▾]   (options: Approve / Partially Approve /           │
│                 Reject / Transfer / Pending)                      │
│                                                                   │
│  Decision Notes / Order Sheet Text                                │
│  [                                                              ] │
│  [                                                              ] │
│  [✎ Generate Draft from AI Analysis]  (small, secondary button)  │
│  ⚠ AI-Generated Draft — review before finalising  (if used)      │
│                                                                   │
│  ☐ I confirm I have reviewed this recommendation and accept       │
│    full legal responsibility for this decision under RTI Act 2005 │
│                                                                   │
│                               [Submit & Finalise Decision →]      │
└───────────────────────────────────────────────────────────────────┘
```
- "Generate Draft" = small text-style button (not a primary CTA).
- AI Draft warning: amber, 12px, appears inline below the textarea after draft is loaded.
- The legal responsibility checkbox MUST be checked before Submit is enabled. If unchecked and Submit is clicked, show an inline error: "You must accept legal responsibility before submitting."
- Submit button: navy, disabled state = greyed out. No tooltip needed.

---

### PHASE 4 — Audit Trail (`AuditTrailView.tsx`)

**Layout:**
```
┌─ AUDIT TRAIL ─────────────────────────────────────────────────────┐
│  [Total: 24] [Approved: 18] [Overridden: 4] [Override Rate: 17%]  │
├───────────────────────────────────────────────────────────────────┤
│  🔍 [Search…]   Action[▾]   Dept[▾]   Confidence[▾]   Date[▾]    │
│  Sort: [Newest First ▾]        Showing 24 of 24    [Export CSV]   │
├───────────────────────────────────────────────────────────────────┤
│  ● 09 Jun 2026  RTI/CHiPS/2026/A1267B6B  CHiPS  APPROVED          │
│    ▶ (expand for full detail)                                     │
│  ● 08 Jun 2026  RTI/CHiPS/2026/B9F3A2C1  Revenue  OVERRIDDEN      │
│    ▶                                                              │
└───────────────────────────────────────────────────────────────────┘
```

**Metric cards:** Four inline stat boxes — plain numbers, no gradient text. Label above, value below.

**Filter row:** All in one horizontal row. Use `<select>` elements — no custom dropdowns. Native selects look more official and are faster to use.

**Record rows:**
- Each record = one `<details>` row with `<summary>` containing: coloured status dot + date + case ID + department + action badge.
- Status dot colours: green = APPROVED, amber = OVERRIDDEN, red = REJECTED, grey = PENDING.
- Inside expanded `<details>`: a two-column layout — left: routing/classification details; right: hash + OCR confidence + language + override info.
- No cards inside the expanded row. Just labelled rows (`field-label` above `field-value`).

**CSV Export:** `[Export CSV]` button top-right of filter row. Exports the currently filtered set. No modal, just trigger a download.

---

### PHASE 5 — RTI Act Reference (`RTIReferenceView.tsx`)

```
┌─ RTI ACT REFERENCE ───────────────────────────────────────────────┐
│  🔍 [Search sections…]                                            │
├───────────────────────────────────────────────────────────────────┤
│  MODULE: Exemptions                                               │
│  ▶ Section 8(1)(a) — Sovereignty & Security                       │
│  ▶ Section 8(1)(d) — Commercial Confidence                        │
│  ▶ Section 8(1)(j) — Personal Information & Privacy               │
│                                                                   │
│  MODULE: Disclosure Obligations                                   │
│  ▶ Section 4 — Proactive Disclosure                               │
└───────────────────────────────────────────────────────────────────┘
```

Inside each expanded section:
- Left column (60%): Definition / Legal Text + Practical Implication
- Right column (40%): CHiPS-Specific Note (if any) + Common Mistakes (if any)
- Source reference: caption at bottom right.

No cards. Use a thin top-border `1px solid --border` to separate sections within a module. Module header = 11px uppercase label with a grey background strip.

---

### PHASE 6 — System Status (`SystemStatusView.tsx`)

Simple table layout:

```
COMPONENT HEALTH
Component                     Status    Description
──────────────────────────────────────────────────
Database (SQLite)             ● Online  Immutable audit trail storage
OCR Engine                    ● Online  PDF/image text extraction
Routing Engine                ● Online  Department jurisdiction classifier

LLM MODELS (Ollama)
qwen2.5:3b                    ● Online  3.1 GB

ARCHITECTURE PRINCIPLES
1. Human Final Decision        PIO must accept legal responsibility before any decision.
2. Immutable Audit Trail       Append-only, hash-chained log. No deletions ever.
...
```

Use an HTML `<table>` for component health. Status = coloured dot + text. No cards.

---

### PHASE 7 — Light/Dark Mode

- Toggle in header bar, top-right: sun icon (light) / moon icon (dark).
- Store in `localStorage` key `rti_theme`.
- Implement via a `data-theme="light"|"dark"` attribute on `<html>`.
- All CSS uses `var(--token)` — no hardcoded colours anywhere in component files.
- In `globals.css`:
  ```css
  :root { /* light defaults */ }
  [data-theme="dark"] { /* dark overrides */ }
  ```
- Default: dark (match current Streamlit). On first visit with no stored preference → dark.

---

## Component File Map

```
src/
├── globals.css                  ← all CSS tokens, dark/light, base elements
├── App.tsx                      ← shell, tabs, header, case ID, theme toggle
├── components/
│   ├── LegalBanner.tsx
│   ├── StepIndicator.tsx
│   ├── ReasoningSteps.tsx       ← pipe-separated steps formatter
│   ├── ConfirmedParamsCard.tsx
│   ├── BalancerGrid.tsx
│   ├── StatutoryCard.tsx
│   ├── ui/
│   │   └── Collapsible.tsx      ← <details>/<summary> wrapper
│   └── steps/
│       ├── InputStep.tsx
│       ├── ReviewStep.tsx       ← includes ParameterDialog (native <dialog>)
│       ├── ExemptionStep.tsx
│       └── CompletedStep.tsx
├── components/views/
│   ├── AuditTrailView.tsx
│   ├── RTIReferenceView.tsx
│   └── SystemStatusView.tsx
├── components/PIOLogForm.tsx
└── lib/
    ├── api.ts                   ← all fetch calls
    └── types.ts                 ← all interfaces
```

---

## Critical Copy Rules (Apply Throughout)

| Instead of | Use |
|---|---|
| "AI Recommendation" | "System Recommendation" |
| "Powered by AI" | (remove entirely) |
| "Smart Analysis" | "Analysis" |
| "✅ Confirm & Run Exemption Rules" | "Confirm & Continue" |
| "LEGAL-CONSEQUENTIAL INTERRUPTION" | "Review Extracted Parameters" |
| "Adversarial Disclosure Balancer" | "Disclosure Balance Analysis" |
| "Layer B Statutory Analysis" | "Statutory Exemption Review" |
| "Autofield" | "Generate Draft" |
| Long warning paragraphs in badges | One sentence, plain English |

---

## What to Build First (Priority Order)

1. `globals.css` — token system, light/dark. Everything else depends on this.
2. `App.tsx` — shell, tabs, header, theme toggle, case ID.
3. `InputStep.tsx` + `LegalBanner.tsx` — users hit this first.
4. `ReviewStep.tsx` + `ReasoningSteps.tsx` + `Collapsible.tsx` — most complex step.
5. `ExemptionStep.tsx` + `BalancerGrid.tsx` + `PIOLogForm.tsx` — core decision point.
6. `AuditTrailView.tsx` — second-most-used page.
7. `RTIReferenceView.tsx`
8. `SystemStatusView.tsx`
9. `CompletedStep.tsx` — export buttons.
10. `api.ts` extensions + `types.ts` additions — thread through as each component is built.

---

## Open Questions (Resolved)

| Question | Decision |
|---|---|
| RTI Reference data source | Fetch from `GET /api/legal_sections` (backend serves JSON). Do not bundle in React build — data may be updated without a frontend deploy. |
| Autofield Draft API | Expose via `POST /api/generate_draft`. Keep the feature; just rename it "Generate Draft" in the UI. |
| Case ID generation | Client-side, matching current format `RTI/CHiPS/{year}/{uuid8}`. Store in `useState` + `sessionStorage`. Reset on "New Case". |
| Sticky step indicator | No. Scrolls naturally. Sticky adds layout complexity and obscures content on small screens. |
| Custom dropdown components | No. Use native `<select>`. Faster, accessible, and looks more official than styled dropdowns. |
| Animation | None, except a single CSS `transition: height 0.2s ease` on collapsible sections. |
