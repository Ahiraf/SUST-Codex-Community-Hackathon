"""
Case Classifier — determines case_type, department, severity, and human_review_required.

All enum values must match the problem statement exactly (case-sensitive).

case_type values:
  wrong_transfer, payment_failed, refund_request, duplicate_payment,
  merchant_settlement_delay, agent_cash_in_issue, phishing_or_social_engineering, other

department values:
  customer_support, dispute_resolution, payments_ops,
  merchant_operations, agent_operations, fraud_risk

severity values:
  low, medium, high, critical
"""
from typing import List, Optional, Tuple
from models.request_schema import TransactionHistoryEntry


# ──────────────────────────────────────────────────────────────
# Keyword sets for complaint classification
# ──────────────────────────────────────────────────────────────

PHISHING_KEYWORDS = [
    "otp", "pin", "password", "someone called", "called me", "phishing",
    "scam", "fraud call", "asking for", "give otp", "share otp", "share pin",
    "পিন", "ওটিপি", "পাসওয়ার্ড", "ফিশিং", "প্রতারণা", "কেউ ফোন", "ফোন করে",
    "account will be blocked", "blocked if", "bkash call",
]

WRONG_TRANSFER_KEYWORDS = [
    "wrong number", "wrong person", "wrong recipient", "mistake", "wrong account",
    "typed wrong", "ভুল নম্বর", "ভুল ব্যক্তি", "ভুলে পাঠিয়েছি", "wrong transfer",
    "sent to wrong",
]

TRANSFER_COMPLAINT_INDICATORS = [
    "i sent", "sent ", "transfer", "send money", "didn't get", "didn't receive",
    "not received", "hasn't received", "has not received", "he says", "she says",
    "they say", "পাঠিয়েছি", "পাঠানো", "পায়নি", "পায় নি",
]

PAYMENT_FAILED_KEYWORDS = [
    "payment failed", "transaction failed", "failed", "app showed failed",
    "balance deducted", "charged but", "deducted but", "not received",
    "পেমেন্ট ফেইল", "পেমেন্ট ব্যর্থ", "ব্যালেন্স কাটা",
]

DUPLICATE_PAYMENT_KEYWORDS = [
    "twice", "double", "charged twice", "deducted twice", "duplicate", "two times",
    "দুইবার", "দ্বিগুণ", "দুইবার কেটেছে",
]

REFUND_REQUEST_KEYWORDS = [
    "refund", "refund me", "return my money", "give back", "changed my mind",
    "রিফান্ড", "টাকা ফেরত", "টাকা ফিরিয়ে",
]

MERCHANT_SETTLEMENT_KEYWORDS = [
    "settlement", "not settled", "merchant", "sales not received",
    "settle", "সেটেলমেন্ট", "মার্চেন্ট",
]

AGENT_CASH_IN_KEYWORDS = [
    "cash in", "cash-in", "agent", "deposit", "balance not received",
    "balance show", "ক্যাশ ইন", "এজেন্ট", "জমা", "ব্যালেন্সে আসেনি",
    "আসেনি", "received not",
]


def _score_keywords(complaint_lower: str, keywords: List[str]) -> int:
    return sum(1 for kw in keywords if kw in complaint_lower)


def _is_transfer_complaint(complaint_lower: str) -> bool:
    return _score_keywords(complaint_lower, TRANSFER_COMPLAINT_INDICATORS) >= 1


