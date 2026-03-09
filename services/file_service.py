from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz
from docx import Document
from telegram import Update
from telegram.ext import ContextTypes

from config import SETTINGS


@dataclass
class ParsedUpload:
    source_kind: str
    file_name: str
    mime_type: str
    telegram_file_id: str | None
    telegram_file_unique_id: str | None
    file_size: int
    text: str
    preview_text: str
    page_count: int
    content_hash: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str) -> list[dict]:
    if not text.strip():
        return []
    out = []
    step = max(1, SETTINGS.max_chunk_chars - SETTINGS.chunk_overlap)
    idx = 0
    for start in range(0, len(text), step):
        chunk = text[start:start + SETTINGS.max_chunk_chars].strip()
        if chunk:
            out.append({"chunk_index": idx, "chunk_text": chunk, "source_page": "", "source_section": ""})
            idx += 1
    return out


def _read_pdf(path: Path) -> tuple[str, int]:
    doc = fitz.open(path)
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    return "\n\n".join(pages), len(doc)


def _read_docx(path: Path) -> tuple[str, int]:
    doc = Document(path)
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(lines), len(lines)


def _read_txt(path: Path) -> tuple[str, int]:
    return path.read_text(encoding="utf-8", errors="ignore"), 1


async def download_to_tmp(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str, suffix: str) -> Path:
    tg_file = await context.bot.get_file(file_id)
    path = SETTINGS.files_tmp_dir / f"{file_id}{suffix}"
    await tg_file.download_to_drive(custom_path=str(path))
    return path


async def parse_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, vision_to_text, audio_to_text) -> Optional[ParsedUpload]:
    msg = update.effective_message
    if not msg:
        return None

    if msg.document:
        doc = msg.document
        suffix = Path(doc.file_name or "file").suffix or ".bin"
        path = await download_to_tmp(update, context, doc.file_id, suffix)
        mime = doc.mime_type or "application/octet-stream"
        text = ""
        pages = 1
        if suffix.lower() == ".pdf":
            text, pages = _read_pdf(path)
        elif suffix.lower() == ".docx":
            text, pages = _read_docx(path)
        elif suffix.lower() in {".txt", ".md", ".csv"}:
            text, pages = _read_txt(path)
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
        return ParsedUpload(
            source_kind="document",
            file_name=doc.file_name or "document",
            mime_type=mime,
            telegram_file_id=doc.file_id,
            telegram_file_unique_id=doc.file_unique_id,
            file_size=doc.file_size or 0,
            text=text.strip(),
            preview_text=text.strip()[: SETTINGS.max_preview_chars],
            page_count=pages,
            content_hash=sha256_text(text.strip()),
        )

    if msg.photo:
        photo = msg.photo[-1]
        path = await download_to_tmp(update, context, photo.file_id, ".jpg")
        text = await vision_to_text(path)
        return ParsedUpload(
            source_kind="photo",
            file_name="photo.jpg",
            mime_type="image/jpeg",
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            file_size=photo.file_size or 0,
            text=text.strip(),
            preview_text=text.strip()[: SETTINGS.max_preview_chars],
            page_count=1,
            content_hash=sha256_text(text.strip()),
        )

    if msg.voice:
        voice = msg.voice
        path = await download_to_tmp(update, context, voice.file_id, ".ogg")
        text = await audio_to_text(path)
        return ParsedUpload(
            source_kind="voice",
            file_name="voice.ogg",
            mime_type="audio/ogg",
            telegram_file_id=voice.file_id,
            telegram_file_unique_id=voice.file_unique_id,
            file_size=voice.file_size or 0,
            text=text.strip(),
            preview_text=text.strip()[: SETTINGS.max_preview_chars],
            page_count=1,
            content_hash=sha256_text(text.strip()),
        )

    if msg.text:
        text = msg.text.strip()
        return ParsedUpload(
            source_kind="text",
            file_name="Matn",
            mime_type="text/plain",
            telegram_file_id=None,
            telegram_file_unique_id=None,
            file_size=len(text.encode("utf-8")),
            text=text,
            preview_text=text[: SETTINGS.max_preview_chars],
            page_count=1,
            content_hash=sha256_text(text),
        )
    return None
