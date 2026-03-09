from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import SETTINGS
from db import DB
from keyboards import (
    admin_menu,
    back_menu,
    file_actions_menu,
    language_keyboard,
    main_menu,
    moderation_keyboard,
    plan_buy_keyboard,
    save_scope_keyboard,
    subscription_keyboard,
    tariffs_keyboard,
)
from services.file_service import chunk_text, parse_upload
from services.openai_service import OpenAIService
from services.search_service import SearchService
from texts import t

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AI = OpenAIService()
SEARCH = SearchService(AI)
SELF_QA_TRIGGERS = [
    "sen kimsan", "seni kim yaratgan", "nima qila olasan", "qanday ishlaysan",
    "who are you", "who made you", "what can you do", "кто ты", "кто тебя создал",
]


async def ensure_user(update: Update) -> int:
    user = update.effective_user
    assert user is not None
    DB.upsert_user(user.id, user.username, user.full_name, user.language_code)
    DB.ensure_admin_roles()
    return user.id


async def is_subscribed(user_id: int, bot) -> bool:
    channels = DB.list_required_channels()
    if not channels:
        return True
    for row in channels:
        try:
            member = await bot.get_chat_member(row["telegram_chat_id"], user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except Exception:
            return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = await ensure_user(update)
    if context.args:
        try:
            referrer_id = int(context.args[0])
            DB.add_referral(user_id, referrer_id)
        except Exception:
            pass
    if not await is_subscribed(user_id, context.bot):
        channels = [dict(r) for r in DB.list_required_channels()]
        await update.effective_message.reply_text(t("uz", "need_subscription"), reply_markup=subscription_keyboard(channels))
        return
    await update.effective_message.reply_text(t("uz", "choose_language"), reply_markup=language_keyboard())


async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":", 1)[1]
    DB.set_interface_language(query.from_user.id, lang)
    is_admin = query.from_user.id in SETTINGS.admin_user_ids
    await query.message.reply_text(t(lang, "main_menu"), reply_markup=main_menu(lang, is_admin))


