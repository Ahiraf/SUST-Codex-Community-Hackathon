"""
Request schema for POST /analyze-ticket.
Matches the specification exactly from the problem statement.
"""
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class TransactionHistoryEntry(BaseModel):
    transaction_id: str
    timestamp: str
    type: str  # transfer, payment, cash_in, cash_out, settlement, refund
    amount: float
    counterparty: str
    status: str  # completed, failed, pending, reversed


class AnalyzeTicketRequest(BaseModel):
    ticket_id: str = Field(..., description="Unique ticket identifier. Must be echoed in the response.")
    complaint: str = Field(..., description="Customer complaint text in English, Bangla, or mixed Banglish.")
    language: Optional[str] = Field(None, description="One of: en, bn, mixed.")
    channel: Optional[str] = Field(None, description="One of: in_app_chat, call_center, email, merchant_portal, field_agent.")
    user_type: Optional[str] = Field(None, description="One of: customer, merchant, agent, unknown.")
    campaign_context: Optional[str] = Field(None, description="Campaign identifier provided by the harness.")
    transaction_history: Optional[List[TransactionHistoryEntry]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(None)
