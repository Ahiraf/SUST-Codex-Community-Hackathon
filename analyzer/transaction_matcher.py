"""
Transaction Matcher — finds the most relevant transaction from the history
that matches the customer's complaint.

Strategy:
 1. Extract clues from complaint: amounts, type hints, time hints, counterparty hints.
 2. Score each transaction against those clues.
 3. If a clear winner exists, return its ID. Otherwise return None (ambiguous/no match).
"""
import re
from typing import List, Optional, Tuple
from models.request_schema import TransactionHistoryEntry


# ──────────────────────────────────────────────────────────────
# Amount extraction helpers
# ──────────────────────────────────────────────────────────────

def _extract_amounts(text: str) -> List[float]:
    """Pull numeric values from complaint text (handles commas, Bangla digits)."""
    # Replace Bangla digits ০-৯ with ASCII
    bangla_map = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
    text = text.translate(bangla_map)
    # Strip phone numbers first so they are not mistaken for transaction amounts
    # (e.g. "01712345678" or "+8801712345678").
    text = re.sub(r"\+?8801[3-9]\d{8}", " ", text)
    text = re.sub(r"\b01[3-9]\d{8}\b", " ", text)
    # Find numbers (including decimal)
    raw = re.findall(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
    amounts = []
    for r in raw:
        try:
            v = float(r.replace(",", ""))
            if v > 0:
                amounts.append(v)
        except ValueError:
            pass
    return amounts


# ──────────────────────────────────────────────────────────────
# Type hint keywords
# ──────────────────────────────────────────────────────────────

TYPE_KEYWORDS = {
    "transfer":    ["sent", "send", "transfer", "wrong number", "wrong person", "পাঠিয়েছি", "পাঠানো", "ট্রান্সফার"],
    "payment":     ["paid", "pay", "payment", "bill", "recharge", "merchant", "পেমেন্ট", "পরিশোধ"],
    "cash_in":     ["cash in", "cash-in", "deposit", "agent", "ক্যাশ ইন", "জমা"],
    "cash_out":    ["cash out", "withdraw", "ক্যাশ আউট", "উত্তোলন"],
    "settlement":  ["settlement", "settle", "সেটেলমেন্ট"],
    "refund":      ["refund", "refunded", "রিফান্ড"],
}

def _guess_type_from_complaint(text: str) -> Optional[str]:
    text_lower = text.lower()
    scores = {}
    for txn_type, kws in TYPE_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in text_lower)
        if score:
            scores[txn_type] = score
    if not scores:
        return None
    return max(scores, key=scores.get)


# ──────────────────────────────────────────────────────────────
# Time hints: "today", "yesterday", "this morning", "2pm", etc.
# ──────────────────────────────────────────────────────────────

TIME_HINTS_TODAY = ["today", "আজ", "এখন"]
TIME_HINTS_YESTERDAY = ["yesterday", "গতকাল"]
TIME_HINTS_MORNING = ["morning", "সকাল"]
TIME_HINTS_AFTERNOON = ["afternoon", "2pm", "3pm", "4pm", "বিকেল", "দুপুর"]
TIME_HINTS_EVENING = ["evening", "night", "রাত", "সন্ধ্যা"]


def _timestamp_to_seconds(timestamp: str) -> float:
    """Parse ISO 8601 timestamp to epoch seconds for simple interval checks."""
    try:
        from datetime import datetime, timezone
        normalized = timestamp.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _time_score(complaint_lower: str, txn: TransactionHistoryEntry) -> float:
    """Bonus score if transaction timing matches complaint hints."""
    score = 0.0
    # crude hour extraction from timestamp
    try:
        hour = int(txn.timestamp[11:13])
    except (IndexError, ValueError):
        hour = 12

    if any(h in complaint_lower for h in TIME_HINTS_TODAY):
        score += 0.5  # recent transactions get a boost
    if any(h in complaint_lower for h in TIME_HINTS_YESTERDAY):
        score += 0.3
    if any(h in complaint_lower for h in TIME_HINTS_MORNING) and 6 <= hour < 12:
        score += 0.5
    if any(h in complaint_lower for h in TIME_HINTS_AFTERNOON) and 12 <= hour < 18:
        score += 0.5
    if any(h in complaint_lower for h in TIME_HINTS_EVENING) and (hour >= 18 or hour < 6):
        score += 0.5
    return score


# ──────────────────────────────────────────────────────────────
# Main matcher
# ──────────────────────────────────────────────────────────────

