"""
Text Generator — produces the three free-text response fields using
deterministic, rule-based templates (English + Bangla).

Generated fields:
  - agent_summary           (1-2 sentences, internal)
  - recommended_next_action (operational step for the support agent)
  - customer_reply          (safe, official reply to the customer)

No external API, no model weights, no network calls — output is fully
deterministic and instant. The wording is keyed off the rule-engine's
classification (case_type, evidence_verdict, severity, department) and the
matched transaction, and every reply is written to respect the safety rules
(no credential requests, no unauthorized refund promises).
"""
from typing import Optional


def generate_text_fields(
    complaint: str,
    case_type: str,
    evidence_verdict: str,
    severity: str,
    department: str,
    relevant_txn_id: Optional[str],
    txn_amount: Optional[float],
    txn_status: Optional[str],
    user_type: Optional[str],
    language: Optional[str],
) -> tuple[str, str, str]:
    """Return (agent_summary, recommended_next_action, customer_reply)."""
    is_bangla = language == "bn" or _is_bangla(complaint)
    txn_ref = f"transaction {relevant_txn_id}" if relevant_txn_id else "the reported transaction"
    amount_str = f"{int(txn_amount)} BDT" if txn_amount else "the reported amount"

    templates = {
        "wrong_transfer": {
            "en": {
                "summary": f"Customer reports sending {amount_str} via {txn_ref} to an unintended recipient. {'Transaction history is consistent with the complaint.' if evidence_verdict == 'consistent' else 'Transaction history shows repeated transfers to the same recipient, suggesting an established contact.' if evidence_verdict == 'inconsistent' else 'Transaction details are unclear from the provided history.'}",
                "action": f"Verify {txn_ref} details and {'initiate the wrong-transfer dispute workflow per policy.' if evidence_verdict == 'consistent' else 'flag for human review given the established recipient pattern.' if evidence_verdict == 'inconsistent' else 'request additional details from the customer.'}",
                "reply": f"We have noted your concern about {txn_ref}. Our dispute team will review the case and any eligible amount will be returned through official channels. Please do not share your PIN or OTP with anyone.",
            },
            "ambiguous_en": {
                "summary": "Customer reports a transfer that may not have been received. Multiple transactions in history could match; the specific transaction cannot be determined without further details.",
                "action": "Reply to customer asking for the recipient's phone number to identify the correct transaction. Do not initiate dispute until the transaction is confirmed.",
                "reply": "Thank you for reaching out. We see multiple transactions that could match your report. Could you share the recipient's phone number so we can identify the right transaction? Please do not share your PIN or OTP with anyone.",
            },
            "bn": {
                "summary": f"গ্রাহক {txn_ref} এর মাধ্যমে {amount_str} ভুল নম্বরে পাঠানোর অভিযোগ করেছেন।",
                "action": f"{txn_ref} এর বিবরণ যাচাই করুন এবং ভুল ট্রান্সফার বিরোধ প্রক্রিয়া শুরু করুন।",
                "reply": f"আপনার {txn_ref} বিষয়ে আমরা অবগত হয়েছি। আমাদের বিরোধ নিষ্পত্তি দল বিষয়টি পর্যালোচনা করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।",
            },
        },
        "payment_failed": {
            "en": {
                "summary": f"Customer reports that {txn_ref} ({amount_str}) failed but balance was deducted. Requires payments operations investigation.",
                "action": f"Investigate {txn_ref} ledger status. If balance was deducted on a failed payment, initiate the automatic reversal flow within standard SLA.",
                "reply": f"We have noted that {txn_ref} may have caused an unexpected balance deduction. Our payments team will review the case and any eligible amount will be returned through official channels. Please do not share your PIN or OTP with anyone.",
            },
            "bn": {
                "summary": f"গ্রাহক {txn_ref} ({amount_str}) ব্যর্থ হওয়ার পরেও ব্যালেন্স কাটার অভিযোগ করেছেন।",
                "action": f"{txn_ref} এর লেজার স্ট্যাটাস তদন্ত করুন এবং প্রযোজ্য হলে রিভার্সাল প্রক্রিয়া শুরু করুন।",
                "reply": f"আপনার {txn_ref} বিষয়ে আমরা অবগত হয়েছি। পেমেন্ট টিম এটি যাচাই করবে এবং যোগ্য পরিমাণ অফিসিয়াল চ্যানেলে ফেরত দেওয়া হবে। অনুগ্রহ করে পিন বা ওটিপি কারো সাথে শেয়ার করবেন না।",
            },
        },
        "refund_request": {
            "en": {
                "summary": f"Customer requests refund of {amount_str} for {txn_ref}. This is a discretionary refund request, not a service failure.",
                "action": "Inform the customer that refund eligibility depends on the merchant's own policy. Provide guidance on contacting the merchant directly.",
                "reply": "Thank you for reaching out. Refunds for completed payments depend on the merchant's own policy. We recommend contacting the merchant directly for a refund. If you need help reaching them, please reply and we will guide you. Please do not share your PIN or OTP with anyone.",
            },
            "bn": {
                "summary": f"গ্রাহক {txn_ref} এর {amount_str} রিফান্ড চেয়েছেন। এটি মার্চেন্টের নীতির উপর নির্ভর করে।",
                "action": "গ্রাহককে জানান যে রিফান্ড যোগ্যতা মার্চেন্টের নীতির উপর নির্ভর করে।",
                "reply": "আপনার অভিযোগের জন্য ধন্যবাদ। সম্পন্ন পেমেন্টের রিফান্ড মার্চেন্টের নীতির উপর নির্ভর করে। অনুগ্রহ করে সরাসরি মার্চেন্টের সাথে যোগাযোগ করুন। পিন বা ওটিপি কারো সাথে শেয়ার করবেন না।",
            },
        },
        "duplicate_payment": {
            "en": {
                "summary": f"Customer reports duplicate payment for {txn_ref}. Two identical transactions of {amount_str} appear in history close in time, strongly suggesting a duplicate charge.",
                "action": f"Verify the duplicate with payments_ops. If the biller confirms only one payment was received, initiate reversal per policy.",
                "reply": f"We have noted the possible duplicate payment for {txn_ref}. Our payments team will verify with the biller and any eligible amount will be returned through official channels. Please do not share your PIN or OTP with anyone.",
            },
            "bn": {
                "summary": f"গ্রাহক {txn_ref} এর ডুপ্লিকেট পেমেন্টের অভিযোগ করেছেন।",
                "action": "পেমেন্ট টিম বিলারের সাথে যাচাই করুন এবং ডুপ্লিকেট নিশ্চিত হলে রিভার্সাল প্রক্রিয়া শুরু করুন।",
                "reply": f"আমরা {txn_ref} এর সম্ভাব্য ডুপ্লিকেট পেমেন্টের বিষয়ে অবগত হয়েছি। পেমেন্ট টিম বিলারের সাথে যাচাই করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। পিন বা ওটিপি শেয়ার করবেন না।",
            },
        },
        "merchant_settlement_delay": {
            "en": {
                "summary": f"Merchant reports {txn_ref} ({amount_str}) is delayed beyond the expected settlement window. Settlement status is {txn_status or 'pending'}.",
                "action": "Route to merchant_operations to verify settlement batch status. If delayed, communicate a revised ETA to the merchant.",
                "reply": f"We have noted your concern about settlement {txn_ref}. Our merchant operations team will check the batch status and update you on the expected settlement time through official channels.",
            },
            "bn": {
                "summary": f"মার্চেন্ট {txn_ref} এর সেটেলমেন্ট বিলম্বের অভিযোগ করেছেন।",
                "action": "মার্চেন্ট অপারেশন্স দলকে ব্যাচ স্ট্যাটাস যাচাই করতে বলুন।",
                "reply": f"আপনার {txn_ref} সেটেলমেন্ট বিষয়ে আমরা অবগত হয়েছি। মার্চেন্ট অপারেশন্স দল ব্যাচ স্ট্যাটাস যাচাই করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে।",
            },
        },
        "agent_cash_in_issue": {
            "en": {
                "summary": f"Customer reports cash-in via agent not reflected in balance. {txn_ref} shows status: {txn_status or 'pending'}. Agent claims funds were sent.",
                "action": f"Investigate {txn_ref} pending status with agent operations. Confirm settlement state and resolve within the standard cash-in SLA.",
                "reply": f"We have noted your concern about {txn_ref}. Our agent operations team will verify the transaction status and update you through official channels. Please do not share your PIN or OTP with anyone.",
            },
            "bn": {
                "summary": f"গ্রাহক এজেন্টের মাধ্যমে ক্যাশ ইন ({txn_ref}) ব্যালেন্সে না আসার অভিযোগ করেছেন।",
                "action": f"এজেন্ট অপারেশন্স দলকে {txn_ref} এর পেন্ডিং স্ট্যাটাস যাচাই করতে বলুন।",
                "reply": f"আপনার লেনদেন {txn_ref} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের এজেন্ট অপারেশন্স দল এটি দ্রুত যাচাই করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।",
            },
        },
        "phishing_or_social_engineering": {
            "en": {
                "summary": "Customer reports an unsolicited contact claiming to be from the company and requesting sensitive credentials. Likely a social engineering attempt.",
                "action": "Escalate to fraud_risk team immediately. Confirm to customer that the company never asks for OTP. Log the reported number for fraud pattern analysis.",
                "reply": "Thank you for reaching out before sharing any information. We never ask for your PIN, OTP, or password under any circumstances. Please do not share these with anyone, even if they claim to be from us. Our fraud team has been notified of this incident.",
            },
            "bn": {
                "summary": "গ্রাহক অননুমোদিত যোগাযোগের অভিযোগ করেছেন যেখানে সংবেদনশীল তথ্য চাওয়া হয়েছে।",
                "action": "অবিলম্বে ফ্রড রিস্ক টিমে এস্কেলেট করুন এবং রিপোর্টেড নম্বরটি রেকর্ড করুন।",
                "reply": "কোনো তথ্য শেয়ার না করেই আমাদের জানানোর জন্য ধন্যবাদ। আমরা কখনো পিন, ওটিপি বা পাসওয়ার্ড চাই না। এমন কারো সাথে এই তথ্য শেয়ার করবেন না যারা আমাদের প্রতিনিধি বলে দাবি করেন। আমাদের ফ্রড টিম বিষয়টি নিয়ে কাজ করছে।",
            },
        },
        "other": {
            "en": {
                "summary": "Customer reports a vague concern without sufficient detail to identify the affected transaction or issue type.",
                "action": "Reply to customer requesting specific details: which transaction, what amount, what went wrong, and approximate time.",
                "reply": "Thank you for reaching out. To help you faster, please share the transaction ID, the amount involved, and a short description of what went wrong. Please do not share your PIN or OTP with anyone.",
            },
            "bn": {
                "summary": "গ্রাহক অস্পষ্ট অভিযোগ করেছেন যা থেকে নির্দিষ্ট সমস্যা চিহ্নিত করা সম্ভব হয়নি।",
                "action": "গ্রাহককে নির্দিষ্ট তথ্য (লেনদেন আইডি, পরিমাণ, সমস্যার বিবরণ) জিজ্ঞাসা করুন।",
                "reply": "আপনার অভিযোগের জন্য ধন্যবাদ। দ্রুত সাহায্য করতে, অনুগ্রহ করে লেনদেন আইডি, পরিমাণ এবং কী সমস্যা হয়েছে তা জানান। পিন বা ওটিপি কারো সাথে শেয়ার করবেন না।",
            },
        },
    }

    lang_key = "bn" if is_bangla else "en"
    case_templates = templates.get(case_type, templates["other"])
    if case_type == "wrong_transfer" and not relevant_txn_id and evidence_verdict == "insufficient_data":
        tmpl = case_templates.get("ambiguous_en", case_templates.get(lang_key, templates["other"]["en"]))
    else:
        tmpl = case_templates.get(lang_key, templates["other"]["en"])

    return tmpl["summary"], tmpl["action"], tmpl["reply"]


def _is_bangla(text: str) -> bool:
    """Detect if text contains significant Bangla characters."""
    bangla_chars = sum(1 for c in text if 0x0980 <= ord(c) <= 0x09FF)
    return bangla_chars > 3
