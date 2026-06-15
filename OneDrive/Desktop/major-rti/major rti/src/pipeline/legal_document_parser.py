"""
Production-oriented legal document parser for RTI precedent documents.

The parser is deliberately local-first:
- regex for stable labels such as File No and dates table rows,
- section parsing for Facts / Grounds / Order bodies,
- optional LLM integration can be layered above this module later.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
for path in (SRC_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from models.extracted_case import ExtractedCase


DATE_RE = r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}|Not\s+on\s+Record)"
CASE_RE = re.compile(r"\b(?:CIC|SIC)[/_-][A-Z0-9]+(?:[/_-][A-Z0-9]+)*[/_-][AC][/_-]\d{4}[/_-]\d+\b", re.I)
SECTION_RE = re.compile(
    r"(?i)\b(?:Section|Sec\.?|S\.|u/s|under\s+the\s+provision\s+of)\s*"
    r"(6\s*\(\s*3\s*\)|2\s*\(\s*f\s*\)|7\s*(?:\(\s*1\s*\)|\(\s*6\s*\))?|"
    r"8\s*\(\s*1\s*\)\s*\(\s*[a-j]\s*\)|8\s*\(\s*2\s*\)|8\s*\(\s*1\s*\)|"
    r"9|10|11\s*(?:\(\s*1\s*\))?|18|19\s*(?:\(\s*1\s*\)|\(\s*3\s*\))?|20\s*(?:\(\s*1\s*\))?|24)"
)
EXEMPTION_PREFIXES = ("8(", "9", "11", "24")


class LegalDocumentParser:
    """Extract rich structured intelligence from CIC/SIC/court/circular text."""

    def parse_text(self, text: str | None, source_file: str = "", source: Optional[str] = None) -> ExtractedCase:
        clean = self._clean_text(text or "")
        sections = self._section_blocks(clean)
        parties = self._extract_parties(clean) or {}
        dates = self._extract_dates(clean)
        rti_sections = self._extract_sections(clean)
        exemption_sections = [s for s in rti_sections if self._is_exemption_section(s)]
        observations = self._extract_observations(sections.get("order", "") or clean)
        final_order = self._extract_final_order(sections.get("order", "") or clean)
        information_requested = self._extract_information_requested(sections.get("facts", "") or clean)
        outcome = self._infer_outcome(clean)
        respondent_text = parties.get("respondent") or ""
        public_authority = self._public_authority(respondent_text, clean)
        entities_by_type = self._entities_by_type(clean, parties, public_authority)
        precedent_chunk = self._build_precedent_chunk(
            information_requested=information_requested,
            observations=observations,
            final_order=final_order,
            outcome=outcome,
        )

        return ExtractedCase(
            case_number=self._case_number(clean),
            commission=self._commission(clean),
            appeal_number=self._case_number(clean),
            decision_date=self._decision_date(clean, final_order),
            hearing_date=dates.get("hearing_date"),
            commissioner_name=self._commissioner(clean),
            appellant_name=parties.get("appellant") or None,
            respondent_name=respondent_text or None,
            public_authority=public_authority,
            department=self._department(public_authority),
            cpio_name=self._cpio_name(respondent_text, clean or ""),
            faa_name=self._faa_name(clean),
            rti_application_date=dates.get("rti_application_date"),
            cpio_reply_date=dates.get("cpio_reply_date"),
            first_appeal_date=dates.get("first_appeal_date"),
            faa_order_date=dates.get("faa_order_date"),
            second_appeal_date=dates.get("second_appeal_date"),
            facts=self._compact(sections.get("facts", ""), 1800),
            information_requested=information_requested,
            grounds_for_appeal=self._compact(sections.get("grounds", ""), 1200),
            rti_request_summary=self._compact(" ".join(information_requested) or sections.get("facts", ""), 650),
            sections_invoked=rti_sections,
            rti_sections=rti_sections,
            exemption_sections=exemption_sections,
            court_references=self._court_references(clean),
            circular_references=self._circular_references(clean),
            commission_observations=observations,
            final_order=final_order,
            outcome=outcome,
            reasoning_pattern=self._reasoning_pattern(clean, outcome),
            pio_learning_signal=self._pio_learning_signal(clean, outcome),
            entities=self._entities(clean, public_authority),
            entities_person=entities_by_type["person"],
            entities_authority=entities_by_type["authority"],
            entities_department=entities_by_type["department"],
            entities_location=entities_by_type["location"],
            precedent_chunk=precedent_chunk,
            key_findings=observations[:5],
            public_interest_discussed=bool(re.search(r"(?i)larger\s+public\s+interest|public\s+interest|Section\s*8\s*\(\s*2\s*\)", clean)),
            source=source or self._source(clean),
            source_file=source_file,
            extraction_confidence=self._confidence(parties, dates, information_requested, observations, final_order),
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        text = str(text or "").replace("\x00", " ")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"<!--\s*page\s+\d+\s*-->", "\n", text, flags=re.I)
        text = re.sub(r"[ \t\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        return re.sub(r"\n{4,}", "\n\n\n", text).strip()

    @staticmethod
    def _case_number(text: str) -> str:
        match = CASE_RE.search(text)
        if match:
            return re.sub(r"[_-]+", "/", match.group(0)).upper()
        fallback = re.search(r"(?i)\bFile\s+No\.?\s*:?\s*([A-Z0-9/_-]+)", text)
        return re.sub(r"[_-]+", "/", fallback.group(1)).upper() if fallback else "UNKNOWN"

    @staticmethod
    def _commission(text: str) -> Optional[str]:
        if re.search(r"(?i)Central\s+Information\s+Commission", text):
            return "Central Information Commission"
        if re.search(r"(?i)State\s+Information\s+Commission", text):
            return "State Information Commission"
        return None

    @staticmethod
    def _source(text: str) -> str:
        if re.search(r"(?i)Central\s+Information\s+Commission|\bCIC/", text):
            return "CIC"
        if re.search(r"(?i)State\s+Information\s+Commission|\bSIC/", text):
            return "SIC"
        if re.search(r"(?i)High\s+Court|Supreme\s+Court", text):
            return "COURT"
        if re.search(r"(?i)circular|office memorandum|guidelines", text):
            return "CIRCULAR"
        return "CIC"

    def _section_blocks(self, text: str) -> dict[str, str]:
        markers = [
            ("facts", r"(?im)^\s*Facts\s*:?\s*$"),
            ("grounds", r"(?im)^\s*Grounds\s+(?:for\s+)?(?:Second\s+)?Appeal\s*:?\s*$"),
            ("order", r"(?im)^\s*(?:Order|Decision|Commission'?s\s+Findings|Observations)\s*:?\s*$"),
        ]
        found: list[tuple[str, int, int]] = []
        for name, pattern in markers:
            for match in re.finditer(pattern, text):
                found.append((name, match.start(), match.end()))
        found.sort(key=lambda item: item[1])
        blocks: dict[str, str] = {}
        for idx, (name, _start, end) in enumerate(found):
            next_start = found[idx + 1][1] if idx + 1 < len(found) else len(text)
            blocks[name] = text[end:next_start].strip(" :\n")
        return blocks

    def _extract_dates(self, text: str) -> dict[str, Optional[str]]:
        labels = {
            "rti_application_date": r"RTI\s+application",
            "cpio_reply_date": r"CPIO\s+reply",
            "first_appeal_date": r"First\s+Appeal",
            "faa_order_date": r"FAA\s+Order",
            "second_appeal_date": r"Second\s+Appeal|Complaint",
            "hearing_date": r"Date\s+of\s+hearing|Hearing\s+date",
        }
        result: dict[str, Optional[str]] = {}
        for key, label in labels.items():
            pattern = rf"(?is)(?:{label})\s*:?\s*({DATE_RE})"
            match = re.search(pattern, text)
            result[key] = self._normalize_date(match.group(1)) if match else None
        return result

    @staticmethod
    def _normalize_date(value: str) -> Optional[str]:
        value = str(value or "").strip()
        if not value or re.search(r"(?i)not\s+on\s+record", value):
            return None
        for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                continue
        return value

    @staticmethod
    def _extract_parties(text: str) -> dict[str, Optional[str]]:
        appellant = None
        respondent = None
        vs_match = re.search(r"(?is)In\s+the\s+matter\s+of:\s*(.*?)\s*\.{2,}\s*Appellant\s*Vs\.\s*(.*?)\s*\.{2,}\s*Respondent", text)
        if vs_match:
            appellant = " ".join(vs_match.group(1).split())
            respondent = " ".join(vs_match.group(2).split())
        appellant = appellant or LegalDocumentParser._label_value(text, "Appellant")
        respondent = respondent or LegalDocumentParser._label_value(text, "Respondent")
        return {"appellant": appellant, "respondent": respondent}

    @staticmethod
    def _label_value(text: str, label: str) -> Optional[str]:
        match = re.search(rf"(?im)^\s*{re.escape(label)}\s*:?\s*(.+)$", text)
        return " ".join(match.group(1).split()).strip(" .,:;") if match else None

    @staticmethod
    def _public_authority(respondent: str, text: str) -> Optional[str]:
        source = respondent or text
        patterns = [
            r"(?i)\b(?:Airport|Airports)\s+Authority\s+of\s+India\b",
            r"(?i)\b[A-Z][A-Za-z &.,()-]+(?:Department|Ministry|Authority|Commission|Corporation|Limited|Board|University)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, source)
            if match:
                return " ".join(match.group(0).split()).strip(" ,.")
        return None

    @staticmethod
    def _department(public_authority: Optional[str]) -> Optional[str]:
        if public_authority and "Department" in public_authority:
            return public_authority
        return None

    @staticmethod
    def _cpio_name(respondent: str | None, text: str | None) -> Optional[str]:
        respondent = respondent or ""
        text = text or ""
        search_text = respondent + "\n" + text[:3000]
        patterns = [
            r"(?i)Respondent\s*:\s*(Shri|Smt\.?|Ms\.?|Mr\.?|Dr\.?)\s+([^,\n]+(?:,\s*[^,\n]+)?)",
            r"(?i)(Shri|Smt\.?|Ms\.?|Mr\.?|Dr\.?)\s+[A-Z][A-Za-z .]+,\s*[^,\n]{0,80}\b(?:CPIO|PIO|APIO)\b",
            r"(?i)(Shri|Smt\.?|Ms\.?|Mr\.?|Dr\.?)\s+([^,\n]+),\s*(?:General Manager|CPIO|PIO|Nodal Officer)",
            r"(?i)\b(?:CPIO|PIO|APIO),?\s*([^,\n]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, search_text)
            if match:
                return " ".join(match.group(0).split()).strip(" ,:")
        return None

    @staticmethod
    def _faa_name(text: str) -> Optional[str]:
        match = re.search(r"(?i)First\s+Appellate\s+Authority\s*:?\s*([^\n]+)", text)
        return " ".join(match.group(1).split()).strip(" ,:") if match else None

    @staticmethod
    def _commissioner(text: str) -> Optional[str]:
        match = re.search(r"(?im)^\s*\[?([A-Z][A-Za-z .]+)\]?\s*\n\s*Information\s+Commissioner", text)
        if match:
            return " ".join(match.group(1).split()).strip(" []")
        match = re.search(r"(?i)(?:Information Commissioner|Chief Information Commissioner)\s*:?\s*([^\n]+)", text)
        return " ".join(match.group(1).split()).strip(" ,:") if match else None

    @staticmethod
    def _decision_date(text: str, final_order: Optional[str]) -> Optional[str]:
        match = re.search(rf"(?i)(?:Date\s+of\s+Decision|Decision\s+Date)\s*:?\s*({DATE_RE})", text)
        if match:
            return LegalDocumentParser._normalize_date(match.group(1))
        return None

    def _extract_information_requested(self, facts: str) -> list[str]:
        text = self._clean_inline(facts)
        if not text:
            return []
        after = re.split(r"(?i)\bsought\s+information\s+(?:on|regarding|about)\b", text, maxsplit=1)
        candidate = after[1] if len(after) > 1 else text
        candidate = re.split(r"(?i)\bGrounds\s+for\s+(?:Second\s+)?Appeal\b|\bCPIO\s+reply\b", candidate, maxsplit=1)[0]
        topic_items = self._topic_items(candidate)
        if len(topic_items) >= 2:
            return topic_items[:12]
        numbered = re.findall(r"(?:^|\s)(?:\d+[\).]|[a-z]\))\s*([^.;]+(?:[.;]|$))", candidate)
        if numbered:
            return [self._compact(item, 220).strip(" ;.") for item in numbered[:12] if item.strip()]
        sentences = re.split(r"(?<=[.!?])\s+", candidate)
        return [self._compact(s, 240).strip(" ;.") for s in sentences[:8] if len(s.split()) >= 4]

    def _topic_items(self, candidate: str) -> list[str]:
        text = self._clean_inline(candidate)
        patterns = [
            r"follow\s+up\s+of\s+[^.]{10,180}?(?:order|boundary)",
            r"prohibiting\s+any\s+construction\s+[^.]{10,180}?(?:boundary|airport)",
            r"details\s+of\s+a\s+Committee[^.]{0,180}",
            r"address\s+of\s+the\s+high\s+power\s+Committee[^.]{0,120}",
            r"whether\s+the\s+said\s+Committee\s+had\s+started\s+proceedings",
            r"whether\s+the\s+final\s+report\s+[^.]{0,120}?(?:prepared|not)",
            r"copy\s+of\s+the\s+said\s+report",
            r"Names\s+of\s+the\s+members\s+of\s+the\s+high\s+power\s+Committee[^.]{0,120}",
        ]
        items: list[str] = []
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if not match:
                continue
            value = self._compact(match.group(0), 220).strip(" ;.,")
            if value and value.lower() not in {item.lower() for item in items}:
                items.append(value)
        if items:
            return items

        split_markers = re.split(
            r"(?i)\b(?:The appellant also sought|The RTI application sought|If the final report|Names of the members)\b",
            text,
        )
        for part in split_markers:
            part = self._compact(part, 220).strip(" ;.,")
            if len(part.split()) >= 5 and part.lower() not in {item.lower() for item in items}:
                items.append(part)
        return items

    @staticmethod
    def _extract_sections(text: str) -> list[str]:
        sections: list[str] = []
        for match in SECTION_RE.finditer(text):
            section = re.sub(r"\s+", "", match.group(1))
            section = section.replace("(A)", "(a)").replace("(B)", "(b)").replace("(C)", "(c)").replace("(D)", "(d)")
            section = section.replace("(E)", "(e)").replace("(F)", "(f)").replace("(G)", "(g)").replace("(H)", "(h)")
            section = section.replace("(I)", "(i)").replace("(J)", "(j)")
            if section not in sections:
                sections.append(section)
        return sections

    @staticmethod
    def _is_exemption_section(section: str) -> bool:
        normalized = section.lower()
        return normalized.startswith(EXEMPTION_PREFIXES)

    @staticmethod
    def _court_references(text: str) -> list[str]:
        refs = re.findall(r"(?i)\b(?:Hon'?ble\s+)?(?:Supreme\s+Court|High\s+Court(?:\s+of\s+[A-Za-z]+)?|Delhi\s+High\s+Court|Bombay\s+High\s+Court|Mumbai'?s?\s+High\s+Court)\b", text)
        return list(dict.fromkeys(" ".join(ref.split()) for ref in refs))

    @staticmethod
    def _circular_references(text: str) -> list[str]:
        refs = re.findall(r"(?i)\b(?:O\.?M\.?|Office\s+Memorandum|Circular|Guideline|Notification)\s*(?:No\.?)?\s*[A-Z0-9/().-]*", text)
        return list(dict.fromkeys(" ".join(ref.split()).strip() for ref in refs if ref.strip()))

    @staticmethod
    def _extract_observations(order: str) -> list[str]:
        text = LegalDocumentParser._clean_inline(order)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        keywords = re.compile(r"(?i)\b(commission|observed|noted|perusal|reply|proper|pointwise|directed|exempt|disclos|interference|absent|penalty)\b")
        observations = []
        for sentence in sentences:
            if len(sentence.split()) >= 5 and keywords.search(sentence):
                observations.append(sentence.strip(" ."))
            if len(observations) >= 6:
                break
        return observations

    @staticmethod
    def _extract_final_order(order: str) -> Optional[str]:
        text = LegalDocumentParser._clean_inline(order)
        patterns = [
            r"(?i)(With\s+the\s+above\s+observation.*?disposed\s+of)",
            r"(?i)(The\s+(?:appeal|complaint|case)\s+is\s+disposed\s+of[^.]*\.)",
            r"(?i)(The\s+respondent\s+(?:CPIO|PIO).*?directed.*?)(?:Copies\s+of|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return LegalDocumentParser._compact(match.group(1), 650)
        return None

    @staticmethod
    def _infer_outcome(text: str) -> Optional[str]:
        lower = text.lower()
        if re.search(r"\bpenalty|show cause|section\s*20", lower):
            return "PENALTY"
        if re.search(r"partly allowed|partially allowed|redact|severance|section\s*10", lower):
            return "PARTIAL"
        if re.search(r"interference\s+of\s+the\s+commission\s+is\s+not\s+called\s+for|reply\s+(?:provided|furnished)\s+is\s+just\s+and\s+proper", lower):
            return "APPEAL_DISPOSED"
        if re.search(r"appeal\s+is\s+dismissed|complaint\s+is\s+dismissed", lower):
            return "REJECTED"
        if re.search(r"directed\s+to\s+provide|appeal\s+is\s+allowed|provide\s+revised\s+information", lower):
            return "APPEAL_ALLOWED"
        if re.search(r"disposed\s+of", lower):
            return "APPEAL_DISPOSED"
        return None

    @staticmethod
    def _reasoning_pattern(text: str, outcome: Optional[str]) -> list[str]:
        lower = text.lower()
        patterns: list[str] = []
        if "just and proper" in lower and "interference" in lower:
            patterns.append("CPIO reply accepted as just and proper")
            patterns.append("No Commission interference required")
        if "pointwise" in lower:
            patterns.append("Pointwise reply considered adequate")
        if "appellant was not present" in lower or "appellant : absent" in lower:
            patterns.append("Appellant absent or did not contest at hearing")
        if "not provided" in lower and "directed to provide" in lower:
            patterns.append("Information not adequately provided; revised reply directed")
        if "8(1)(j)" in lower:
            patterns.append("Personal information/privacy exemption analysis")
        if "6(3)" in lower:
            patterns.append("Record custody / transfer consideration")
        if outcome:
            patterns.append(outcome.replace("_", " ").title())
        return list(dict.fromkeys(patterns))

    @staticmethod
    def _pio_learning_signal(text: str, outcome: Optional[str]) -> Optional[str]:
        lower = text.lower()
        if "just and proper" in lower and "pointwise" in lower:
            return "Pointwise and reasoned CPIO replies are more likely to be upheld."
        if "directed to provide" in lower:
            return "Incomplete replies can lead to direction for revised pointwise disclosure."
        if "not called for" in lower:
            return "Commission may decline intervention when reply is proper and appellant does not contest."
        return "PIO should verify record custody, statutory exemptions, and provide a reasoned reply."

    @staticmethod
    def _entities(text: str, public_authority: Optional[str]) -> list[str]:
        entities = []
        if public_authority:
            entities.append(public_authority)
        for pattern in (r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b", r"\b[A-Z][A-Za-z]+\s+Airport\b", r"\bMumbai\b|\bDelhi\b|\bMaharashtra\b|\bNew Delhi\b"):
            for match in re.finditer(pattern, text[:5000]):
                value = " ".join(match.group(0).split())
                if value not in entities and len(value) <= 80:
                    entities.append(value)
                if len(entities) >= 20:
                    return entities
        return entities

    @staticmethod
    def _entities_by_type(text: str, parties: dict[str, Optional[str]], public_authority: Optional[str]) -> dict[str, list[str]]:
        people: list[str] = []
        authority: list[str] = []
        departments: list[str] = []
        locations: list[str] = []

        for value in (parties.get("appellant"),):
            if value:
                people.append(value)
        for match in re.finditer(r"(?i)\b(?:Shri|Smt\.?|Ms\.?|Mr\.?|Dr\.?)\s+[A-Z][A-Za-z .]{2,60}", text[:5000]):
            value = " ".join(match.group(0).split()).strip(" ,.")
            if value not in people:
                people.append(value)

        if public_authority:
            authority.append(public_authority)
        for match in re.finditer(r"\b[A-Z][A-Za-z &.,()-]+(?:Authority|Commission|Corporation|Board|University|Limited)\b", text[:6000]):
            value = " ".join(match.group(0).split()).strip(" ,.")
            if value not in authority:
                authority.append(value)

        for match in re.finditer(r"\b[A-Z][A-Za-z &.,()-]+(?:Department|Ministry)\b", text[:6000]):
            value = " ".join(match.group(0).split()).strip(" ,.")
            if value not in departments:
                departments.append(value)

        for match in re.finditer(r"\b(?:Mumbai|Delhi|New Delhi|Maharashtra|Chhattisgarh|Raipur|Bhopal|Kolkata|Chennai|Bengaluru|Hyderabad)\b", text[:8000]):
            value = match.group(0)
            if value not in locations:
                locations.append(value)

        return {
            "person": people[:12],
            "authority": authority[:12],
            "department": departments[:12],
            "location": locations[:12],
        }

    @staticmethod
    def _build_precedent_chunk(
        information_requested: list[str],
        observations: list[str],
        final_order: Optional[str],
        outcome: Optional[str],
    ) -> Optional[str]:
        parts = []
        if information_requested:
            parts.append("Applicant sought " + "; ".join(information_requested[:4]))
        if observations:
            priority = [
                item for item in observations
                if re.search(r"(?i)just\s+and\s+proper|pointwise|interference|directed|disclosed|exempt", item)
            ]
            selected = list(dict.fromkeys(priority + observations))[:4]
            parts.append("Commission observed " + "; ".join(selected))
        if final_order:
            parts.append("Final order: " + final_order)
        if outcome:
            parts.append("Outcome: " + outcome)
        return LegalDocumentParser._compact(". ".join(parts), 1200) if parts else None

    @staticmethod
    def _clean_inline(text: str) -> str:
        return " ".join(str(text or "").split())

    @staticmethod
    def _compact(text: str, limit: int) -> str:
        text = LegalDocumentParser._clean_inline(text)
        return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _confidence(parties: dict[str, Optional[str]], dates: dict[str, Optional[str]], info: list[str], obs: list[str], final_order: Optional[str]) -> float:
        score = 0.25
        if parties.get("appellant"):
            score += 0.12
        if parties.get("respondent"):
            score += 0.12
        if any(dates.values()):
            score += 0.18
        if info:
            score += 0.15
        if obs:
            score += 0.15
        if final_order:
            score += 0.10
        return round(min(score, 0.97), 3)


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse one CIC/SIC/court/circular text file into structured JSON.")
    parser.add_argument("--text-file", required=True, help="Path to extracted .txt file.")
    parser.add_argument("--source", default=None, help="Optional source type override: CIC, SIC, COURT, CIRCULAR.")
    args = parser.parse_args()

    text_path = Path(args.text_file)
    parsed = LegalDocumentParser().parse_text(
        text_path.read_text(encoding="utf-8", errors="replace"),
        source_file=str(text_path),
        source=args.source,
    )
    print(parsed.model_dump_json(indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
