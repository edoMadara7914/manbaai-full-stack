from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from texts import t


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("O'zbekcha", callback_data="lang:uz")],
            [InlineKeyboardButton("Русский", callback_data="lang:ru")],
            [InlineKeyboardButton("English", callback_data="lang:en")],
        ]
    )


def subscription_keyboard(rows: list[dict]) -> InlineKeyboardMarkup:
    kb = []
    for row in rows:
        url = row.get("url") or ""
        if url:
            kb.append([InlineKeyboardButton(row.get("title", url), url=url)])
    kb.append([InlineKeyboardButton("Obuna bo'ldim", callback_data="check_sub")])
    return InlineKeyboardMarkup(kb)


def main_menu(lang: str, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(t(lang, "ask")), KeyboardButton(t(lang, "upload"))],
        [KeyboardButton(t(lang, "my_files")), KeyboardButton(t(lang, "tariffs"))],
        [KeyboardButton(t(lang, "referrals")), KeyboardButton(t(lang, "history"))],
        [KeyboardButton(t(lang, "help"))],
    ]
    if is_admin:
        rows.append([KeyboardButton(t(lang, "admin"))])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def back_menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(t(lang, "back"))]], resize_keyboard=True)


def save_scope_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(t(lang, "save_private"), callback_data="save_scope:private"),
            InlineKeyboardButton(t(lang, "save_public"), callback_data="save_scope:public"),
        ]]
    )


def moderation_keyboard(doc_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Approve", callback_data=f"mod:approve:{doc_id}"),
            InlineKeyboardButton("Reject", callback_data=f"mod:reject:{doc_id}"),
        ]]
    )


def tariffs_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("⭐ Basic"), KeyboardButton("🚀 Premium")],
            [KeyboardButton(t(lang, "my_plan")), KeyboardButton(t(lang, "admin_contact"))],
            [KeyboardButton(t(lang, "back"))],
        ],
        resize_keyboard=True,
    )


def plan_buy_keyboard(plan: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t(lang, "buy_stars"), callback_data=f"buy:stars:{plan}")],
            [InlineKeyboardButton(t(lang, "buy_click"), callback_data=f"buy:click:{plan}")],
            [InlineKeyboardButton(t(lang, "buy_admin"), callback_data=f"buy:admin:{plan}")],
        ]
    )


def file_actions_menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t(lang, "private_files")), KeyboardButton(t(lang, "public_files"))],
            [KeyboardButton(t(lang, "preview_file")), KeyboardButton(t(lang, "rename_file"))],
            [KeyboardButton(t(lang, "delete_file"))],
            [KeyboardButton(t(lang, "back"))],
        ],
        resize_keyboard=True,
    )


def admin_menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t(lang, "admin_dashboard")), KeyboardButton(t(lang, "admin_files"))],
            [KeyboardButton(t(lang, "admin_users")), KeyboardButton(t(lang, "admin_moderation"))],
            [KeyboardButton(t(lang, "admin_channels")), KeyboardButton(t(lang, "admin_tariffs"))],
            [KeyboardButton(t(lang, "admin_exports")), KeyboardButton(t(lang, "admin_logs"))],
            [KeyboardButton(t(lang, "back"))],
        ],
        resize_keyboard=True,
    )