async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if await is_subscribed(query.from_user.id, context.bot):
        await query.message.reply_text(t("uz", "choose_language"), reply_markup=language_keyboard())
    else:
        await query.message.reply_text(t("uz", "need_subscription"))


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = await ensure_user(update)
    lang = DB.get_interface_language(user_id)
    text = (update.effective_message.text or "").strip()
    lower = text.lower()
    is_admin = user_id in SETTINGS.admin_user_ids
    mode = context.user_data.get("mode")

    if text == t(lang, "back"):
        context.user_data.clear()
        await update.effective_message.reply_text(t(lang, "main_menu"), reply_markup=main_menu(lang, is_admin))
        return

    # Global canned self-answers
    if any(trigger in lower for trigger in SELF_QA_TRIGGERS):
        await update.effective_message.reply_text(t(lang, "about"))
        return

    # Admin state handlers
    state = context.user_data.get("state")
    if state == "rename_wait_doc_id":
        if not text.isdigit():
            await update.effective_message.reply_text(t(lang, "invalid_id"))
            return
        doc = DB.get_document(int(text))
        if not doc or (not is_admin and doc["owner_user_id"] != user_id):
            await update.effective_message.reply_text(t(lang, "invalid_id"))
            return
        context.user_data["rename_doc_id"] = int(text)
        context.user_data["state"] = "rename_wait_new_name"
        await update.effective_message.reply_text(t(lang, "send_new_name"))
        return
    if state == "rename_wait_new_name":
        doc_id = context.user_data.get("rename_doc_id")
        if not doc_id:
            context.user_data.clear()
            return
        DB.rename_document(int(doc_id), text[:100])
        context.user_data.clear()
        await update.effective_message.reply_text(t(lang, "done"), reply_markup=file_actions_menu(lang))
        return
    if state == "delete_wait_doc_id":
        if not text.isdigit():
            await update.effective_message.reply_text(t(lang, "invalid_id"))
            return
        doc = DB.get_document(int(text))
        if not doc or (not is_admin and doc["owner_user_id"] != user_id):
            await update.effective_message.reply_text(t(lang, "invalid_id"))
            return
        DB.soft_delete_document(int(text))
        context.user_data.clear()
        await update.effective_message.reply_text(t(lang, "done"), reply_markup=file_actions_menu(lang))
        return
    if state == "channel_wait_id" and is_admin:
        context.user_data["tmp_channel_id"] = text
        context.user_data["state"] = "channel_wait_url"
        await update.effective_message.reply_text(t(lang, "choose_channel_url"))
        return
    if state == "channel_wait_url" and is_admin:
        channel_id = context.user_data.get("tmp_channel_id")
        DB.add_channel(channel_id, channel_id, text)
        context.user_data.clear()
        await update.effective_message.reply_text(t(lang, "done"), reply_markup=admin_menu(lang))
        return
    if state == "grant_plan_wait_user" and is_admin:
        if not text.isdigit():
            await update.effective_message.reply_text(t(lang, "invalid_id"))
            return
        context.user_data["target_plan_user_id"] = int(text)
        context.user_data["state"] = None
        await update.effective_message.reply_text(
            "Tarifni tanlang:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Basic 30 kun", callback_data="grant:basic:30")],
                [InlineKeyboardButton("Premium 30 kun", callback_data="grant:premium:30")],
            ]),
        )
        return

    # Main menus
    if text == t(lang, "ask"):
        context.user_data["mode"] = "ask"
        await update.effective_message.reply_text(t(lang, "send_question"), reply_markup=back_menu(lang))
        return
    if text == t(lang, "upload"):
        context.user_data["mode"] = "upload"
        await update.effective_message.reply_text(t(lang, "send_upload"), reply_markup=back_menu(lang))
        return
    if text == t(lang, "my_files"):
        context.user_data.clear()
        await update.effective_message.reply_text(t(lang, "my_files"), reply_markup=file_actions_menu(lang))
        return
    if text == t(lang, "tariffs"):
        await update.effective_message.reply_text(t(lang, "tariffs_text"), reply_markup=tariffs_keyboard(lang))
        return
    if text == t(lang, "referrals"):
        info = DB.get_referral_info(user_id)
        link = f"https://t.me/{SETTINGS.bot_username.lstrip('@')}?start={user_id}"
        await update.effective_message.reply_text(
            f"{t(lang, 'ref_text')}\n\nTaklif qilganlar: {info['count']}\nKeyingi bonusgacha: {info['remaining']}\n\nLink:\n{link}"
        )
        return
    if text == t(lang, "history"):
        rows = DB.list_history(user_id, limit=10)
        if not rows:
            await update.effective_message.reply_text("Tarix bo'sh.")
        else:
            msg = "\n\n".join([f"Savol: {r['question_text']}\nShaxsiy: {r['private_answer']}\nOmmaviy: {r['public_answer']}" for r in rows])
            await update.effective_message.reply_text(msg[:4096])
        return
    if text == t(lang, "help"):
        await update.effective_message.reply_text(t(lang, "help_text"), reply_markup=back_menu(lang))
        return
    if text == t(lang, "private_files"):
        rows = DB.list_user_documents(user_id, "private")
        await update.effective_message.reply_text(format_docs_list(rows) or t(lang, "no_docs"))
        return
    if text == t(lang, "public_files"):
        rows = DB.list_user_documents(user_id, "public")
        await update.effective_message.reply_text(format_docs_list(rows) or t(lang, "no_docs"))
        return
    if text == t(lang, "preview_file"):
        rows = DB.list_user_documents(user_id)
        if not rows:
            await update.effective_message.reply_text(t(lang, "no_docs"))
        else:
            row = rows[0]
            preview = (
                f"ID: {row['id']}\n"
                f"Nomi: {row['display_name'] or row['original_file_name']}\n"
                f"Turi: {row['mime_type']}\n"
                f"Scope: {row['scope']}\n"
                f"Status: {row['moderation_status']}\n"
                f"Preview: {row['preview_text'] or ''}"
            )
            await update.effective_message.reply_text(preview[:4096])
        return
    if text == t(lang, "rename_file"):
        context.user_data["state"] = "rename_wait_doc_id"
        await update.effective_message.reply_text(t(lang, "choose_doc_for_rename"))
        return
    if text == t(lang, "delete_file"):
        context.user_data["state"] = "delete_wait_doc_id"
        await update.effective_message.reply_text(t(lang, "choose_doc_for_delete"))
        return

    if text == "⭐ Basic":
        await update.effective_message.reply_text(
            f"{t(lang, 'basic_plan')}",
            reply_markup=plan_buy_keyboard("basic", lang),
        )
        return
    if text == "🚀 Premium":
        await update.effective_message.reply_text(
            f"{t(lang, 'premium_plan')}",
            reply_markup=plan_buy_keyboard("premium", lang),
        )
        return
    if text == t(lang, "my_plan"):
        info = DB.get_plan(user_id)
        limit = DB.get_daily_limit(user_id)
        await update.effective_message.reply_text(
            f"Tarif: {info['plan']}\nTugash: {info['expires_at'] or 'yo\'q'}\nKunlik limit: {limit}\nBugun ishlatilgan: {info['used']}"
        )
        return
    if text == t(lang, "admin_contact"):
        await update.effective_message.reply_text(f"Admin bilan bog'lanish: {SETTINGS.admin_contact_username}")
        return

    if text == t(lang, "admin") and is_admin:
        await update.effective_message.reply_text("Admin panel", reply_markup=admin_menu(lang))
        return

    if is_admin and text == t(lang, "admin_dashboard"):
        stats = DB.dashboard_stats()
        msg = (
            f"Users: {stats['users']}\n"
            f"Documents: {stats['documents']}\n"
            f"Public: {stats['public_documents']}\n"
            f"Private: {stats['private_documents']}\n"
            f"Pending public: {stats['pending_public']}\n"
            f"Questions today: {stats['questions_today']}\n"
            f"Uploads today: {stats['uploads_today']}"
        )
        await update.effective_message.reply_text(msg)
        return
    if is_admin and text == t(lang, "admin_files"):
        rows = DB.list_public_documents()[:25]
        await update.effective_message.reply_text(format_docs_list(rows) or t(lang, "no_docs"))
        return
    if is_admin and text == t(lang, "admin_moderation"):
        await show_pending_moderation(update, lang)
        return
    if is_admin and text == t(lang, "admin_channels"):
        context.user_data["state"] = "channel_wait_id"
        await update.effective_message.reply_text(t(lang, "choose_channel_id"))
        return
    if is_admin and text == t(lang, "admin_tariffs"):
        context.user_data["state"] = "grant_plan_wait_user"
        await update.effective_message.reply_text(t(lang, "choose_user_for_plan"))
        return
    if is_admin and text == t(lang, "admin_exports"):
        path = export_public_documents_csv(user_id)
        with path.open("rb") as fh:
            await update.effective_message.reply_document(document=fh, filename=path.name)
        return
    if is_admin and text == t(lang, "admin_logs"):
        rows = DB.list_logs(15)
        out = "\n\n".join([f"[{r['level']}] {r['category']}\n{r['message']}" for r in rows]) or "No logs"
        await update.effective_message.reply_text(out[:4000])
        return

    if mode == "ask":
        await answer_question(update, text)
        return

    await update.effective_message.reply_text(t(lang, "main_menu"), reply_markup=main_menu(lang, is_admin))


