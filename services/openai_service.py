from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from openai import APIError, AuthenticationError, OpenAI, RateLimitError

from config import SETTINGS


class OpenAIService:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=SETTINGS.openai_api_key) if SETTINGS.openai_api_key else None

    def available(self) -> bool:
        return self.client is not None

    def detect_language(self, text: str) -> str:
        lowered = (text or "").lower()
        if any(ch in lowered for ch in ["qanday", "nima", "bo'lim", "sahifa", "ma'lumot"]):
            return "uz"
        if any(ch in lowered for ch in ["что", "как", "данные", "страница"]):
            return "ru"
        return "en" if any("a" <= c <= "z" for c in lowered) else "uz"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.client or not texts:
            return [[0.0] * 8 for _ in texts]
        try:
            resp = self.client.embeddings.create(model=SETTINGS.openai_embed_model, input=texts)
            return [row.embedding for row in resp.data]
        except Exception:
            return [[0.0] * 8 for _ in texts]

    async def image_to_text(self, path: Path) -> str:
        if not self.client:
            return ""
        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        try:
            resp = self.client.responses.create(
                model=SETTINGS.openai_vision_model,
                input=[{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Extract and summarize the visible text in Uzbek. Return plain text only."},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"},
                    ],
                }],
            )
            return getattr(resp, "output_text", "") or ""
        except Exception:
            return ""

    async def transcribe_audio(self, path: Path) -> str:
        if not self.client:
            return ""
        try:
            with path.open("rb") as fh:
                resp = self.client.audio.transcriptions.create(
                    model=SETTINGS.openai_transcribe_model,
                    file=fh,
                )
            text = getattr(resp, "text", None)
            if isinstance(text, str):
                return text
            return str(resp)
        except Exception:
            return ""

    def answer_from_context(self, question: str, private_context: str, public_context: str, answer_lang: str) -> dict[str, Any]:
        no_data = "Ma'lumot topilmadi."
        if not self.client:
            return {
                "private": {"short_answer": no_data, "details": "OpenAI API ulanmagan.", "source": "topilmadi"},
                "public": {"short_answer": no_data, "details": "OpenAI API ulanmagan.", "source": "topilmadi"},
            }

        prompt = (
            "You are ManbaAI. Answer only from provided contexts. "
            "Never mention OpenAI or GPT. Output strict JSON with keys private and public. "
            "Each block must have short_answer, details, source. "
            "If not found, use 'Ma\'lumot topilmadi.' and source 'topilmadi'. "
            f"Answer language preference: {answer_lang}.\n\n"
            f"QUESTION:\n{question}\n\n"
            f"PRIVATE_CONTEXT:\n{private_context or 'NONE'}\n\n"
            f"PUBLIC_CONTEXT:\n{public_context or 'NONE'}"
        )
        try:
            resp = self.client.responses.create(
                model=SETTINGS.openai_chat_model,
                input=prompt,
                text={"format": {"type": "json_object"}},
            )
            raw = getattr(resp, "output_text", "") or "{}"
            data = json.loads(raw)
            return data
        except RateLimitError:
            return {
                "private": {"short_answer": no_data, "details": "AI limiti yoki quota tugagan.", "source": "AI xizmati"},
                "public": {"short_answer": no_data, "details": "AI limiti yoki quota tugagan.", "source": "AI xizmati"},
            }
        except AuthenticationError:
            return {
                "private": {"short_answer": no_data, "details": "API kalit xatosi.", "source": "AI xizmati"},
                "public": {"short_answer": no_data, "details": "API kalit xatosi.", "source": "AI xizmati"},
            }
        except (APIError, json.JSONDecodeError, Exception):
            return {
                "private": {"short_answer": no_data, "details": "Javob tayyorlashda xatolik bo'ldi.", "source": "AI xizmati"},
                "public": {"short_answer": no_data, "details": "Javob tayyorlashda xatolik bo'ldi.", "source": "AI xizmati"},
            }
