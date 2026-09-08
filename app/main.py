"""
FairSplit-AI: FastAPI entry point.

Endpoints:
  POST /api/upload-receipt   -> upload one or more receipt images, get ReceiptData
  POST /api/calculate-split  -> given a SplitRequest, compute SplitResponse
  GET  /health               -> liveness check
  GET  /                     -> serves the static single-page frontend
"""
from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import ReceiptData, SplitRequest, SplitResponse
from app.services import splitter
from app.services.vision_service import VisionServiceError, extract_receipt_data_multi

app = FastAPI(
    title="FairSplit-AI",
    description="Upload a receipt photo, let Gemini read it, and split the bill fairly.",
    version="0.1.0",
)

# --- CORS -------------------------------------------------------------------
# Wide open by default for local frontend development. Tighten allow_origins
# to your actual frontend domain(s) before deploying to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB per file


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/upload-receipt", response_model=ReceiptData, tags=["receipt"])
async def upload_receipt(files: list[UploadFile] = File(...)) -> ReceiptData:
    """
    Accepts one or more receipt images (e.g. a 2-page receipt) and returns
    the merged, structured ReceiptData with a code-verified math_is_valid flag.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    image_bytes_list: list[bytes] = []
    for f in files:
        if f.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=415, detail=f"Unsupported image type: {f.content_type}"
            )
        data = await f.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413, detail=f"File '{f.filename}' exceeds 10MB limit"
            )
        image_bytes_list.append(data)

    try:
        receipt = await extract_receipt_data_multi(image_bytes_list)
    except VisionServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return receipt


@app.post("/api/calculate-split", response_model=SplitResponse, tags=["split"])
async def calculate_split(payload: SplitRequest) -> SplitResponse:
    try:
        return splitter.compute_split(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Static frontend ---------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    return FileResponse("static/index.html")