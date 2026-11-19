from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.services.answer_normalizer import AnswerNormalizer
from backend.services.form_schema import public_schema
from backend.services.pdf_parser_service import PDFParserService
from backend.services.question_engine import QuestionEngine

router = APIRouter(prefix="/api", tags=["Assistant"])
engine = QuestionEngine()
normalizer = AnswerNormalizer()
pdf_parser = PDFParserService()
MAX_PDF_BYTES = 8 * 1024 * 1024


class NextQuestionRequest(BaseModel):
    language: str = "en"
    field_keys: Optional[List[str]] = None
    answers: Dict[str, Any] = Field(default_factory=dict)
    skipped: List[str] = Field(default_factory=list)


class MapAnswerRequest(BaseModel):
    field_key: str
    raw_answer: str
    language: str = "en"
    field_type: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


@router.get("/form/schema")
def form_schema():
    return public_schema()


@router.post("/assistant/next-question")
def next_question(req: NextQuestionRequest):
    return engine.get_next_question(req.field_keys, req.answers, req.language, req.skipped)


@router.post("/assistant/map-answer")
def map_answer(req: MapAnswerRequest):
    return normalizer.normalize(req.field_key, req.raw_answer[:500], req.language, req.field_type, req.context)


@router.post("/pdf/parse")
async def parse_pdf(file: UploadFile = File(...)):
    name = (file.filename or "").lower()
    if not name.endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF file.")
    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF is larger than 8 MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "This file is not a valid PDF.")
    return pdf_parser.parse_pdf(data)
