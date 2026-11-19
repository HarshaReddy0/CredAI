from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend import db
from backend.services.report_service import build_pdf

router = APIRouter(prefix="/api/applications", tags=["Applications"])


def _get(app_id: str) -> dict:
    rec = db.get_application(app_id)
    if not rec:
        raise HTTPException(404, "Application not found")
    rec.pop("pan_hash", None)
    return rec


@router.get("/{app_id}")
def get_application(app_id: str):
    return _get(app_id)


@router.get("/{app_id}/report.pdf")
def report(app_id: str):
    pdf = build_pdf(_get(app_id))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="CredAI-{app_id}.pdf"'})
