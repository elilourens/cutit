"""
Playground — audio endpoints for the dashboard test UI.

/playground/audio             — local Whisper transcription only (quick preview)
/playground/audio/elevenlabs  — full privacy pipeline: screen for PII, bleep,
                                then forward bleeped WAV to ElevenLabs STT.
"""
import base64
import os
import tempfile
import uuid

import httpx
import numpy as np
import scipy.io.wavfile as wav_io
from fastapi import APIRouter, File, HTTPException, UploadFile
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

from app.config import settings
from app.ws.manager import manager

router = APIRouter()

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    return _model


def _decode_to_numpy(file_path: str) -> np.ndarray:
    """Decode any audio format → 16 kHz mono float32 ndarray using faster-whisper's PyAV decoder."""
    # decode_audio ships with faster-whisper and uses PyAV (bundled FFmpeg bindings),
    # so no system ffmpeg binary is needed.
    return decode_audio(file_path, sampling_rate=16_000)


@router.post("/playground/audio")
async def transcribe_audio(file: UploadFile = File(...)) -> dict:
    """Transcribe an uploaded audio file and return the text (local Whisper)."""
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


@router.post("/playground/audio/elevenlabs")
async def screen_and_send_elevenlabs(file: UploadFile = File(...)) -> dict:
    """
    Full audio privacy pipeline → ElevenLabs STT.

    Steps:
      1. Decode uploaded audio to 16 kHz mono via ffmpeg
      2. Transcribe locally with Whisper to locate PII words
      3. Bleep flagged segments in-place
      4. POST bleeped WAV to ElevenLabs speech-to-text
      5. Return ElevenLabs transcript + findings
    """
    if not settings.elevenlabs_api_key:
        raise HTTPException(status_code=400, detail="ELEVENLABS_API_KEY is not configured")

    session_id = str(uuid.uuid4())
    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"

    raw_bytes = await file.read()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw_bytes)
        upload_path = tmp.name

    # Encode original audio for the pipeline view (browser can play webm natively)
    mime = "audio/webm" if suffix == ".webm" else f"audio/{suffix.lstrip('.')}"
    original_audio_url = f"data:{mime};base64,{base64.b64encode(raw_bytes).decode()}"

    bleeped_path: str | None = None

    try:
        # ── Event: intercepted ────────────────────────────────────────────
        await manager.broadcast(
            "request_intercepted",
            {"path": "/playground/audio/elevenlabs", "method": "POST",
             "has_messages": False, "provider": "elevenlabs"},
            session_id,
        )

        # ── Decode audio ──────────────────────────────────────────────────
        try:
            audio_np = _decode_to_numpy(upload_path)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Audio decode failed: {exc}") from exc

        # ── Transcribe locally to get word timestamps + original text ────
        from app.screening.audio import bleep_segments, transcribe as whisper_transcribe
        from app.screening.text import screen_text
        from app.screening.entity_settings import get as get_entities

        await manager.broadcast("screening_started", {"message_count": 1}, session_id)

        word_infos = whisper_transcribe(audio_np)
        original_transcript = " ".join(w["word"] for w in word_infos)

        flagged: list = []
        entities = get_entities("audio")
        if entities:
            redacted_transcript, findings = await screen_text(
                original_transcript, session_id, entities=entities
            )
            flagged = [w for w in word_infos if w["word"] and w["word"] not in redacted_transcript]
            bleeped = bleep_segments(audio_np, flagged)
        else:
            redacted_transcript = original_transcript
            findings = []
            bleeped = audio_np
        redacted_segments = [{"start": w["start"], "end": w["end"]} for w in flagged]

        await manager.broadcast(
            "screening_done",
            {"findings_count": len(findings), "findings": findings, "vault_size": 0},
            session_id,
        )

        # ── Save bleeped WAV ──────────────────────────────────────────────
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as bleep_tmp:
            bleeped_path = bleep_tmp.name
        wav_io.write(bleeped_path, 16_000, (bleeped * 32_767).astype(np.int16))

        # ── Forward to ElevenLabs STT ─────────────────────────────────────
        target = "https://api.elevenlabs.io/v1/speech-to-text"
        await manager.broadcast(
            "forwarding",
            {"target": target, "provider": "elevenlabs", "redacted_count": len(findings)},
            session_id,
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(bleeped_path, "rb") as wav_fh:
                el_response = await client.post(
                    target,
                    headers={"xi-api-key": settings.elevenlabs_api_key},
                    files={"file": ("audio.wav", wav_fh, "audio/wav")},
                    data={"model_id": "scribe_v1"},
                )

        await manager.broadcast(
            "response_received",
            {"status": el_response.status_code, "bytes": len(el_response.content)},
            session_id,
        )

        if el_response.status_code != 200:
            raise HTTPException(
                status_code=el_response.status_code,
                detail=f"ElevenLabs error: {el_response.text[:300]}",
            )

        el_transcript = el_response.json().get("text", "")

        # Encode bleeped WAV for the pipeline view
        with open(bleeped_path, "rb") as wav_fh2:
            screened_audio_url = f"data:audio/wav;base64,{base64.b64encode(wav_fh2.read()).decode()}"

        # ── Pipeline snapshot ─────────────────────────────────────────────
        await manager.broadcast(
            "pipeline_snapshot",
            {
                "original": original_transcript or "(audio)",
                "screened": redacted_transcript,
                "original_audio": original_audio_url,
                "screened_audio": screened_audio_url,
                "cloud_response": el_transcript,
                "reconstructed": el_transcript,
                "findings": len(findings),
                "redacted_segments": redacted_segments,
                "vault": {},
                "provider": "elevenlabs",
            },
            session_id,
        )

        return {"text": el_transcript, "findings": findings, "session_id": session_id}

    finally:
        os.unlink(upload_path)
        if bleeped_path and os.path.exists(bleeped_path):
            os.unlink(bleeped_path)
