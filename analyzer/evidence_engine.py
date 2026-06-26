"""
Evidence Engine — determines evidence_verdict based on the matched transaction
and the context of the complaint.

Verdict values (exact enum):
  consistent          — data supports the complaint
  inconsistent        — data contradicts the complaint
  insufficient_data   — cannot be determined from the provided history
"""
from typing import List, Optional
from models.request_schema import TransactionHistoryEntry


VERDICT_CONSISTENT = "consistent"
VERDICT_INCONSISTENT = "inconsistent"
VERDICT_INSUFFICIENT = "insufficient_data"


def determine_evidence_verdict(
    complaint: str,
    relevant_txn_id: Optional[str],
    match_reason: str,
    transaction_history: List[TransactionHistoryEntry],
    case_type: str,
) -> str:
    """
    Core evidence verdict logic.

    Rules (in priority order):
    1. If no match found → insufficient_data (default)
    2. If ambiguous match → insufficient_data
    3. If match found → check for contradictions → consistent or inconsistent
    """
    complaint_lower = complaint.lower()

    # ── No match cases ──────────────────────────────────────────────
    if relevant_txn_id is None:
        return VERDICT_INSUFFICIENT

    # Find the matched transaction object
    matched_txn = next(
        (t for t in transaction_history if t.transaction_id == relevant_txn_id),
        None
    )
    if matched_txn is None:
        return VERDICT_INSUFFICIENT

    # ── Phishing/social engineering: always insufficient_data ────────
    # There's no transaction to validate against for fraud reports
    if case_type == "phishing_or_social_engineering":
        return VERDICT_INSUFFICIENT

    # ── Check for contradictions ─────────────────────────────────────

    # Wrong transfer contradiction: same counterparty appears in multiple prior transactions
    # (suggests an "established recipient", not a wrong number)
    if case_type == "wrong_transfer":
        same_counterparty_count = sum(
            1 for t in transaction_history
            if t.counterparty == matched_txn.counterparty
            and t.transaction_id != relevant_txn_id
            and t.type in ("transfer", "payment")
        )
        if same_counterparty_count >= 2:
            return VERDICT_INCONSISTENT

    # Refund request contradiction: if the status is "reversed" already, 
    # then the refund has happened
    if case_type == "refund_request" and matched_txn.status == "reversed":
        return VERDICT_INCONSISTENT

    # Payment failed contradiction: transaction shows completed, not failed
    if case_type == "payment_failed":
        if matched_txn.status == "completed":
            # Customer claims failed but data shows completed
            if "failed" in complaint_lower or "not received" in complaint_lower:
                return VERDICT_INCONSISTENT
        # If status is "failed", that's consistent with the claim
        return VERDICT_CONSISTENT

    # Duplicate payment: two identical transactions close in time → consistent
    if case_type == "duplicate_payment":
        duplicates = [
            t for t in transaction_history
            if t.amount == matched_txn.amount
            and t.counterparty == matched_txn.counterparty
            and t.type == matched_txn.type
            and t.transaction_id != relevant_txn_id
        ]
        if duplicates:
            return VERDICT_CONSISTENT
        else:
            return VERDICT_INCONSISTENT  # No duplicate found in history

    # Agent cash-in: pending status is consistent with complaint of non-receipt
    if case_type == "agent_cash_in_issue":
        if matched_txn.status == "pending":
            return VERDICT_CONSISTENT
        elif matched_txn.status == "completed":
            # Balance was credited but customer says it wasn't received —
            # contradiction
            return VERDICT_INCONSISTENT

    # Merchant settlement delay: pending status is consistent
    if case_type == "merchant_settlement_delay":
        if matched_txn.status in ("pending", "failed"):
            return VERDICT_CONSISTENT
        elif matched_txn.status == "completed":
            return VERDICT_INCONSISTENT

    # Default: a match was found → consistent
    return VERDICT_CONSISTENT
