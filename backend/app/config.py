from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai"
    elevenlabs_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral:latest"
    whisper_model: str = "tiny"
    log_level: str = "INFO"


settings = Settings()