def find_relevant_transaction(
    complaint: str,
    transaction_history: List[TransactionHistoryEntry],
) -> Tuple[Optional[str], str]:
    """
    Returns (transaction_id | None, match_reason).
    match_reason is a short label used downstream for evidence scoring.
    """
    if not transaction_history:
        return None, "no_history"

    complaint_lower = complaint.lower()
    amounts_in_complaint = _extract_amounts(complaint)
    guessed_type = _guess_type_from_complaint(complaint)

    scored: List[Tuple[float, TransactionHistoryEntry]] = []

    for txn in transaction_history:
        score = 0.0

        # Amount match (highest signal)
        if amounts_in_complaint:
            if txn.amount in amounts_in_complaint:
                score += 3.0
            else:
                # Allow ±5% tolerance for rounding
                for a in amounts_in_complaint:
                    if a > 0 and abs(txn.amount - a) / a < 0.05:
                        score += 2.0
                        break

        # Type match
        if guessed_type and txn.type == guessed_type:
            score += 2.0

        # Time bonus
        score += _time_score(complaint_lower, txn)

        # Status hints: "failed", "deducted but failed"
        if "failed" in complaint_lower and txn.status == "failed":
            score += 1.5
        if "pending" in complaint_lower and txn.status == "pending":
            score += 1.0
        if ("not received" in complaint_lower or "আসেনি" in complaint_lower) and txn.status == "pending":
            score += 1.5

        # Counterparty hints (phone fragment)
        phone_fragments = re.findall(r"01[3-9]\d{8}", complaint)
        for frag in phone_fragments:
            if frag in txn.counterparty:
                score += 3.0

        # Agent mentions
        if ("agent" in complaint_lower or "এজেন্ট" in complaint_lower) and "AGENT" in txn.counterparty:
            score += 1.0

        # Merchant mentions
        if ("merchant" in complaint_lower or "electricity" in complaint_lower or
                "recharge" in complaint_lower) and "MERCHANT" in txn.counterparty.upper():
            score += 1.0

        scored.append((score, txn))

    if not scored:
        return None, "no_history"

    # Sort descending
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_txn = scored[0]

    # Duplicate payment: identical amount, type, and counterparty → pick the later txn
    if len(transaction_history) >= 2:
        dup_groups: dict[tuple, list] = {}
        for txn in transaction_history:
            key = (txn.amount, txn.type, txn.counterparty)
            dup_groups.setdefault(key, []).append(txn)
        complaint_suggests_dup = any(
            kw in complaint_lower
            for kw in ("twice", "double", "duplicate", "two times", "deducted twice", "দুইবার")
        )
        for group in dup_groups.values():
            completed = [t for t in group if t.status == "completed"]
            if len(completed) >= 2:
                if complaint_suggests_dup:
                    latest = max(completed, key=lambda t: t.timestamp)
                    return latest.transaction_id, "duplicate_match"
                # Auto-detect duplicate when two completed txns are seconds/minutes apart
                completed_sorted = sorted(completed, key=lambda t: t.timestamp)
                for i in range(len(completed_sorted) - 1):
                    t1 = completed_sorted[i].timestamp
                    t2 = completed_sorted[i + 1].timestamp
                    if t1[:10] == t2[:10] and abs(
                        _timestamp_to_seconds(t2) - _timestamp_to_seconds(t1)
                    ) <= 300:
                        return completed_sorted[-1].transaction_id, "duplicate_match"

    # Detect truly ambiguous cases:
    # Multiple transactions with the SAME amount AND same type on the same day
    # but DIFFERENT counterparties → cannot determine which one without more info
    if amounts_in_complaint and len(scored) >= 2:
        best_amount = best_txn.amount
        best_type = best_txn.type
        same_amount_same_type = [
            txn for _, txn in scored
            if txn.amount == best_amount and txn.type == best_type
        ]
        if len(same_amount_same_type) >= 2:
            counterparties = {txn.counterparty for txn in same_amount_same_type}
            if len(counterparties) == 1:
                latest = max(same_amount_same_type, key=lambda t: t.timestamp)
                return latest.transaction_id, "duplicate_match"

            dates = set()
            for txn in same_amount_same_type:
                try:
                    dates.add(txn.timestamp[:10])  # YYYY-MM-DD
                except Exception:
                    pass
            if len(dates) <= 1:  # Same day (or unknown)
                return None, "ambiguous_match"

    # If there's effectively a tie among top candidates (score gap < 1.5) → ambiguous
    if len(scored) >= 2:
        second_score = scored[1][0]
        if best_score > 0 and best_score - second_score < 1.5 and best_score < 5.0:
            return None, "ambiguous_match"

    # Minimum threshold to claim a match
    if best_score < 1.5:
        return None, "low_confidence_match"

    return best_txn.transaction_id, "match_found"