def classify_case(
    complaint: str,
    transaction_history: List[TransactionHistoryEntry],
    relevant_txn_id: Optional[str],
    user_type: Optional[str],
    channel: Optional[str],
) -> Tuple[str, str, str, bool, List[str]]:
    """
    Returns (case_type, department, severity, human_review_required, reason_codes).
    """
    complaint_lower = complaint.lower()
    reason_codes: List[str] = []

    # Find matched transaction
    matched_txn = next(
        (t for t in transaction_history if t.transaction_id == relevant_txn_id),
        None
    ) if relevant_txn_id else None

    # ── 1. Phishing / social engineering (highest priority check) ───
    phishing_score = _score_keywords(complaint_lower, PHISHING_KEYWORDS)
    if phishing_score >= 1:
        reason_codes.append("phishing")
        reason_codes.append("credential_protection")
        reason_codes.append("critical_escalation")
        return "phishing_or_social_engineering", "fraud_risk", "critical", True, reason_codes

    # ── 2. Agent cash-in issue ──────────────────────────────────────
    agent_score = _score_keywords(complaint_lower, AGENT_CASH_IN_KEYWORDS)
    has_cash_in_txn = matched_txn and matched_txn.type == "cash_in"
    has_pending_cash_in = any(
        t.type == "cash_in" and t.status == "pending"
        for t in transaction_history
    )
    if (agent_score >= 2 or has_cash_in_txn or has_pending_cash_in) and agent_score >= 1:
        severity = "high" if has_pending_cash_in else "medium"
        reason_codes.extend(["agent_cash_in", "agent_ops"])
        if has_pending_cash_in:
            reason_codes.append("pending_transaction")
        return "agent_cash_in_issue", "agent_operations", severity, True, reason_codes

    # ── 3. Merchant settlement delay ────────────────────────────────
    merchant_score = _score_keywords(complaint_lower, MERCHANT_SETTLEMENT_KEYWORDS)
    is_merchant = user_type == "merchant" or channel == "merchant_portal"
    has_settlement_txn = matched_txn and matched_txn.type == "settlement"
    if (merchant_score >= 1 and is_merchant) or has_settlement_txn:
        severity = "medium"
        # Only mark critical/high if truly large amount AND very delayed
        if matched_txn and matched_txn.amount >= 50000:
            severity = "high"
        reason_codes.extend(["merchant_settlement", "delay"])
        if matched_txn and matched_txn.status == "pending":
            reason_codes.append("pending")
        # Merchant settlement does NOT require human_review by default — routed to merchant_ops
        return "merchant_settlement_delay", "merchant_operations", severity, False, reason_codes

    # ── 4. Duplicate payment ────────────────────────────────────────
    dup_score = _score_keywords(complaint_lower, DUPLICATE_PAYMENT_KEYWORDS)
    # Also detect via transaction history: two same-amount payments to same counterparty
    if matched_txn:
        dupes = [
            t for t in transaction_history
            if t.amount == matched_txn.amount
            and t.counterparty == matched_txn.counterparty
            and t.type == matched_txn.type
            and t.transaction_id != matched_txn.transaction_id
        ]
        txn_based_dup = len(dupes) >= 1
    else:
        txn_based_dup = False

    if dup_score >= 1 or txn_based_dup:
        severity = "high"
        if matched_txn and matched_txn.amount >= 5000:
            severity = "critical"
        reason_codes.extend(["duplicate_payment", "biller_verification_required"])
        return "duplicate_payment", "payments_ops", severity, True, reason_codes

    # ── 5. Payment failed ───────────────────────────────────────────
    failed_score = _score_keywords(complaint_lower, PAYMENT_FAILED_KEYWORDS)
    has_failed_txn = matched_txn and matched_txn.status == "failed"
    has_payment_txn = matched_txn and matched_txn.type in ("payment",)
    if failed_score >= 1 or has_failed_txn:
        # Distinguish payment_failed from wrong_transfer
        is_transfer_complaint = _score_keywords(complaint_lower, WRONG_TRANSFER_KEYWORDS) >= 1
        if not is_transfer_complaint:
            severity = "high"
            reason_codes.extend(["payment_failed", "potential_balance_deduction"])
            # payment_failed does NOT require human review by default (ops team handles via SLA)
            return "payment_failed", "payments_ops", severity, False, reason_codes

    # ── 6. Wrong transfer ───────────────────────────────────────────
    wrong_txn_score = _score_keywords(complaint_lower, WRONG_TRANSFER_KEYWORDS)
    has_transfer_txn = matched_txn and matched_txn.type == "transfer"
    is_transfer_complaint = _is_transfer_complaint(complaint_lower)
    if wrong_txn_score >= 1 or has_transfer_txn or is_transfer_complaint:
        # If no transaction matched (ambiguous / insufficient data)
        # → medium severity, no human review yet (need more info first)
        if matched_txn is None:
            severity = "medium"
            reason_codes.extend(["ambiguous_match", "needs_clarification"])
            return "wrong_transfer", "dispute_resolution", severity, False, reason_codes

        severity = "high"
        if matched_txn.amount >= 10000:
            severity = "critical"
        reason_codes.extend(["wrong_transfer", "transaction_match"])
        # Check for "established recipient" contradiction — lower severity for inconsistent evidence
        same_counterparty = sum(
            1 for t in transaction_history
            if t.counterparty == matched_txn.counterparty
            and t.transaction_id != matched_txn.transaction_id
            and t.type in ("transfer", "payment")
        )
        if same_counterparty >= 2:
            reason_codes.append("established_recipient_pattern")
            reason_codes.append("evidence_inconsistent")
            severity = "medium"  # Inconsistent evidence → lower urgency
        else:
            reason_codes.append("dispute_initiated")
        return "wrong_transfer", "dispute_resolution", severity, True, reason_codes

    # ── 7. Refund request ───────────────────────────────────────────
    refund_score = _score_keywords(complaint_lower, REFUND_REQUEST_KEYWORDS)
    if refund_score >= 1:
        severity = "low"
        if matched_txn and matched_txn.amount >= 5000:
            severity = "medium"
        reason_codes.extend(["refund_request", "merchant_policy_dependent"])
        return "refund_request", "customer_support", severity, False, reason_codes

    # ── 8. Other / vague ────────────────────────────────────────────
    reason_codes.extend(["vague_complaint", "needs_clarification"])
    return "other", "customer_support", "low", False, reason_codes


# ──────────────────────────────────────────────────────────────
# Human review logic
# ──────────────────────────────────────────────────────────────

def should_require_human_review(
    case_type: str,
    severity: str,
    evidence_verdict: str,
    matched_txn: Optional[TransactionHistoryEntry],
    human_review_required: bool,  # from classify_case
) -> bool:
    """
    Final human review determination.
    Primarily trusts the flag from classify_case.
    Additional escalation only for truly high-stakes situations.
    """
    # Always trust the classifier's explicit flag
    if human_review_required:
        return True
    # Inconsistent evidence always warrants a second look
    if evidence_verdict == "inconsistent":
        return True
    # Critical severity always escalates
    if severity == "critical":
        return True
    # High-value matched transactions escalate
    if matched_txn and matched_txn.amount >= 5000 and case_type not in (
        "refund_request", "other", "merchant_settlement_delay"
    ):
        return True
    return False
