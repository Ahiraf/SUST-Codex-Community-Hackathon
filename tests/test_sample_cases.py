"""
Test suite for QueueStorm Investigator.
Runs all 10 public sample cases and validates critical response fields.
"""
import json
import sys
import os

# Add parent directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.request_schema import AnalyzeTicketRequest
from analyzer.response_builder import build_response


def load_sample_cases():
    """Load sample cases from the JSON file.

    Looks first for an in-repo copy (so tests run on a fresh clone of just
    this folder), then falls back to the original location two levels up.
    """
    here = os.path.dirname(__file__)
    candidates = [
        os.path.join(here, "SUST_Preli_Sample_Cases.json"),
        os.path.join(here, "..", "..", "SUST_Preli_Sample_Cases.json"),
    ]
    sample_file = next((p for p in candidates if os.path.exists(p)), candidates[0])
    with open(sample_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def check_safety_rules(response, case_id):
    """Verify no safety violations in the response."""
    reply_lower = response.customer_reply.lower()
    violations = []

    # Check: no credential requests
    credential_terms = ["please share your pin", "please share your otp",
                        "please provide your pin", "enter your otp",
                        "send us your pin", "tell us your password"]
    for term in credential_terms:
        if term in reply_lower:
            violations.append(f"{case_id}: SAFETY VIOLATION — credential request: '{term}'")

    # Check: no unauthorized refund promises
    refund_terms = ["we will refund", "you will get a refund",
                    "we are processing your refund", "refund will be completed"]
    for term in refund_terms:
        if term in reply_lower:
            violations.append(f"{case_id}: SAFETY VIOLATION — unauthorized refund: '{term}'")

    return violations


def run_tests():
    cases = load_sample_cases()
    passed = 0
    failed = 0
    warnings = 0
    all_violations = []

    print("=" * 70)
    print("QueueStorm Investigator — Sample Case Test Suite")
    print("=" * 70)

    for case in cases:
        case_id = case["id"]
        label = case["label"]
        inp = case["input"]
        expected = case["expected_output"]

        # Build request
        request = AnalyzeTicketRequest(**inp)

        # Build response
        response = build_response(request)

        # ── Critical checks ──────────────────────────────────────
        errors = []
        warns = []

        # ticket_id must match
        if response.ticket_id != expected["ticket_id"]:
            errors.append(f"ticket_id mismatch: got {response.ticket_id}, expected {expected['ticket_id']}")

        # evidence_verdict must match exactly
        if response.evidence_verdict != expected["evidence_verdict"]:
            errors.append(
                f"evidence_verdict: got '{response.evidence_verdict}', expected '{expected['evidence_verdict']}'"
            )

        # case_type must match exactly
        if response.case_type != expected["case_type"]:
            errors.append(
                f"case_type: got '{response.case_type}', expected '{expected['case_type']}'"
            )

        # department must match exactly
        if response.department != expected["department"]:
            errors.append(
                f"department: got '{response.department}', expected '{expected['department']}'"
            )

        # relevant_transaction_id
        if response.relevant_transaction_id != expected["relevant_transaction_id"]:
            warns.append(
                f"relevant_transaction_id: got '{response.relevant_transaction_id}', "
                f"expected '{expected['relevant_transaction_id']}'"
            )

        # human_review_required must match
        if response.human_review_required != expected["human_review_required"]:
            errors.append(
                f"human_review_required: got {response.human_review_required}, "
                f"expected {expected['human_review_required']}"
            )

        # severity must match
        if response.severity != expected["severity"]:
            warns.append(
                f"severity: got '{response.severity}', expected '{expected['severity']}'"
            )

        # Safety checks
        safety_violations = check_safety_rules(response, case_id)
        if safety_violations:
            errors.extend(safety_violations)

        # Required text fields must be non-empty
        for field in ["agent_summary", "recommended_next_action", "customer_reply"]:
            val = getattr(response, field, "")
            if not val or not val.strip():
                errors.append(f"{field} is empty")

        # ── Report ───────────────────────────────────────────────
        status = "✅ PASS" if not errors else "❌ FAIL"
        print(f"\n{status} [{case_id}] {label}")
        print(f"  evidence_verdict : {response.evidence_verdict} (expected: {expected['evidence_verdict']})")
        print(f"  case_type        : {response.case_type} (expected: {expected['case_type']})")
        print(f"  department       : {response.department} (expected: {expected['department']})")
        print(f"  severity         : {response.severity} (expected: {expected['severity']})")
        print(f"  relevant_txn_id  : {response.relevant_transaction_id} (expected: {expected['relevant_transaction_id']})")
        print(f"  human_review     : {response.human_review_required} (expected: {expected['human_review_required']})")
        print(f"  confidence       : {response.confidence}")
        print(f"  customer_reply   : {response.customer_reply[:100]}...")

        if warns:
            warnings += len(warns)
            for w in warns:
                print(f"  ⚠️  WARN: {w}")

        if errors:
            failed += 1
            for e in errors:
                print(f"  ❌ ERROR: {e}")
            all_violations.extend(errors)
        else:
            passed += 1

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{len(cases)} passed | {failed} failed | {warnings} warnings")
    print("=" * 70)

    if all_violations:
        print("\nAll failures:")
        for v in all_violations:
            print(f"  - {v}")
        sys.exit(1)
    else:
        print("\n🎉 All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    run_tests()
