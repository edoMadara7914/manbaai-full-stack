from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item and item.strip()]


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    bot_username: str
    bot_name: str
    admin_user_ids: List[int]
    admin_contact_username: str
    database_path: Path
    files_tmp_dir: Path
    exports_dir: Path
    default_language: str
    openai_chat_model: str
    openai_embed_model: str
    openai_transcribe_model: str
    openai_vision_model: str
    max_chunk_chars: int
    chunk_overlap: int
    max_preview_chars: int
    basic_price_uzs: int
    premium_price_uzs: int
    basic_daily_limit: int
    premium_daily_limit: int
    free_daily_limit: int
    click_basic_url: str
    click_premium_url: str
    stars_basic_amount: int
    stars_premium_amount: int


def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / "data"
    tmp_dir = base_dir / os.getenv("FILES_TMP_DIR", "tmp")
    exports_dir = base_dir / os.getenv("EXPORTS_DIR", "exports")
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)
    db_path = base_dir / os.getenv("DATABASE_PATH", "data/manbaai.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        bot_username=os.getenv("BOT_USERNAME", "@ManbaAI_bot"),
        bot_name=os.getenv("BOT_NAME", "ManbaAI"),
        admin_user_ids=[int(x) for x in _split_csv(os.getenv("ADMIN_USER_IDS"))],
        admin_contact_username=os.getenv("ADMIN_CONTACT_USERNAME", "@ManbaAI_admin"),
        database_path=db_path,
        files_tmp_dir=tmp_dir,
        exports_dir=exports_dir,
        default_language=os.getenv("DEFAULT_LANGUAGE", "uz"),
        openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        openai_embed_model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
        openai_transcribe_model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"),
        openai_vision_model=os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini"),
        max_chunk_chars=int(os.getenv("MAX_CHUNK_CHARS", "1400")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
        max_preview_chars=int(os.getenv("MAX_PREVIEW_CHARS", "400")),
        basic_price_uzs=int(os.getenv("BASIC_PRICE_UZS", "12000")),
        premium_price_uzs=int(os.getenv("PREMIUM_PRICE_UZS", "25000")),
        basic_daily_limit=int(os.getenv("BASIC_DAILY_LIMIT", "20")),
        premium_daily_limit=int(os.getenv("PREMIUM_DAILY_LIMIT", "1000")),
        free_daily_limit=int(os.getenv("FREE_DAILY_LIMIT", "3")),
        click_basic_url=os.getenv("CLICK_BASIC_URL", ""),
        click_premium_url=os.getenv("CLICK_PREMIUM_URL", ""),
        stars_basic_amount=int(os.getenv("STARS_BASIC_AMOUNT", "120")),
        stars_premium_amount=int(os.getenv("STARS_PREMIUM_AMOUNT", "250")),
    )


SETTINGS = get_settings()
