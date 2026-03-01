from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Cloud provider API keys
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    xai_api_key: str = ""

    # Audio
    elevenlabs_api_key: str = ""

    # Local models
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral:latest"
    whisper_model: str = "tiny"
    log_level: str = "INFO"


settings = Settings()
