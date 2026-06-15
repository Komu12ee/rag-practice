import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Define audit log directory absolute path (project_root/audit_log)
AUDIT_BASE_DIR = Path(__file__).resolve().parent.parent / 'audit_log'


def _get_case_file(case_id: str) -> Path:
    date_dir = AUDIT_BASE_DIR / datetime.now().strftime('%Y-%m-%d')
    date_dir.mkdir(parents=True, exist_ok=True)
    # Sanitize case_id for filename
    safe_case_id = case_id.replace('/', '_').replace('\\', '_')
    return date_dir / f'{safe_case_id}.json'


def _load_case(case_id: str) -> dict:
    path = _get_case_file(case_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'case_id': case_id, 'created_at': datetime.now().isoformat(), 'events': []}


def _save_case(case_id: str, data: dict):
    """Append-only: never removes events already stored."""
    path = _get_case_file(case_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _append_event(case_id: str, event_type: str, payload: Dict[str, Any]):
    case = _load_case(case_id)
    event = {
        'event_type': event_type,
        'timestamp': datetime.now().isoformat(),
        'payload': payload
    }
    # Hash the payload for integrity verification
    event['hash'] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]
    case['events'].append(event)
    _save_case(case_id, case)


# Public API — one function per event type

def log_rti_input(case_id: str, rti_text: str, source_type: str, ocr_confidence: float, language: str):
    _append_event(case_id, 'RTI_INPUT', {
        'rti_text_preview': rti_text[:500],
        'rti_text_length': len(rti_text),
        'source_type': source_type,
        'ocr_confidence': ocr_confidence,
        'language_detected': language
    })


def log_routing_decision(case_id: str, ai_prediction: str, pio_override: Optional[str],
                         correction_reason: str, effective_department: str, is_chips: bool):
    _append_event(case_id, 'ROUTING_DECISION', {
        'ai_prediction': ai_prediction,
        'pio_override': pio_override,
        'override_reason': correction_reason,
        'effective_department': effective_department,
        'is_chips_jurisdiction': is_chips,
        'training_data_flag': pio_override is not None  # Flag for future training
    })


def log_exemption_analysis(case_id: str, ai_analysis: dict, sections_applied: list):
    _append_event(case_id, 'EXEMPTION_ANALYSIS', {
        'ai_analysis_summary': ai_analysis,
        'sections_applied': sections_applied
    })


def log_pio_decision(case_id: str, ai_draft: str, pio_edited_text: str,
                     final_decision: str, pio_notes: str):
    """
    CRITICAL: Stores all 3 versions separately.
    ai_draft: what the LLM generated
    pio_edited_text: what the PIO typed / edited before finalizing
    final_decision: the confirmed final decision
    """
    _append_event(case_id, 'PIO_DECISION', {
        'ai_draft_original': ai_draft,
        'pio_edited_version': pio_edited_text,
        'final_approved_decision': final_decision,
        'pio_notes': pio_notes,
        'was_ai_draft_modified': ai_draft.strip() != pio_edited_text.strip()
    })


def log_response_letter_generated(case_id: str, letter_text: str, export_format: str):
    _append_event(case_id, 'RESPONSE_LETTER_GENERATED', {
        'letter_preview': letter_text[:500],
        'export_format': export_format,
        'generated_at': datetime.now().isoformat()
    })


def export_training_data(output_path: Optional[str] = None):
    """
    Exports all PIO corrections as JSONL for future model fine-tuning.
    Only exports events where pio_override is not None (actual corrections).
    """
    if output_path is None:
        output_path = str(AUDIT_BASE_DIR.parent / 'training_data' / 'corrections.jsonl')
    
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    
    if not AUDIT_BASE_DIR.exists():
        return 0
        
    for date_dir in sorted(AUDIT_BASE_DIR.iterdir()):
        if not date_dir.is_dir():
            continue
        for case_file in date_dir.glob('*.json'):
            try:
                case = json.loads(case_file.read_text(encoding='utf-8'))
            except Exception:
                continue
            events = case.get('events', [])
            routing_events = [e for e in events if e.get('event_type') == 'ROUTING_DECISION']
            pio_events = [e for e in events if e.get('event_type') == 'PIO_DECISION']
            input_events = [e for e in events if e.get('event_type') == 'RTI_INPUT']
            
            if routing_events and routing_events[0].get('payload', {}).get('training_data_flag'):
                record = {
                    'case_id': case.get('case_id'),
                    'rti_text_preview': input_events[0]['payload']['rti_text_preview'] if input_events else '',
                    'ai_routing': routing_events[0]['payload']['ai_prediction'],
                    'correct_routing': routing_events[0]['payload']['effective_department'],
                    'correction_reason': routing_events[0]['payload']['override_reason'],
                    'pio_final_decision': pio_events[0]['payload']['final_approved_decision'] if pio_events else '',
                }
                records.append(json.dumps(record, ensure_ascii=False))
                
    if records:
        out_path.write_text('\n'.join(records), encoding='utf-8')
    return len(records)
