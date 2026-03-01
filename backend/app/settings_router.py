"""
Settings API — read and persist API keys to .env without restarting.
"""
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.screening.entity_settings import ALL_ENTITIES, get_all, set_all, reset as reset_entities

router = APIRouter()

_ENV_PATH = Path(".env")


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "●" * len(key)
    return key[:4] + "●" * 8 + key[-4:]


def _write_env(**updates: str) -> None:
    """Update or add keys in the .env file without touching other lines."""
    lines: list[str] = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()

    written: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip().upper()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)

    for key, value in updates.items():
        if key not in written:
            new_lines.append(f"{key}={value}")

    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


class SettingsPayload(BaseModel):
    mistral_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    mistral_base_url: str | None = None


@router.get("/settings")
async def get_settings():
    return {
        "mistral_api_key": _mask(settings.mistral_api_key),
        "elevenlabs_api_key": _mask(settings.elevenlabs_api_key),
        "mistral_base_url": settings.mistral_base_url,
        "has_mistral_key": bool(settings.mistral_api_key),
        "has_elevenlabs_key": bool(settings.elevenlabs_api_key),
    }


@router.post("/settings")
async def save_settings(body: SettingsPayload):
    env_updates: dict[str, str] = {}

    if body.mistral_api_key is not None:
        settings.mistral_api_key = body.mistral_api_key
        env_updates["MISTRAL_API_KEY"] = body.mistral_api_key

    if body.elevenlabs_api_key is not None:
        settings.elevenlabs_api_key = body.elevenlabs_api_key
        env_updates["ELEVENLABS_API_KEY"] = body.elevenlabs_api_key

    if body.mistral_base_url is not None:
        settings.mistral_base_url = body.mistral_base_url
        env_updates["MISTRAL_BASE_URL"] = body.mistral_base_url

    if env_updates:
        _write_env(**env_updates)

    return {"saved": True}


# ── Screening entity settings ──────────────────────────────────────────────────

class EntityPayload(BaseModel):
    text: list[str]
    image: list[str]
    audio: list[str]


@router.get("/settings/entities")
async def get_entity_settings():
    return {"entities": get_all(), "all_entities": ALL_ENTITIES}


@router.post("/settings/entities")
async def save_entity_settings(body: EntityPayload):
    set_all(body.text, body.image, body.audio)
    return {"saved": True}


@router.post("/settings/entities/reset")
async def reset_entity_settings():
    return {"entities": reset_entities()}