async def media_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = await ensure_user(update)
    lang = DB.get_interface_language(user_id)
    mode = context.user_data.get("mode")
    parsed = await parse_upload(update, context, AI.image_to_text, AI.transcribe_audio)
    if not parsed or not parsed.text.strip():
        await update.effective_message.reply_text("Matn ajratib bo'lmadi.")
        return

    if mode == "ask":
        await answer_question(update, parsed.text)
        return

    if mode != "upload":
        await update.effective_message.reply_text(t(lang, "send_upload"), reply_markup=back_menu(lang))
        return

    duplicate = DB.find_duplicate_by_hash(parsed.content_hash)
    if duplicate:
        await update.effective_message.reply_text(
            f"Bu fayl oldin yuklangan: {duplicate['file_name']} (ID: {duplicate['id']})\nBaribir saqlashingiz mumkin.",
            reply_markup=save_scope_keyboard(lang),
        )
    else:
        await update.effective_message.reply_text(t(lang, "save_where"), reply_markup=save_scope_keyboard(lang))
    context.user_data["pending_upload"] = parsed.__dict__


async def save_scope_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    scope = query.data.split(":", 1)[1]
    lang = DB.get_interface_language(query.from_user.id)
    payload = context.user_data.get("pending_upload")
    if not payload:
        await query.message.reply_text("Pending upload topilmadi.")
        return
    moderation_status = "pending" if scope == "public" else "approved"
    doc_id = DB.add_document(
        owner_user_id=query.from_user.id,
        telegram_file_id=payload.get("telegram_file_id"),
        telegram_file_unique_id=payload.get("telegram_file_unique_id"),
        original_file_name=payload.get("file_name"),
        display_name=payload.get("file_name"),
        mime_type=payload.get("mime_type"),
        source_kind=payload.get("source_kind"),
        scope=scope,
        moderation_status=moderation_status,
        preview_text=payload.get("preview_text"),
        page_count=payload.get("page_count", 1),
        section_hint=None,
        content_hash=payload.get("content_hash"),
        file_size=payload.get("file_size", 0),
    )
    chunks = chunk_text(payload["text"])
    embeddings = AI.embed_texts([c["chunk_text"] for c in chunks]) if chunks else []
    for idx, emb in enumerate(embeddings):
        chunks[idx]["embedding"] = emb
    DB.add_chunks(doc_id, chunks)
    DB.add_log("INFO", "upload", f"document saved #{doc_id}", {"scope": scope, "owner": query.from_user.id})
    context.user_data.pop("pending_upload", None)
    await query.message.reply_text(t(lang, "saved_public_pending") if scope == "public" else t(lang, "saved_private"))


