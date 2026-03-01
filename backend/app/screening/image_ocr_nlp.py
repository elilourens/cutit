"""
Image PII screening — OCR + NLP pipeline (no LLM):
  Step 1: MediaPipe face detection  → tight face bounding boxes
  Step 2: EasyOCR                   → per-word text + pixel coords
  Step 3: Presidio (same as text)   → flag PII words
  Step 4: Pillow                    → black out flagged regions

Same public interface as image.py — swap by changing the import in router.py.
"""
import base64
from io import BytesIO
from typing import Dict, List, Tuple

import easyocr
import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw
from presidio_analyzer import AnalyzerEngine

from app.screening.entity_settings import get as get_entities

# ── One-time initialisation (module load) ─────────────────────────────────────
_analyzer = AnalyzerEngine()
_ocr = easyocr.Reader(["en"], gpu=False, verbose=False)
_face_detector = mp.solutions.face_detection.FaceDetection(
    model_selection=1,          # 1 = full-range model (works beyond 2 m)
    min_detection_confidence=0.5,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _b64_to_pil(image_b64: str) -> Image.Image:
    return Image.open(BytesIO(base64.b64decode(image_b64))).convert("RGB")


def _pil_to_np(img: Image.Image) -> np.ndarray:
    return np.array(img)


def _detect_faces(img_np: np.ndarray, img_w: int, img_h: int) -> List[Dict]:
    """Return normalised face regions via MediaPipe."""
    results = _face_detector.process(img_np)
    regions = []
    if not results.detections:
        return regions
    for det in results.detections:
        bb = det.location_data.relative_bounding_box
        regions.append({
            "label": "face",
            "x": max(0.0, bb.xmin),
            "y": max(0.0, bb.ymin),
            "w": min(1.0 - max(0.0, bb.xmin), bb.width),
            "h": min(1.0 - max(0.0, bb.ymin), bb.height),
        })
    return regions


def _detect_text_pii(img_np: np.ndarray, img_w: int, img_h: int) -> List[Dict]:
    """
    OCR the image, run Presidio on the extracted text, return normalised
    bounding boxes for every word that falls inside a flagged PII span.
    """
    ocr_results = _ocr.readtext(img_np, detail=1, paragraph=False)
    if not ocr_results:
        return []

    # Build a flat string of all words keeping track of their positions
    words: List[Dict] = []   # {text, start, end, bbox_px}
    flat_parts: List[str] = []
    cursor = 0

    for (quad, text, _conf) in ocr_results:
        # quad: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)

        # Split into individual words so Presidio can flag substrings
        for word in text.split():
            start = cursor
            end = cursor + len(word)
            words.append({"text": word, "start": start, "end": end,
                          "x1": x1, "y1": y1, "x2": x2, "y2": y2})
            flat_parts.append(word)
            cursor = end + 1   # +1 for the space separator

    flat_text = " ".join(flat_parts)

    active_entities = [e for e in get_entities("image") if e != "FACE"]
    if not active_entities:
        return []
    hits = _analyzer.analyze(text=flat_text, entities=active_entities, language="en")

    regions = []
    for hit in hits:
        for word in words:
            # Does this word's span overlap the Presidio hit?
            if word["end"] <= hit.start or word["start"] >= hit.end:
                continue
            regions.append({
                "label": hit.entity_type,
                "x": word["x1"] / img_w,
                "y": word["y1"] / img_h,
                "w": (word["x2"] - word["x1"]) / img_w,
                "h": (word["y2"] - word["y1"]) / img_h,
            })

    return regions


def _redact(img: Image.Image, regions: List[Dict]) -> str:
    """Black out normalised regions. Returns base64 JPEG."""
    w, h = img.size
    draw = ImageDraw.Draw(img)
    for r in regions:
        x1 = int(r["x"] * w)
        y1 = int(r["y"] * h)
        x2 = int((r["x"] + r["w"]) * w)
        y2 = int((r["y"] + r["h"]) * h)
        draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


# ── Public API (same signature as image.py) ───────────────────────────────────

async def screen_image(image_b64: str) -> Tuple[str, List[Dict]]:
    """
    Screen and redact a base64-encoded image using face detection + OCR/NLP.
    Returns (redacted_b64, regions_found).
    """
    img = _b64_to_pil(image_b64)
    img_np = _pil_to_np(img)
    w, h = img.size

    active = get_entities("image")
    if not active:
        return image_b64, []
    face_regions = _detect_faces(img_np, w, h) if "FACE" in active else []
    regions = face_regions + _detect_text_pii(img_np, w, h)

    if not regions:
        return image_b64, []

    redacted = _redact(img, regions)
    return redacted, regions
