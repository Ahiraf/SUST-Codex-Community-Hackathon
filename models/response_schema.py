"""
Response schema for POST /analyze-ticket.
Matches the specification exactly from the problem statement.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class AnalyzeTicketResponse(BaseModel):
    ticket_id: str = Field(..., description="Must match the value sent in the request.")
    relevant_transaction_id: Optional[str] = Field(
        None,
        description="Transaction ID the complaint refers to, or null if none in the provided history matches."
    )
    evidence_verdict: str = Field(
        ...,
        description="One of: consistent, inconsistent, insufficient_data."
    )
    case_type: str = Field(
        ...,
        description="One of the case_type enum values."
    )
    severity: str = Field(
        ...,
        description="One of: low, medium, high, critical."
    )
    department: str = Field(
        ...,
        description="One of the department enum values."
    )
    agent_summary: str = Field(
        ...,
        description="Concise agent-ready summary of the case (one to two sentences)."
    )
    recommended_next_action: str = Field(
        ...,
        description="Suggested operational next step for the support agent."
    )
    customer_reply: str = Field(
        ...,
        description="Safe official reply that respects all safety rules."
    )
    human_review_required: bool = Field(
        ...,
        description="True for disputes, suspicious cases, high-value cases, or ambiguous evidence."
    )
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    reason_codes: Optional[List[str]] = Field(default_factory=list)
