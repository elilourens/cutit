"""
Shared in-memory store for active Presidio entity lists per modality.
Each modality (text, image, audio) has its own independently configurable list.
"""
from typing import Dict, List

# Every entity available for selection in the UI
ALL_ENTITIES: List[str] = [
    "FACE",
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "LOCATION",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
    "US_SSN",
    "US_PASSPORT",
    "US_BANK_NUMBER",
    "US_DRIVER_LICENSE",
    "DATE_TIME",
    "NRP",
    "URL",
    "MEDICAL_LICENSE",
    "CRYPTO",
    "UK_NHS",
]

_DEFAULTS: Dict[str, List[str]] = {
    "text": [
        "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION",
        "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS", "US_SSN", "US_PASSPORT",
        "DATE_TIME", "NRP", "URL", "MEDICAL_LICENSE",
    ],
    "image": [
        "FACE", "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE",
        "IP_ADDRESS", "US_SSN", "US_PASSPORT", "MEDICAL_LICENSE", "NRP",
    ],
    "audio": [
        "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION",
        "CREDIT_CARD", "US_SSN", "DATE_TIME",
    ],
}

_active: Dict[str, List[str]] = {k: list(v) for k, v in _DEFAULTS.items()}


def get(modality: str) -> List[str]:
    """Return the active entity list for a modality."""
    return list(_active.get(modality, []))


def get_all() -> Dict[str, List[str]]:
    return {k: list(v) for k, v in _active.items()}


def set_all(text: List[str], image: List[str], audio: List[str]) -> None:
    _active["text"] = [e for e in text if e in ALL_ENTITIES and e != "FACE"]
    _active["image"] = [e for e in image if e in ALL_ENTITIES]
    _active["audio"] = [e for e in audio if e in ALL_ENTITIES and e != "FACE"]


def reset() -> Dict[str, List[str]]:
    """Reset all modalities to their default entity lists."""
    _active["text"] = list(_DEFAULTS["text"])
    _active["image"] = list(_DEFAULTS["image"])
    _active["audio"] = list(_DEFAULTS["audio"])
    return get_all()
