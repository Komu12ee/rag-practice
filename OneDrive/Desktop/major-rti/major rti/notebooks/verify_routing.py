
import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
"""
RTI Intelligence System — Routing Verification Script
=======================================================
Automated benchmark to test department routing accuracy
against the sample RTI dataset.

Usage:
    C:\\Users\\hp\\anaconda3\\python.exe verify_routing.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')


def load_sample_rtis() -> list[dict]:
    """Load the sample RTI test dataset."""
    path = Path(__file__).resolve().parent.parent / "data" / "sample_rtis.json"
    if not path.exists():
        print(f"ERROR: Sample RTIs not found at {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_benchmark():
    """Run the routing accuracy benchmark."""
    print("=" * 70)
    print("RTI Intelligence System — Routing Accuracy Benchmark")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    # Import routing module
    try:
        from routing import classify_department
    except ImportError as e:
        print(f"\nERROR: Could not import routing module: {e}")
        print("Ensure routing.py is in the same directory.")
        sys.exit(1)

    # Load test data
    samples = load_sample_rtis()
    print(f"\nLoaded {len(samples)} test RTI applications.\n")

    # Run tests
    results = []
    correct = 0
    total = len(samples)
    hindi_correct = 0
    hindi_total = 0
    english_correct = 0
    english_total = 0

    for i, sample in enumerate(samples):
        rti_text = sample["text"]
        expected = sample["expected_department"]
        language = sample.get("language", "en")
        notes = sample.get("notes", "")

        print(f"--- Test {i+1}/{total} ---")
        print(f"  Language: {language}")
        print(f"  Expected: {expected}")
        print(f"  Text: {rti_text[:80]}...")

        try:
            result = classify_department(rti_text, language)
            predicted = result.primary_department
            confidence = result.confidence_band
            is_correct = predicted == expected

            # Check if expected dept is in alternatives
            alt_match = False
            if not is_correct and result.alternative_departments:
                alt_depts = [a.department_id if hasattr(a, 'department_id') else a.get("department", "") for a in result.alternative_departments]
                if expected in alt_depts:
                    alt_match = True

            if is_correct:
                correct += 1
                status = "[CORRECT]"
            elif alt_match:
                # Partial credit — expected dept was in alternatives
                correct += 0.5
                status = "[PARTIAL] (in alternatives)"
            else:
                status = "[WRONG]"

            # Track by language
            if language == "hi":
                hindi_total += 1
                if is_correct:
                    hindi_correct += 1
            elif language == "en":
                english_total += 1
                if is_correct:
                    english_correct += 1

            print(f"  Predicted: {predicted} ({confidence})")
            print(f"  Reasoning: {result.reasoning[:100]}")
            print(f"  Status: {status}")

            results.append({
                "id": sample["id"],
                "expected": expected,
                "predicted": predicted,
                "confidence": confidence,
                "correct": is_correct,
                "alt_match": alt_match,
                "language": language,
                "notes": notes,
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "id": sample["id"],
                "expected": expected,
                "predicted": "ERROR",
                "confidence": "N/A",
                "correct": False,
                "alt_match": False,
                "language": language,
                "notes": str(e),
            })

        print()

    # Summary
    accuracy = (correct / total * 100) if total > 0 else 0
    hindi_acc = (hindi_correct / hindi_total * 100) if hindi_total > 0 else 0
    english_acc = (english_correct / english_total * 100) if english_total > 0 else 0
    parity_gap = abs(hindi_acc - english_acc) if (hindi_total > 0 and english_total > 0) else 0

    print("=" * 70)
    print("BENCHMARK RESULTS")
    print("=" * 70)
    print(f"  Overall Accuracy:   {accuracy:.1f}%  ({correct}/{total})")
    print(f"  English Accuracy:   {english_acc:.1f}%  ({english_correct}/{english_total})")
    print(f"  Hindi Accuracy:     {hindi_acc:.1f}%  ({hindi_correct}/{hindi_total})")
    print(f"  Bilingual Parity:   {parity_gap:.1f}% gap")
    print()

    # Thresholds
    ACCURACY_THRESHOLD = 80.0
    PARITY_THRESHOLD = 5.0

    print("THRESHOLD CHECKS:")
    if accuracy >= ACCURACY_THRESHOLD:
        print(f"  [PASS] Overall accuracy ({accuracy:.1f}%) meets threshold ({ACCURACY_THRESHOLD}%)")
    else:
        print(f"  [FAIL] Overall accuracy ({accuracy:.1f}%) BELOW threshold ({ACCURACY_THRESHOLD}%)")

    if parity_gap <= PARITY_THRESHOLD:
        print(f"  [PASS] Bilingual parity gap ({parity_gap:.1f}%) within threshold ({PARITY_THRESHOLD}%)")
    else:
        print(f"  [WARN] Bilingual parity gap ({parity_gap:.1f}%) EXCEEDS threshold ({PARITY_THRESHOLD}%)")

    # Confidence distribution
    high_count = sum(1 for r in results if r["confidence"] == "HIGH")
    med_count = sum(1 for r in results if r["confidence"] == "MEDIUM")
    low_count = sum(1 for r in results if r["confidence"] == "LOW")
    print(f"\n  Confidence Distribution: HIGH={high_count}, MEDIUM={med_count}, LOW={low_count}")

    # Save results
    output_path = Path(__file__).resolve().parent.parent / "data" / "benchmark_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "overall_accuracy": accuracy,
            "english_accuracy": english_acc,
            "hindi_accuracy": hindi_acc,
            "bilingual_parity_gap": parity_gap,
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to: {output_path}")

    print("=" * 70)
    return accuracy >= ACCURACY_THRESHOLD


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)
