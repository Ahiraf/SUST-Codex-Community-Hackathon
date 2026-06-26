"""
QueueStorm Investigator — Main FastAPI Application

Endpoints:
  GET  /health          → {"status": "ok"}
  POST /analyze-ticket  → Full structured analysis JSON

Starts on PORT env var (default 8000), binds to 0.0.0.0.
"""
import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from models.request_schema import AnalyzeTicketRequest
from models.response_schema import AnalyzeTicketResponse
from analyzer.response_builder import build_response

# ──────────────────────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("queuestorm")


# ──────────────────────────────────────────────────────────────
# App lifecycle
# ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("QueueStorm Investigator starting up...")
    yield
    logger.info("QueueStorm Investigator shutting down...")


# ──────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="QueueStorm Investigator",
    description=(
        "AI/API service for fintech support ticket classification, "
        "evidence reasoning, routing, and safe customer reply generation."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────────────────────
# Exception handlers
# ──────────────────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return 400 with a clear, non-sensitive error message for malformed input."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error.get("loc", []))
        msg = error.get("msg", "validation error")
        errors.append(f"{field}: {msg}")

    return JSONResponse(
        status_code=400,
        content={
            "error": "Invalid request body",
            "details": errors[:5],  # Limit details to avoid verbose stack traces
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Return 500 with a non-sensitive error message. Never expose stack traces."""
    logger.exception(f"Unhandled error on {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error. Please try again later."},
    )


# ──────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────
@app.get("/health", summary="Health check")
async def health_check():
    """
    Returns {"status": "ok"} to indicate the service is running.
    The judge harness calls this before sending test cases.
    """
    return {"status": "ok"}


@app.post(
    "/analyze-ticket",
    response_model=AnalyzeTicketResponse,
    summary="Analyze a support ticket",
    responses={
        200: {"description": "Successful analysis"},
        400: {"description": "Malformed input"},
        422: {"description": "Semantically invalid input"},
        500: {"description": "Internal server error"},
    },
)
async def analyze_ticket(request: AnalyzeTicketRequest):
    """
    Accepts one support ticket with complaint text and transaction history.
    Returns a structured JSON analysis including:
    - Case classification and severity
    - Department routing
    - Evidence verdict (consistent / inconsistent / insufficient_data)
    - Safe customer reply (no PIN/OTP requests, no refund promises)
    - Human escalation flag
    """
    # Semantic validation: complaint must not be empty
    if not request.complaint or not request.complaint.strip():
        return JSONResponse(
            status_code=422,
            content={"error": "Complaint text must not be empty."},
        )

    # Validate ticket_id
    if not request.ticket_id or not request.ticket_id.strip():
        return JSONResponse(
            status_code=422,
            content={"error": "ticket_id must not be empty."},
        )

    try:
        response = build_response(request)
        return response
    except ValidationError as e:
        logger.error(f"Response validation error for ticket {request.ticket_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error during response generation."},
        )
    except Exception as e:
        logger.exception(f"Error analyzing ticket {request.ticket_id}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error. Please try again later."},
        )


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=False,
    )
