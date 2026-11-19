import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.services import face_service

router = APIRouter(prefix="/api", tags=["Face (optional server-side)"])
_pool = ThreadPoolExecutor(max_workers=2)
ALLOWED = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 6 * 1024 * 1024


async def _read(f: UploadFile):
    if f.content_type not in ALLOWED:
        raise HTTPException(415, f"Unsupported image type {f.content_type}")
    data = await f.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image larger than 6 MB")
    try:
        return face_service.decode_image(data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/face-analyze")
async def face_analyze(image: UploadFile = File(...)):
    img = await _read(image)
    return await asyncio.get_running_loop().run_in_executor(_pool, face_service.analyze, img)


@router.post("/face-verify")
async def face_verify(img1: UploadFile = File(...), img2: UploadFile = File(...)):
    a, b = await _read(img1), await _read(img2)
    return await asyncio.get_running_loop().run_in_executor(_pool, face_service.verify, a, b)
