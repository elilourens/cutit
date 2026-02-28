"""
Image PII screening — two-step pipeline:
  Step 1: Ollama/Ministral vision identifies sensitive regions (local)
  Step 2: Pillow blacks them out (local)
Only the redacted image is ever forwarded to Mistral cloud.
"""
import base64
import json
import re
from io import BytesIO
from typing import Dict, List, Tuple

import ollama
from PIL import Image, ImageDraw

from app.config import settings


async def _detect_regions(image_b64: str) -> List[Dict]:
    """
    Ask local Ollama vision to return normalised bounding boxes for sensitive content.
    Returns list of {"label": str, "x": float, "y": float, "w": float, "h": float}
    where all coords are in the 0–1 range (top-left origin).
    """
    prompt = (
        "You are a privacy scanner. Look at this image for sensitive or personally "
        "identifying content: faces, names, IDs, documents, license plates, "
        "addresses, financial information, medical records.\n"
        "Return ONLY a JSON array. Each item must have:\n"
        '  {"label": "<what it is>", "x": <0-1>, "y": <0-1>, "w": <0-1>, "h": <0-1>}\n'
        "where x,y is the top-left corner and w,h are width/height, all normalised 0–1.\n"
        "If nothing sensitive is found, return []."
    )
    try:
        resp = ollama.generate(
            model=settings.ollama_model,
            prompt=prompt,
            images=[image_b64],
            options={"temperature": 0.1},
        )
        raw = resp["response"].strip()
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if m:
            regions = json.loads(m.group())
            # Validate and clamp values
            cleaned = []
            for r in regions:
                if all(k in r for k in ("x", "y", "w", "h")):
                    cleaned.append(
                        {
                            "label": r.get("label", "sensitive"),
                            "x": max(0.0, min(1.0, float(r["x"]))),
                            "y": max(0.0, min(1.0, float(r["y"]))),
                            "w": max(0.0, min(1.0, float(r["w"]))),
                            "h": max(0.0, min(1.0, float(r["h"]))),
                        }
                    )
            return cleaned
    except Exception:
        pass
    return []


def _redact_image(image_b64: str, regions: List[Dict]) -> str:
    """Black out the specified normalised regions. Returns new base64 JPEG."""
    img_data = base64.b64decode(image_b64)
    img = Image.open(BytesIO(img_data)).convert("RGB")
    w, h = img.size

    draw = ImageDraw.Draw(img)
    for region in regions:
        x1 = int(region["x"] * w)
        y1 = int(region["y"] * h)
        x2 = int((region["x"] + region["w"]) * w)
        y2 = int((region["y"] + region["h"]) * h)
        draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0))

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


async def screen_image(image_b64: str) -> Tuple[str, List[Dict]]:
    """
    Screen and redact a base64-encoded image.
    Returns (redacted_b64, regions_found).
    """
    regions = await _detect_regions(image_b64)
    if not regions:
        return image_b64, []
    redacted = _redact_image(image_b64, regions)
    return redacted, regions