async def moderation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in SETTINGS.admin_user_ids:
        return
    _, action, doc_id = query.data.split(":")
    status = "approved" if action == "approve" else "rejected"
    DB.set_document_moderation_status(int(doc_id), status, admin_user_id=query.from_user.id)
    await query.message.reply_text(f"Document {doc_id}: {status}")


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, provider, plan = query.data.split(":")
    lang = DB.get_interface_language(query.from_user.id)
    if provider == "admin":
        await query.message.reply_text(f"Admin bilan bog'lanish: {SETTINGS.admin_contact_username}")
        return
    if provider == "click":
        url = SETTINGS.click_basic_url if plan == "basic" else SETTINGS.click_premium_url
        if not url:
            await query.message.reply_text(f"Click link hali sozlanmagan. Admin: {SETTINGS.admin_contact_username}")
            return
        await query.message.reply_text(f"To'lov linki:\n{url}")
        return
    if provider == "stars":
        amount = SETTINGS.stars_basic_amount if plan == "basic" else SETTINGS.stars_premium_amount
        title = f"{SETTINGS.bot_name} {'Basic' if plan == 'basic' else 'Premium'}"
        description = "1 oylik tarif"
        prices = [LabeledPrice(title, amount)]
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title=title,
            description=description,
            payload=f"plan:{plan}",
            provider_token="",
            currency="XTR",
            prices=prices,
        )
        return
    await query.message.reply_text(t(lang, "done"))


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payment = update.effective_message.successful_payment
    payload = payment.invoice_payload
    user_id = update.effective_user.id
    plan = "basic" if payload.endswith("basic") else "premium"
    days = 30
    amount = SETTINGS.stars_basic_amount if plan == "basic" else SETTINGS.stars_premium_amount
    DB.grant_plan_days(user_id, plan, days, source="payment", amount=amount, provider="telegram_stars")
    await update.effective_message.reply_text(f"Tarif yoqildi: {plan} ({days} kun)")


async def grant_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in SETTINGS.admin_user_ids:
        return
    _, plan, days = query.data.split(":")
    target_user = context.user_data.get("target_plan_user_id")
    if not target_user:
        await query.message.reply_text("Target user topilmadi.")
        return
    DB.grant_plan_days(int(target_user), plan, int(days), source="admin", granted_by_admin_id=query.from_user.id)
    await query.message.reply_text("Tarif berildi.")


