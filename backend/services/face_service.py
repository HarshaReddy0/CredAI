"""Optional server-side face analysis.

The browser already performs face detection, age estimate, face matching and
the liveness challenge with face-api.js, so the server works without any
heavy dependency. If DeepFace (TensorFlow) is installed, these endpoints add
a second, server-side opinion. OpenCV is used for a lightweight fallback
face-presence check."""
import threading

import numpy as np

from backend.config import ENABLE_DEEPFACE

_deepface = None
_deepface_state = "not_loaded"  # not_loaded | ready | unavailable | disabled
_lock = threading.Lock()


def deepface():
    global _deepface, _deepface_state
    if _deepface_state in ("ready", "unavailable", "disabled"):
        return _deepface
    with _lock:
        if ENABLE_DEEPFACE == "false":
            _deepface_state = "disabled"
            return None
        try:
            from deepface import DeepFace  # noqa: heavy import
            _deepface = DeepFace
            _deepface_state = "ready"
        except Exception:
            _deepface_state = "unavailable"
    return _deepface


def status() -> str:
    deepface()
    return _deepface_state


def _cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        return None


def decode_image(data: bytes):
    cv2 = _cv2()
    if cv2 is None:
        raise RuntimeError("opencv-python-headless is not installed")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")
    return img


def count_faces_opencv(img) -> int:
    cv2 = _cv2()
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    return len(faces)


def analyze(img) -> dict:
    brightness = float(np.mean(img))
    lighting = "good" if brightness > 110 else "ok" if brightness > 70 else "low"
    df = deepface()
    if df is not None:
        try:
            res = df.analyze(img, actions=["age", "gender", "emotion"], enforce_detection=False,
                             detector_backend="opencv", silent=True)
            res = res[0] if isinstance(res, list) else res
            return {"success": True, "engine": "deepface", "faces": 1 if res.get("face_confidence", 0) > 0.6 else 0,
                    "estimated_age": res.get("age"), "gender": res.get("dominant_gender"),
                    "emotion": res.get("dominant_emotion"), "lighting": lighting}
        except Exception as e:
            return {"success": False, "engine": "deepface", "error": str(e), "lighting": lighting}
    return {"success": True, "engine": "opencv", "faces": count_faces_opencv(img), "lighting": lighting,
            "estimated_age": None, "note": "Install deepface for age/emotion estimates."}


def verify(img1, img2) -> dict:
    df = deepface()
    if df is None:
        return {"success": False, "engine": None,
                "error": "Server-side face verification needs DeepFace. The browser performs matching instead."}
    try:
        r = df.verify(img1_path=img1, img2_path=img2, model_name="Facenet", detector_backend="opencv",
                      enforce_detection=False, silent=True)
        thr, dist = r.get("threshold", 0.4), r.get("distance", 1.0)
        return {"success": True, "engine": "deepface", "verified": bool(r.get("verified")),
                "distance": dist, "threshold": thr,
                "match_score": round(max(0.0, 1.0 - dist / (2 * thr)), 3) if thr else 0.0}
    except Exception as e:
        return {"success": False, "engine": "deepface", "error": str(e)}
