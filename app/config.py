"""PhantomAPI — Configuration via environment variables."""

from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env file or environment variables."""

    # --- Security ---
    # Set to empty string or "none" to disable authentication (local dev only)
    API_SECRET_KEY: str = "change-me-to-a-strong-secret"

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 7777

    # --- Browser Engine ---
    HEADLESS: bool = True
    BROWSER_TIMEOUT: int = 120000  # milliseconds

    # --- ChatGPT Session ---
    # Path to a saved Playwright storage-state JSON file (cookies + localStorage).
    # Run `python scripts/save_session.py` once while logged in to generate it.
    CHATGPT_STORAGE_STATE: Optional[str] = "chatgpt_session.json"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
