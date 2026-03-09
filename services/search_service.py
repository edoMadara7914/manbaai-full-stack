from __future__ import annotations

import math
from typing import Any

from db import DB
from services.openai_service import OpenAIService


class SearchService:
    def __init__(self, ai: OpenAIService) -> None:
        self.ai = ai

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if not na or not nb:
            return 0.0
        return dot / (na * nb)

    def search_scope(self, user_id: int, scope: str, question: str, top_k: int = 5) -> dict[str, Any]:
        docs = DB.list_searchable_documents(user_id, scope)
        if not docs:
            return {"context": "", "source": "topilmadi", "doc_ids": []}
        q_emb = self.ai.embed_texts([question])[0]
        scored: list[tuple[float, dict]] = []
        for row in docs:
            emb = DB.deserialize_embedding(row["embedding_json"])
            score = self.cosine(q_emb, emb)
            scored.append((score, dict(row)))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [row for _, row in scored[:top_k] if row.get("chunk_text")]
        if not selected:
            return {"context": "", "source": "topilmadi", "doc_ids": []}
        ctx_lines = []
        sources = []
        doc_ids = []
        for row in selected:
            source = row.get("display_name") or row.get("file_name") or "Noma'lum fayl"
            page = row.get("source_page") or row.get("section_hint") or row.get("source_section") or "bo'lim ko'rsatilmagan"
            ctx_lines.append(f"[{source} | {page}]\n{row['chunk_text']}")
            sources.append(f"{source} — {page}")
            doc_ids.append(row["document_id"])
        return {"context": "\n\n".join(ctx_lines), "source": "; ".join(sources[:3]), "doc_ids": doc_ids}
