"""
Playground — audio transcription endpoint for the dashboard test UI.
Accepts an audio file upload, transcribes locally with faster-whisper,
and returns the plain text so the frontend can include it in a proxy request.
"""
import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from faster_whisper import WhisperModel

from app.config import settings

router = APIRouter()

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    return _model


@router.post("/playground/audio")
async def transcribe_audio(file: UploadFile = File(...)) -> dict:
    """Transcribe an uploaded audio file and return the text."""
    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        model = _get_model()
        segments, _ = model.transcribe(tmp_path, word_timestamps=False)
        text = " ".join(seg.text.strip() for seg in segments)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        os.unlink(tmp_path)

    return {"text": text}
