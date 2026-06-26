"""
Safety Checker — post-processes all generated text outputs to ensure
compliance with the fintech safety rules from the problem statement.

Rules (with penalty amounts):
  -15 pts: Never ask for PIN, OTP, password, full card number
  -10 pts: Never confirm refund, reversal, account unblock without authority
  -10 pts: Never direct to suspicious third parties
  Disqualification: 2+ critical safety violations across hidden cases

This module is the final safety gate AFTER the templates generate text.
"""
import re

# ──────────────────────────────────────────────────────────────
# Dangerous patterns to detect and fix
# ──────────────────────────────────────────────────────────────

# Credential request patterns
CREDENTIAL_REQUEST_PATTERNS = [
    r"\bplease\b.{0,40}\b(share|send|provide|give|enter|type)\b.{0,40}\b(pin|otp|password|card.?number|cvv|secret)\b",
    r"\b(share|send|provide|give|enter|type)\b.{0,40}\b(pin|otp|password|card.?number|cvv|secret)\b",
    r"\bverif\w+\b.{0,40}\b(pin|otp|password)\b",
    r"\b(can you|could you|please)\b.{0,30}\b(confirm|provide|share)\b.{0,30}\b(pin|otp|password)\b",
]

# Unauthorized refund/reversal promise patterns
UNAUTHORIZED_REFUND_PATTERNS = [
    r"\bwe will refund\b",
    r"\byou will (get|receive) (your|a) refund\b",
    r"\bwe are (processing|initiating) (your )?refund\b",
    r"\brefund (has been|will be) (processed|initiated|completed|done|made)\b",
    r"\bwe will reverse\b",
    r"\bwe will unblock\b",
    r"\bwe will recover\b",
    r"\byour account (will be|has been) unblocked\b",
    r"\bmoney will be returned\b",
    r"\bfunds? will be (restored?|returned|refunded|reversed)\b",
]

# Suspicious third party patterns
SUSPICIOUS_THIRD_PARTY_PATTERNS = [
    r"\bcontact\b.{0,30}\b(this number|that number|this person|third.?party)\b",
    r"\bcall\b.{0,30}\b(\+\d{10,}|0\d{9,})\b",
]

# Safe replacements for unauthorized refund language
SAFE_REFUND_REPLACEMENT = "any eligible amount will be returned through official channels"

# Prompt injection: instructions embedded in user text.
# Patterns are scoped to instruction-like phrasing so ordinary complaints
# (e.g. "I act as guardian", "disregard the receipt") are not flagged.
INJECTION_PATTERNS = [
    r"ignore (the |these |your )?(previous|all|prior|above) (instructions?|rules?|prompts?)",
    r"disregard (the |these |your |any )?(previous|all|prior|above) (instructions?|rules?|prompts?)",
    r"forget (your |the |previous |all )?(instructions?|rules?|prompts?)",
    r"you are now (a |an )?",
    r"act as (a |an )?(ai|assistant|model|system|dan|jailbreak)",
    r"system prompt",
    r"new (system )?instructions?:",
    r"override (your |the |all )?(instructions?|rules?|safety)",
]

NEGATION_PHRASES = (
    "do not share",
    "don't share",
    "never share",
    "never ask",
    "do not provide",
    "don't provide",
    "do not send",
    "don't send",
    "do not give",
    "don't give",
    "not share your",
    "without sharing",
)


def _is_negated_credential_request(text: str, match: re.Match) -> bool:
    """True when the match is a safety reminder (e.g. 'do not share your PIN')."""
    window = text[max(0, match.start() - 25): match.end() + 10].lower()
    return any(phrase in window for phrase in NEGATION_PHRASES)


def sanitize_text(text: str) -> str:
    """
    Remove or replace unsafe content in a generated text field.
    Returns the sanitized text.
    """
    # Lowercase for pattern matching but preserve original case for replacement
    # We work on lowercased version for detection, then fix original

    # 1. Remove/replace unauthorized refund promises
    for pattern in UNAUTHORIZED_REFUND_PATTERNS:
        text = re.sub(pattern, SAFE_REFUND_REPLACEMENT, text, flags=re.IGNORECASE)

    # 2. Remove credential requests entirely (replace with safety reminder)
    for pattern in CREDENTIAL_REQUEST_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match and not _is_negated_credential_request(text, match):
            text = re.sub(
                r"[^.!?]*" + pattern + r"[^.!?]*[.!?]?",
                "",
                text,
                flags=re.IGNORECASE,
            )

    # 3. Ensure every customer reply contains the PIN/OTP safety reminder
    # if it doesn't already have one
    safety_reminder_en = "Please do not share your PIN or OTP with anyone."
    safety_reminder_bn = "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"

    has_reminder = (
        "pin" in text.lower() and "otp" in text.lower()
    ) or "পিন" in text or "ওটিপি" in text

    # Detect if reply is in Bangla
    is_bangla = any(ord(c) > 0x0980 for c in text)

    if not has_reminder:
        reminder = safety_reminder_bn if is_bangla else safety_reminder_en
        text = text.rstrip() + " " + reminder

    return text.strip()


def check_safety(
    customer_reply: str,
    recommended_next_action: str,
) -> tuple[str, str, list[str]]:
    """
    Run safety checks on customer_reply and recommended_next_action.
    Returns (safe_customer_reply, safe_recommended_next_action, violations_list).
    """
    violations = []

    # Check for credential requests (ignore safety reminders like "do not share your PIN")
    for pattern in CREDENTIAL_REQUEST_PATTERNS:
        match = re.search(pattern, customer_reply, flags=re.IGNORECASE)
        if match and not _is_negated_credential_request(customer_reply, match):
            violations.append("credential_request_detected")
            break

    # Check for unauthorized refund promises
    for pattern in UNAUTHORIZED_REFUND_PATTERNS:
        if re.search(pattern, customer_reply, flags=re.IGNORECASE):
            violations.append("unauthorized_refund_promise")
            break

    # Check for unauthorized refund in recommended_next_action
    for pattern in UNAUTHORIZED_REFUND_PATTERNS:
        if re.search(pattern, recommended_next_action, flags=re.IGNORECASE):
            violations.append("unauthorized_refund_in_action")
            break

    # Sanitize
    safe_reply = sanitize_text(customer_reply)
    safe_action = recommended_next_action

    # Remove unauthorized promises from recommended action too
    for pattern in UNAUTHORIZED_REFUND_PATTERNS:
        safe_action = re.sub(pattern, "initiate review per policy", safe_action, flags=re.IGNORECASE)

    return safe_reply, safe_action, violations


def detect_prompt_injection(complaint: str) -> bool:
    """Detect if the complaint contains embedded instructions (prompt injection)."""
    complaint_lower = complaint.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, complaint_lower):
            return True
    return False
