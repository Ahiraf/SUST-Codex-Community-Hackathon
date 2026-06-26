"""
Response Builder — the main orchestrator that ties together all sub-modules
and produces the final AnalyzeTicketResponse JSON.

Flow:
  1. Extract prompt-injection indicators from complaint
  2. Find relevant transaction (transaction_matcher)
  3. Classify case (case_classifier)
  4. Determine evidence verdict (evidence_engine)
  5. Generate text fields (deterministic rule-based templates)
  6. Post-process safety (safety_checker)
  7. Compute confidence and reason_codes
  8. Return AnalyzeTicketResponse
"""
from typing import Optional, List
import logging

from models.request_schema import AnalyzeTicketRequest, TransactionHistoryEntry
from models.response_schema import AnalyzeTicketResponse

from analyzer.transaction_matcher import find_relevant_transaction
from analyzer.case_classifier import classify_case, should_require_human_review
from analyzer.evidence_engine import determine_evidence_verdict
from analyzer.text_generator import generate_text_fields
from analyzer.safety_checker import check_safety, detect_prompt_injection

logger = logging.getLogger(__name__)


def build_response(request: AnalyzeTicketRequest) -> AnalyzeTicketResponse:
    """
    Main entry point — takes a validated request and returns a full response.
    """
    complaint = request.complaint.strip()
    transaction_history: List[TransactionHistoryEntry] = request.transaction_history or []

    # ── Step 1: Detect prompt injection ─────────────────────────────
    is_injection = detect_prompt_injection(complaint)
    classification_complaint = complaint
    generation_complaint = complaint
    if is_injection:
        logger.warning(f"Prompt injection detected in ticket {request.ticket_id}")
        # Keep original text for rule-based classification; sanitize only for text generation
        generation_complaint = "[SANITIZED COMPLAINT — INJECTION ATTEMPT DETECTED]"

    # ── Step 2: Find relevant transaction ───────────────────────────
    relevant_txn_id, match_reason = find_relevant_transaction(
        classification_complaint, transaction_history
    )

    # ── Step 3: Preliminary classification (needed before evidence) ──
    case_type, department, severity, human_review_flag, reason_codes = classify_case(
        complaint=classification_complaint,
        transaction_history=transaction_history,
        relevant_txn_id=relevant_txn_id,
        user_type=request.user_type,
        channel=request.channel,
    )
    if is_injection:
        reason_codes.append("prompt_injection_detected")

    # ── Step 4: Evidence verdict ─────────────────────────────────────
    evidence_verdict = determine_evidence_verdict(
        complaint=classification_complaint,
        relevant_txn_id=relevant_txn_id,
        match_reason=match_reason,
        transaction_history=transaction_history,
        case_type=case_type,
    )

    # ── Step 5: Human review determination ──────────────────────────
    matched_txn = next(
        (t for t in transaction_history if t.transaction_id == relevant_txn_id),
        None
    ) if relevant_txn_id else None

    human_review_required = should_require_human_review(
        case_type=case_type,
        severity=severity,
        evidence_verdict=evidence_verdict,
        matched_txn=matched_txn,
        human_review_required=human_review_flag,
    )

    # ── Step 6: Generate text fields ─────────────────────────────────
    txn_amount = matched_txn.amount if matched_txn else None
    txn_status = matched_txn.status if matched_txn else None

    agent_summary, recommended_next_action, customer_reply = generate_text_fields(
        complaint=generation_complaint,
        case_type=case_type,
        evidence_verdict=evidence_verdict,
        severity=severity,
        department=department,
        relevant_txn_id=relevant_txn_id,
        txn_amount=txn_amount,
        txn_status=txn_status,
        user_type=request.user_type,
        language=request.language,
    )

    # ── Step 7: Safety post-processing ──────────────────────────────
    safe_reply, safe_action, violations = check_safety(customer_reply, recommended_next_action)

    if violations:
        logger.warning(f"Safety violations in ticket {request.ticket_id}: {violations}")
        # Add violations to reason codes for transparency
        reason_codes.extend([f"safety_fix:{v}" for v in violations])

    # ── Step 8: Confidence score ─────────────────────────────────────
    confidence = _compute_confidence(
        match_reason=match_reason,
        evidence_verdict=evidence_verdict,
        case_type=case_type,
        relevant_txn_id=relevant_txn_id,
        matched_txn=matched_txn,
    )

    # ── Step 9: Assemble response ────────────────────────────────────
    return AnalyzeTicketResponse(
        ticket_id=request.ticket_id,
        relevant_transaction_id=relevant_txn_id,
        evidence_verdict=evidence_verdict,
        case_type=case_type,
        severity=severity,
        department=department,
        agent_summary=agent_summary,
        recommended_next_action=safe_action,
        customer_reply=safe_reply,
        human_review_required=human_review_required,
        confidence=confidence,
        reason_codes=reason_codes,
    )


def _compute_confidence(
    match_reason: str,
    evidence_verdict: str,
    case_type: str,
    relevant_txn_id: Optional[str],
    matched_txn: Optional[TransactionHistoryEntry],
) -> float:
    """
    Compute a confidence score (0.0 to 1.0) based on how strongly
    the evidence supports the classification.
    """
    base = 0.5

    # Transaction match quality
    if relevant_txn_id and match_reason in ("match_found", "duplicate_match"):
        base += 0.2
    elif match_reason == "ambiguous_match":
        base -= 0.1
    elif match_reason == "low_confidence_match":
        base -= 0.05

    # Evidence verdict quality
    if evidence_verdict == "consistent":
        base += 0.2
    elif evidence_verdict == "inconsistent":
        base += 0.1  # We're confident about the inconsistency
    else:  # insufficient_data
        base -= 0.1

    # Phishing is almost always high confidence
    if case_type == "phishing_or_social_engineering":
        base = max(base, 0.92)

    # Cap
    return round(min(max(base, 0.3), 0.97), 2)
