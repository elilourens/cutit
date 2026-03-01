"""
Audio PII screening — three-step pipeline:
  Step 1: sounddevice captures mic locally
  Step 2: Whisper tiny transcribes with word timestamps (local)
  Step 3: Text pipeline screens transcription; flagged words → 1 kHz bleep (local)
Only bleeped audio leaves the machine.
"""
import os
import tempfile
from typing import Dict, List, Tuple

import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav_io
from faster_whisper import WhisperModel

from app.config import settings

SAMPLE_RATE = 16_000  # Hz — Whisper expects 16 kHz mono
BLEEP_FREQ = 1_000    # Hz — classic bleep tone

_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    return _whisper_model


# ── Capture ───────────────────────────────────────────────────────────────────

def record_audio(duration: int = 10) -> np.ndarray:
    """Block and record *duration* seconds from the default mic. Returns float32 mono."""
    audio = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return audio.squeeze()


# ── Transcription ─────────────────────────────────────────────────────────────

def transcribe(audio: np.ndarray) -> List[Dict]:
    """
    Transcribe *audio* with word-level timestamps using local Whisper.
    Returns list of {"word": str, "start": float, "end": float}.
    """
    model = _get_whisper()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_io.write(f.name, SAMPLE_RATE, (audio * 32_767).astype(np.int16))
        tmp_path = f.name

    try:
        segments, _ = model.transcribe(tmp_path, word_timestamps=True)
        words = []
        for seg in segments:
            for w in seg.words:
                words.append({"word": w.word.strip(), "start": w.start, "end": w.end})
    finally:
        os.unlink(tmp_path)

    return words


# ── Bleep ─────────────────────────────────────────────────────────────────────

def bleep_segments(audio: np.ndarray, segments: List[Dict]) -> np.ndarray:
    """Replace each segment with a 1 kHz sine bleep in-place (copy returned)."""
    audio = audio.copy()
    for seg in segments:
        start = int(seg["start"] * SAMPLE_RATE)
        end = int(seg["end"] * SAMPLE_RATE)
        n = end - start
        if n <= 0:
            continue
        t = np.linspace(0, n / SAMPLE_RATE, n, endpoint=False)
        audio[start:end] = (0.4 * np.sin(2 * np.pi * BLEEP_FREQ * t)).astype(audio.dtype)
    return audio


# ── Public API ────────────────────────────────────────────────────────────────

async def screen_audio(
    audio: np.ndarray, session_id: str
) -> Tuple[np.ndarray, str, List[Dict]]:
    """
    Full audio screening pipeline.
    Returns (bleeped_audio, redacted_transcript, findings).
    """
    from app.screening.text import screen_text
    from app.screening.entity_settings import get as get_entities

    if not get_entities("audio"):
        return audio, "", []

    word_infos = transcribe(audio)
    full_text = " ".join(w["word"] for w in word_infos)

    redacted_text, findings = await screen_text(full_text, session_id, entities=get_entities("audio"))

    # Identify which words were replaced (no longer present verbatim in redacted text)
    flagged = [w for w in word_infos if w["word"] and w["word"] not in redacted_text]

    bleeped = bleep_segments(audio, flagged)
    return bleeped, redacted_text, findings