async def answer_question(update: Update, question_text: str) -> None:
    user_id = update.effective_user.id
    can_ask, used, limit = DB.can_ask_question(user_id)
    if not can_ask:
        await update.effective_message.reply_text(f"{t(DB.get_interface_language(user_id), 'question_limit_reached')} ({used}/{limit})")
        return
    private_result = SEARCH.search_scope(user_id, "private", question_text)
    public_result = SEARCH.search_scope(user_id, "public", question_text)
    answer_lang = AI.detect_language(question_text)
    result = AI.answer_from_context(question_text, private_result["context"], public_result["context"], answer_lang)
    private_block = result.get("private", {})
    public_block = result.get("public", {})
    msg = format_answer_block("Shaxsiy ma'lumotlardan", private_block) + "\n\n" + format_answer_block("Ommaviy ma'lumotlardan", public_block)
    await update.effective_message.reply_text(msg[:4096], parse_mode=ParseMode.MARKDOWN)
    DB.increase_daily_questions(user_id)
    DB.add_history(
        telegram_user_id=user_id,
        question_text=question_text,
        question_language=answer_lang,
        private_answer=private_block.get("short_answer", ""),
        public_answer=public_block.get("short_answer", ""),
        private_source=private_block.get("source", private_result["source"]),
        public_source=public_block.get("source", public_result["source"]),
    )
    DB.add_log("INFO", "search", "question answered", {"user_id": user_id, "question": question_text[:120]})


async def show_pending_moderation(update: Update, lang: str) -> None:
    rows = DB.list_pending_public_documents()[:10]
    if not rows:
        await update.effective_message.reply_text(t(lang, "pending_empty"))
        return
    for row in rows:
        text = (
            f"ID: {row['id']}\n"
            f"File: {row['display_name'] or row['original_file_name']}\n"
            f"Owner: {row['owner_user_id']}\n"
            f"Preview: {(row['preview_text'] or '')[:300]}"
        )
        await update.effective_message.reply_text(text, reply_markup=moderation_keyboard(int(row["id"])))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error", exc_info=context.error)
    DB.add_log("ERROR", "runtime", str(context.error))


def format_docs_list(rows) -> str:
    items = []
    for row in rows:
        items.append(
            f"ID {row['id']} | {row['display_name'] or row['original_file_name']} | {row['scope']} | {row['moderation_status']}"
        )
    return "\n".join(items)


def format_answer_block(title: str, block: dict[str, Any]) -> str:
    not_found = "Ma'lumot topilmadi."
    return (
        f"*{title}:*\n"
        f"*Qisqa javob:* {block.get('short_answer', not_found)}\n"
        f"*Batafsil:* {block.get('details', not_found)}\n"
        f"*Manba:* {block.get('source', 'topilmadi')}"
    )


def export_public_documents_csv(admin_user_id: int) -> Path:
    rows = DB.list_public_documents()
    path = SETTINGS.exports_dir / "public_documents_export.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "file_name", "mime_type", "owner_user_id", "moderation_status", "created_at", "preview_text"])
        for row in rows:
            writer.writerow([
                row["id"],
                row["display_name"] or row["original_file_name"],
                row["mime_type"],
                row["owner_user_id"],
                row["moderation_status"],
                row["created_at"],
                row["preview_text"],
            ])
    DB.add_export_log(admin_user_id, "public_csv", str(path))
    return path


def build_app() -> Application:
    app = Application.builder().token(SETTINGS.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern=r"^check_sub$"))
    app.add_handler(CallbackQueryHandler(save_scope_callback, pattern=r"^save_scope:"))
    app.add_handler(CallbackQueryHandler(moderation_callback, pattern=r"^mod:"))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern=r"^buy:"))
    app.add_handler(CallbackQueryHandler(grant_plan_callback, pattern=r"^grant:"))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(CallbackQueryHandler())
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VOICE, media_router))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_error_handler(error_handler)
    return app


from telegram.ext import PreCheckoutQueryHandler  # noqa: E402


if __name__ == "__main__":
    if not SETTINGS.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN kerak")
    build_app().run_polling(allowed_updates=Update.ALL_TYPES)
