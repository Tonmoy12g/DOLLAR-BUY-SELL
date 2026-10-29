#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================
BINANCE DOLLAR (USDT) BUY & SELL TELEGRAM BOT (FULL ADMIN PANEL)
python-telegram-bot version — converted from binance_dollar_bot.py (telebot)
====================================================================
Features (preserved exactly from the telebot version):
- /start welcome with Buy/Sell rates and reserve, Today's Rate, My Orders, Support
- Buy Dollar (USDT), Sell Dollar (USDT) — amount -> payment method ->
  receive info -> proof -> Pending -> admin Approve/Reject
- Sell-only Max: Min Order applies to both, Max Order applies to SELL only
  (Buy prompt shows Min only; Sell prompt shows Min + Max; Sell > Max rejected)
- Admin Panel: Bot Status toggle, bKash/Nagad/Rocket ON/OFF toggles,
  Buy Rate, Sell Rate, Reserve, Min Order, Max Order (Sell),
  Set bKash/Nagad/Rocket numbers, Set BEP20 Address, Set Gram Address, Set Support ID,
  Set Notice Text, Pending Orders with Approve/Reject, Broadcast,
  Add Admin ID, Refresh
- Reserve adjustment on approve: Buy approve decreases reserve,
  Sell approve increases reserve
- Built-in SQLite Database (dollar_bot.db, same schema as the source)

Color: MAIN MENU Reply Keyboard only, using the SMM bot _mkb pattern
(KeyboardButton style kwarg -> api_kwargs fallback -> plain button).
Inline buttons stay as-is: Telegram inline buttons have no background color.
Token / Admin ID come ONLY from environment: BOT_TOKEN, ADMIN_ID.
No hardcoded token or key in this file.

Setup:
  pip install python-telegram-bot
  BOT_TOKEN=<token from @BotFather> ADMIN_ID=<numeric id> python binance-dollar-bot-ptb.py
====================================================================
"""

import os
import sqlite3
import threading
from datetime import datetime

from flask import Flask

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    filters,
)

# ====================================================================
# BASIC CONFIGURATION — environment only, no hardcoded token/key
# ====================================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MAIN_ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or 0)
DB_PATH = "dollar_bot.db"

# In-memory step state tracker for multi-step user & admin inputs
# (context.user_data["step"] mirrors the source's user_states dict)
user_states = {}


# ====================================================================
# DATABASE SETUP & HELPER FUNCTIONS (same schema/defaults as source)
# ====================================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            joined_at TEXT,
            is_admin INTEGER DEFAULT 0
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            order_type TEXT,
            usd_amount REAL,
            bdt_amount REAL,
            rate REAL,
            payment_method TEXT,
            receive_info TEXT,
            trx_proof TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT
        )
        """
    )
    try:
        c.execute("ALTER TABLE orders ADD COLUMN currency TEXT DEFAULT 'USDT'")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE orders ADD COLUMN sender_number TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE orders ADD COLUMN screenshot_file_id TEXT DEFAULT ''")
    except Exception:
        pass
    default_settings = {
        "bot_active": "1",
        "buy_rate": "125.0",
        "sell_rate": "121.0",
        "min_usd": "5.0",
        "max_usd": "1000.0",
        "buy_min": "5.0",
        "buy_max": "1000.0",
        "sell_min": "5.0",
        "sell_max": "1000.0",
        "gram_buy_min": "5.0",
        "gram_buy_max": "1000.0",
        "gram_sell_min": "5.0",
        "gram_sell_max": "1000.0",
        "usdt_reserve": "500.0",
        "gram_buy_rate": "125.0",
        "gram_sell_rate": "121.0",
        "gram_reserve": "500.0",
        "gram_min": "5.0",
        "gram_max": "1000.0",
        "bkash_active": "1",
        "nagad_active": "1",
        "rocket_active": "1",
        "bkash_number": "017XXXXXXXX (Personal)",
        "nagad_number": "018XXXXXXXX (Personal)",
        "rocket_number": "019XXXXXXXX (Personal)",
        "bep20_address": "Not Set - BEP20 Address",
        "gram_address": "Not Set - Gram Address",
        "support_user": "@YourSupportUsername",
        "notice_text": "⚡ ১০০% ট্রাস্টেড ও দ্রুত Binance USDT Buy-Sell সার্ভিস। অর্ডার করার ৫-১০ মিনিটের মধ্যে ডেলিভারি পাবেন।",
    }
    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    if MAIN_ADMIN_ID:
        c.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at, is_admin) VALUES (?, ?, ?, ?, 1)",
            (MAIN_ADMIN_ID, "MainAdmin", "Main Admin", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        c.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (MAIN_ADMIN_ID,))
    conn.commit()
    conn.close()


def get_setting(key: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""


def set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


def register_user(user):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    username = f"@{user.username}" if user.username else "NoUsername"
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    is_adm = 1 if user.id == MAIN_ADMIN_ID else 0
    c.execute(
        """
        INSERT INTO users (user_id, username, full_name, joined_at, is_admin)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            full_name = excluded.full_name
        """,
        (user.id, username, full_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), is_adm),
    )
    conn.commit()
    conn.close()


def is_admin(user_id: int) -> bool:
    if MAIN_ADMIN_ID and user_id == MAIN_ADMIN_ID:
        return True
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0] == 1)


def get_all_admin_ids():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_admin = 1")
    ids = [r[0] for r in c.fetchall()]
    conn.close()
    if MAIN_ADMIN_ID and MAIN_ADMIN_ID not in ids:
        ids.append(MAIN_ADMIN_ID)
    return ids


# ====================================================================
# COLORED KEYBOARD BUTTON HELPER (SMM bot pattern, bot__23.py)
# Creates a colored Reply KeyboardButton; falls back gracefully.
# Valid styles: "primary" (blue), "success" (green), "danger" (red).
# Supporting clients render the color; others show a plain button.
# ====================================================================
_VALID_STYLES = ("primary", "success", "danger")


def _mkb(text: str, style: str = "primary") -> KeyboardButton:
    """Creates a colored Reply KeyboardButton compatible with all PTB versions."""
    if style not in _VALID_STYLES:
        style = "primary"
    try:
        return KeyboardButton(text, style=style)
    except TypeError:
        try:
            return KeyboardButton(text, api_kwargs={"style": style})
        except Exception:
            return KeyboardButton(text)


# ====================================================================
# BUTTON LABELS & KEYBOARDS
# ====================================================================
BTN_BUY = "💵 Buy Dollar"
BTN_SELL = "💰 Sell Dollar"
BTN_RATE = "📊 Today's Rate"
BTN_ORDERS = "📜 My Orders"
BTN_SUPPORT = "👨‍💼 Support"
BTN_GRAM = "💎 Gram"
BTN_BUY_GRAM = "💎 Buy Gram"
BTN_SELL_GRAM = "💎 Sell Gram"
BTN_ADMIN = "⚙️ 👑 Admin Panel"
BTN_CANCEL = "🔴 ❌ Cancel Action"


def main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    # MAIN MENU ONLY: alternate primary (blue) / success (green),
    # like the SMM bot main menu. Inline buttons are intentionally untouched.
    rows = [
        [_mkb(BTN_BUY, "primary"), _mkb(BTN_SELL, "success")],
        # 2026-10-29 21:29-21:31: separate Buy Gram and Sell Gram buttons removed.
        # Gram Buy is only inside Buy Dollar -> USDT / Gram, Gram Sell only inside Sell Dollar -> USDT / Gram (BEP20 address behind the scenes).
        [_mkb(BTN_RATE, "primary"), _mkb(BTN_ORDERS, "success")],
    ]
    if is_admin(user_id):
        rows.append([_mkb(BTN_SUPPORT, "primary"), _mkb(BTN_ADMIN, "primary")])
    else:
        rows.append([_mkb(BTN_SUPPORT, "primary")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(BTN_CANCEL)]], resize_keyboard=True, one_time_keyboard=True)


def active_payment_methods_markup(prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    if get_setting("bkash_active") == "1":
        buttons.append([InlineKeyboardButton("🟣 📲 bKash (বিকাশ)", callback_data=f"{prefix}_bKash")])
    if get_setting("nagad_active") == "1":
        buttons.append([InlineKeyboardButton("🟠 📲 Nagad (নগদ)", callback_data=f"{prefix}_Nagad")])
    if get_setting("rocket_active") == "1":
        buttons.append([InlineKeyboardButton("🔵 📲 Rocket (রকেট)", callback_data=f"{prefix}_Rocket")])
    buttons.append([InlineKeyboardButton("🔴 ❌ Cancel Order", callback_data="user_cancel_flow")])
    return InlineKeyboardMarkup(buttons)


def has_any_active_payment() -> bool:
    return any(get_setting(k) == "1" for k in ("bkash_active", "nagad_active", "rocket_active"))


def admin_panel_inline_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 DOLLAR SETTING", callback_data="adm_open_dollar"),
         InlineKeyboardButton("💎 GRAM SETTING", callback_data="adm_open_gram")],
        [InlineKeyboardButton("💳 PAYMENT SYSTEM", callback_data="adm_open_payment"),
         InlineKeyboardButton("🤖 BOT SETTING", callback_data="adm_open_bot")],
        [InlineKeyboardButton("📦 Pending Orders", callback_data="adm_pending_orders"),
         InlineKeyboardButton("🔄 Refresh Panel", callback_data="adm_refresh")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="adm_main_menu")],
    ])


def dollar_setting_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🟢 BUY RET: {get_setting('buy_rate')}৳", callback_data="adm_set_buy_rate"),
         InlineKeyboardButton(f"🔴 SELL RET: {get_setting('sell_rate')}৳", callback_data="adm_set_sell_rate")],
        [InlineKeyboardButton(f"💎 RESERVE: {get_setting('usdt_reserve')}$", callback_data="adm_set_reserve")],
        [InlineKeyboardButton(f"🟢 BUY DOLLAR MIN: {get_setting('buy_min')}$", callback_data="adm_set_buy_min"),
         InlineKeyboardButton(f"🟢 BUY DOLLAR MAX: {get_setting('buy_max')}$", callback_data="adm_set_buy_max")],
        [InlineKeyboardButton(f"🔴 SELL DOLLAR MIN: {get_setting('sell_min')}$", callback_data="adm_set_sell_min"),
         InlineKeyboardButton(f"🔴 SELL DOLLAR MAX: {get_setting('sell_max')}$", callback_data="adm_set_sell_max")],
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="adm_back_admin")],
    ])


def gram_setting_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🟢 BUY RET: {get_setting('gram_buy_rate')}৳", callback_data="adm_set_gram_buy_rate"),
         InlineKeyboardButton(f"🔴 SELL RET: {get_setting('gram_sell_rate')}৳", callback_data="adm_set_gram_sell_rate")],
        [InlineKeyboardButton(f"💎 RESERVE: {get_setting('gram_reserve')}", callback_data="adm_set_gram_reserve")],
        [InlineKeyboardButton(f"🟢 BUY GRAM MIN: {get_setting('gram_buy_min')}", callback_data="adm_set_gram_buy_min"),
         InlineKeyboardButton(f"🟢 BUY GRAM MAX: {get_setting('gram_buy_max')}", callback_data="adm_set_gram_buy_max")],
        [InlineKeyboardButton(f"🔴 SELL GRAM MIN: {get_setting('gram_sell_min')}", callback_data="adm_set_gram_sell_min"),
         InlineKeyboardButton(f"🔴 SELL GRAM MAX: {get_setting('gram_sell_max')}", callback_data="adm_set_gram_sell_max")],
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="adm_back_admin")],
    ])


def payment_setting_markup() -> InlineKeyboardMarkup:
    bkash_st = "🟢 ON" if get_setting("bkash_active") == "1" else "🔴 OFF"
    nagad_st = "🟢 ON" if get_setting("nagad_active") == "1" else "🔴 OFF"
    rocket_st = "🟢 ON" if get_setting("rocket_active") == "1" else "🔴 OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🟣 bKash: {bkash_st}", callback_data="adm_toggle_bkash"),
         InlineKeyboardButton(f"🟠 Nagad: {nagad_st}", callback_data="adm_toggle_nagad")],
        [InlineKeyboardButton(f"🔵 Rocket: {rocket_st}", callback_data="adm_toggle_rocket")],
        [InlineKeyboardButton("🟣 Set bKash No", callback_data="adm_set_bkash_no"),
         InlineKeyboardButton("🟠 Set Nagad No", callback_data="adm_set_nagad_no")],
        [InlineKeyboardButton("🔵 Set Rocket No", callback_data="adm_set_rocket_no"),
         InlineKeyboardButton("🟡 Set BEP20 Address", callback_data="adm_set_bep20_address")],
        [InlineKeyboardButton("💎 Set Gram Address", callback_data="adm_set_gram_address")],
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="adm_back_admin")],
    ])


def bot_setting_markup() -> InlineKeyboardMarkup:
    bot_st = "🟢 ON" if get_setting("bot_active") == "1" else "🔴 OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🤖 Bot Status: {bot_st} (Click to Toggle)", callback_data="adm_toggle_bot")],
        [InlineKeyboardButton("📞 Set Support ID", callback_data="adm_set_support"),
         InlineKeyboardButton("📢 Set Notice Text", callback_data="adm_set_notice")],
        [InlineKeyboardButton("➕ Add Admin ID", callback_data="adm_add_admin"),
         InlineKeyboardButton("📣 Broadcast Msg", callback_data="adm_broadcast")],
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="adm_back_admin")],
    ])


def get_admin_dashboard_text() -> str:
    bot_st = "🟢 ACTIVE" if get_setting("bot_active") == "1" else "🔴 OFF (Maintenance)"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE status = 'PENDING'")
    pending_orders = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE status = 'APPROVED'")
    completed_orders = c.fetchone()[0]
    conn.close()
    return (
        "⚙️ <b>👑 BINANCE DOLLAR BOT — ADMIN PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Bot Status:</b> {bot_st}\n"
        f"👥 <b>Total Users:</b> {total_users} | ⏳ <b>Pending:</b> {pending_orders} | ✅ <b>Done:</b> {completed_orders}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <i>নিচের ৪টা ভাগ থেকে সেটিং করুন:</i>\n"
        "💵 DOLLAR SETTING | 💎 GRAM SETTING\n"
        "💳 PAYMENT SYSTEM | 🤖 BOT SETTING"
    )


def get_dollar_setting_text() -> str:
    return (
        "💵 <b>DOLLAR SETTING</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>BUY RET:</b> <code>{get_setting('buy_rate')} BDT/$</code>\n"
        f"🔴 <b>SELL RET:</b> <code>{get_setting('sell_rate')} BDT/$</code>\n"
        f"💎 <b>RESERVE:</b> <code>{get_setting('usdt_reserve')} USDT</code>\n"
        f"🟢 <b>BUY DOLLAR MIN:</b> <code>{get_setting('buy_min')} USDT</code> | <b>MAX:</b> <code>{get_setting('buy_max')} USDT</code>\n"
        f"🔴 <b>SELL DOLLAR MIN:</b> <code>{get_setting('sell_min')} USDT</code> | <b>MAX:</b> <code>{get_setting('sell_max')} USDT</code>"
    )


def get_gram_setting_text() -> str:
    return (
        "💎 <b>GRAM SETTING</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>BUY RET:</b> <code>{get_setting('gram_buy_rate')} BDT/Gram</code>\n"
        f"🔴 <b>SELL RET:</b> <code>{get_setting('gram_sell_rate')} BDT/Gram</code>\n"
        f"💎 <b>RESERVE:</b> <code>{get_setting('gram_reserve')} Gram</code>\n"
        f"🟢 <b>BUY GRAM MIN:</b> <code>{get_setting('gram_buy_min')} Gram</code> | <b>MAX:</b> <code>{get_setting('gram_buy_max')} Gram</code>\n"
        f"🔴 <b>SELL GRAM MIN:</b> <code>{get_setting('gram_sell_min')} Gram</code> | <b>MAX:</b> <code>{get_setting('gram_sell_max')} Gram</code>"
    )


def get_payment_setting_text() -> str:
    bkash_st = "🟢 ON" if get_setting("bkash_active") == "1" else "🔴 OFF"
    nagad_st = "🟢 ON" if get_setting("nagad_active") == "1" else "🔴 OFF"
    rocket_st = "🟢 ON" if get_setting("rocket_active") == "1" else "🔴 OFF"
    return (
        "💳 <b>PAYMENT SYSTEM</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟣 <b>bKash [{bkash_st}]:</b> <code>{get_setting('bkash_number')}</code>\n"
        f"🟠 <b>Nagad [{nagad_st}]:</b> <code>{get_setting('nagad_number')}</code>\n"
        f"🔵 <b>Rocket [{rocket_st}]:</b> <code>{get_setting('rocket_number')}</code>\n"
        f"🟡 <b>BEP20 Address:</b> <code>{get_setting('bep20_address')}</code>\n"
        f"💎 <b>Gram Address:</b> <code>{get_setting('gram_address')}</code>"
    )


def get_bot_setting_text() -> str:
    bot_st = "🟢 ACTIVE" if get_setting("bot_active") == "1" else "🔴 OFF (Maintenance)"
    return (
        "🤖 <b>BOT SETTING</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Bot Status:</b> {bot_st}\n"
        f"📞 <b>Support:</b> {get_setting('support_user')}\n"
        f"📢 <b>Notice:</b> {get_setting('notice_text')}"
    )


def _admin_section_view(message_text: str):
    if "DOLLAR SETTING" in message_text:
        return get_dollar_setting_text(), dollar_setting_markup()
    if "GRAM SETTING" in message_text:
        return get_gram_setting_text(), gram_setting_markup()
    if "PAYMENT SYSTEM" in message_text:
        return get_payment_setting_text(), payment_setting_markup()
    if "BOT SETTING" in message_text:
        return get_bot_setting_text(), bot_setting_markup()
    return get_admin_dashboard_text(), admin_panel_inline_markup()


def build_rate_card() -> str:
    bk = "🟢 চালু (ON)" if get_setting("bkash_active") == "1" else "🔴 বন্ধ (OFF)"
    ng = "🟢 চালু (ON)" if get_setting("nagad_active") == "1" else "🔴 বন্ধ (OFF)"
    rk = "🟢 চালু (ON)" if get_setting("rocket_active") == "1" else "🔴 বন্ধ (OFF)"
    return (
        "🟡 📊 <b>আজকের ডলার রেট ও পেমেন্ট আপডেট</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>💵 Buy USDT Rate:</b> <code>{get_setting('buy_rate')} টাকা / $1</code>\n"
        f"🔴 <b>💰 Sell USDT Rate:</b> <code>{get_setting('sell_rate')} টাকা / $1</code>\n"
        f"💎 <b>Available Reserve:</b> <code>{get_setting('usdt_reserve')} USDT</code>\n"
        f"📉 <b>Minimum Order:</b> <code>{get_setting('buy_min')} USDT</code>\n"
        f"💎 <b>Gram Buy Rate:</b> <code>{get_setting('gram_buy_rate')} টাকা / Gram</code>\n"
        f"💎 <b>Gram Sell Rate:</b> <code>{get_setting('gram_sell_rate')} টাকা / Gram</code>\n"
        f"💎 <b>Gram Reserve:</b> <code>{get_setting('gram_reserve')} Gram</code>\n"
        f"💎 <b>Gram Minimum Order:</b> <code>{get_setting('gram_buy_min')} Gram</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📲 <b>সক্রিয় পেমেন্ট মেথডসমূহ:</b>\n"
        f"🟣 <b>bKash:</b> {bk}\n"
        f"🟠 <b>Nagad:</b> {ng}\n"
        f"🔵 <b>Rocket:</b> {rk}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 {get_setting('notice_text')}"
    )


# ====================================================================
# START & ADMIN COMMANDS
# ====================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    user_states.pop(update.effective_user.id, None)
    welcome_text = (
        f"👋 <b>স্বাগতম {update.effective_user.first_name}!</b>\n"
        "💎 <b>Binance Dollar (USDT) Buy & Sell Bot</b>-এ আপনাকে স্বাগতম।\n\n"
        f"📢 <b>নোটিশ:</b> {get_setting('notice_text')}\n\n"
        f"🟢 <b>ডলার কেনার রেট (Buy):</b> <code>{get_setting('buy_rate')} BDT</code>\n"
        f"🔴 <b>ডলার বিক্রির রেট (Sell):</b> <code>{get_setting('sell_rate')} BDT</code>\n"
        f"💎 <b>আমাদের রিজার্ভ:</b> <code>{get_setting('usdt_reserve')} USDT</code>\n"
        f"💎 <b>Gram কেনার রেট (Buy):</b> <code>{get_setting('gram_buy_rate')} BDT</code>\n"
        f"💎 <b>Gram বিক্রির রেট (Sell):</b> <code>{get_setting('gram_sell_rate')} BDT</code>\n"
        f"💎 <b>Gram রিজার্ভ:</b> <code>{get_setting('gram_reserve')} Gram</code>\n\n"
        "👇 <b>লেনদেন শুরু করতে নিচের রঙিন বাটন ব্যবহার করুন:</b>"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard(update.effective_user.id))


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🔴 ❌ দুঃখিত! শুধুমাত্র অ্যাডমিন এই প্যানেলে প্রবেশ করতে পারবেন.")
        return
    user_states.pop(update.effective_user.id, None)
    await update.message.reply_text(get_admin_dashboard_text(), reply_markup=admin_panel_inline_markup())


# ====================================================================
# TEXT HANDLER — button dispatch first (as in the source), then steps
# ====================================================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    uid = message.from_user.id
    text = (message.text or "").strip()

    if text == BTN_CANCEL:
        user_states.pop(uid, None)
        await message.reply_text(
            "🔴 ❌ আপনার চলমান কার্যক্রম বাতিল করা হয়েছে। মেইন মেনুতে ফিরে আসা হলো:",
            reply_markup=main_menu_keyboard(uid),
        )
        return
    if text == BTN_RATE:
        await message.reply_text(build_rate_card(), reply_markup=main_menu_keyboard(uid))
        return
    if text == BTN_SUPPORT:
        sup = get_setting("support_user")
        await message.reply_text(
            "🟣 👨‍💼 <b>লাইভ সাপোর্ট সেন্টার</b>\n\n"
            "যেকোনো সমস্যা বা জরুরি প্রয়োজনে আমাদের অ্যাডমিনের সাথে যোগাযোগ করুন:\n"
            f"👉 <b>Support:</b> {sup}",
            reply_markup=main_menu_keyboard(uid),
        )
        return
    if text == BTN_ORDERS:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT order_id, order_type, usd_amount, bdt_amount, payment_method, status, created_at "
            "FROM orders WHERE user_id = ? ORDER BY order_id DESC LIMIT 10",
            (uid,),
        )
        rows = c.fetchall()
        conn.close()
        if not rows:
            await message.reply_text("🔵 📜 আপনার এখনো কোনো অর্ডার নেই.", reply_markup=main_menu_keyboard(uid))
            return
        out = "🔵 📜 <b>আপনার সর্বশেষ ১০টি অর্ডার:</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for r in rows:
            oid, otype, usd, bdt, pm, status, cat = r
            st_icon = "🟡 PENDING" if status == "PENDING" else ("🟢 APPROVED" if status == "APPROVED" else "🔴 REJECTED")
            type_icon = "🟢 BUY" if otype == "BUY" else "🔴 SELL"
            out += (
                f"🆔 <b>Order #{oid}</b> ({type_icon})\n"
                f"💵 Amount: <code>{usd}$</code> ({bdt:.2f} BDT) | 📲 {pm}\n"
                f"📌 Status: <b>{st_icon}</b> | 🕒 {cat}\n"
                "──────────────────────\n"
            )
        await message.reply_text(out, reply_markup=main_menu_keyboard(uid))
        return
    if text == BTN_ADMIN:
        await cmd_admin(update, context)
        return
    if text in (BTN_BUY_GRAM, BTN_SELL_GRAM):
        is_buy = text == BTN_BUY_GRAM
        order_type = "BUY" if is_buy else "SELL"
        rate = float(get_setting("gram_buy_rate" if is_buy else "gram_sell_rate"))
        min_usd = float(get_setting("gram_buy_min" if is_buy else "gram_sell_min"))
        max_usd = float(get_setting("gram_buy_max" if is_buy else "gram_sell_max"))
        reserve = float(get_setting("gram_reserve"))
        user_states[uid] = {"step": "ENTER_USD_AMOUNT", "order_type": order_type, "rate": rate, "currency": "GRAM", "new_buy": order_type == "BUY", "new_sell": order_type == "SELL"}
        if is_buy:
            prompt = (
                "🟢 💎 <b>Buy Gram</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💠 <b>আজকের কেনার রেট:</b> <code>{rate} BDT / Gram</code>\n"
                f"💎 <b>আমাদের রিজার্ভ:</b> <code>{reserve} Gram</code>\n"
                f"📉 <b>সর্বনিম্ন অর্ডার:</b> <code>{min_usd} Gram</code>\n"
                f"📈 <b>সর্বোচ্চ অর্ডার:</b> <code>{max_usd} Gram</code>\n\n"
                "✍️ <b>আপনি কত Gram কিনতে চান? সংখ্যায় লিখুন (যেমন: 10 বা 25):</b>"
            )
        else:
            prompt = (
                "🔴 💎 <b>Sell Gram</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💠 <b>আজকের বিক্রির রেট:</b> <code>{rate} BDT / Gram</code>\n"
                f"📉 Minimum gram sell: <code>{min_usd} Gram</code>\n"
                f"📈 Maximum gram sell: <code>{max_usd} Gram</code>\n\n"
                "✍️ <b>আপনি কত Gram বিক্রি করতে চান? সংখ্যায় লিখুন (যেমন: 10 বা 50):</b>"
            )
        await message.reply_text(prompt, reply_markup=cancel_keyboard())
        return
    if text == BTN_GRAM:
        await message.reply_text(
            f"💎 <b>Gram Buy / Sell</b>\n\n"
            f"🟢 Gram Buy Rate: <code>{get_setting('gram_buy_rate')} BDT</code>\n"
            f"🔴 Gram Sell Rate: <code>{get_setting('gram_sell_rate')} BDT</code>\n"
            f"💎 Gram Reserve: <code>{get_setting('gram_reserve')} Gram</code>\n\n"
            "নিচ থেকে Buy Gram নাকি Sell Gram সিলেক্ট করুন:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🟢 Buy Gram", callback_data="gram_buy"),
                 InlineKeyboardButton("🔴 Sell Gram", callback_data="gram_sell")],
            ]),
        )
        return
    if text in (BTN_BUY, BTN_SELL):
        register_user(message.from_user)
        if get_setting("bot_active") != "1" and not is_admin(uid):
            await message.reply_text("🔴 ⚠️ বট বর্তমানে সাময়িক বিরতিতে (Maintenance) আছে। অনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন.")
            return
        if not has_any_active_payment():
            await message.reply_text("🔴 ⚠️ বর্তমানে সকল পেমেন্ট মেথড (bKash/Nagad/Rocket) সাময়িকভাবে বন্ধ আছে। পরে চেষ্টা করুন।")
            return
        is_buy = text == BTN_BUY
        if is_buy:
            await message.reply_text(
                "🟢 💵 <b>Buy Dollar</b>\n\nকোনটা কিনতে চান, সিলেক্ট করুন:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💵 USDT", callback_data="buy_choice_usdt"),
                     InlineKeyboardButton("💎 Gram", callback_data="buy_choice_gram")],
                    [InlineKeyboardButton("🔴 ❌ Cancel Order", callback_data="user_cancel_flow")],
                ]),
            )
        else:
            await message.reply_text(
                "🔴 💰 <b>Sell Dollar</b>\n\nকোনটা বিক্রি করতে চান, সিলেক্ট করুন:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💵 USDT", callback_data="sell_choice_bep20"),
                     InlineKeyboardButton("💎 Gram", callback_data="sell_choice_gram")],
                    [InlineKeyboardButton("🔴 ❌ Cancel Order", callback_data="user_cancel_flow")],
                ]),
            )
        return

    # ---- multi-step inputs ----
    state = user_states.get(uid)
    if not state:
        await message.reply_text(
            "👇 নিচের রঙিন মেনু বাটন থেকে একটি অপশন সিলেক্ট করুন:",
            reply_markup=main_menu_keyboard(uid),
        )
        return
    step = state.get("step")

    if step == "ADMIN_SET_VALUE" and is_admin(uid):
        s_key = state["setting_key"]
        if s_key in ("buy_rate", "sell_rate", "usdt_reserve", "min_usd", "max_usd", "gram_buy_rate", "gram_sell_rate", "gram_reserve", "gram_min", "gram_max", "buy_min", "buy_max", "sell_min", "sell_max", "gram_buy_min", "gram_buy_max", "gram_sell_min", "gram_sell_max"):
            try:
                val = float(text)
                if val <= 0 and s_key != "usdt_reserve":
                    raise ValueError()
                text = str(val)
            except ValueError:
                await message.reply_text("🔴 ❌ অনুগ্রহ করে সঠিক সংখ্যা (Number) লিখুন!")
                return
        set_setting(s_key, text)
        user_states.pop(uid, None)
        _labels = {
            "buy_rate": "BUY RET", "sell_rate": "SELL RET", "usdt_reserve": "RESERVE",
            "buy_min": "BUY DOLLAR MIN", "buy_max": "BUY DOLLAR MAX",
            "sell_min": "SELL DOLLAR MIN", "sell_max": "SELL DOLLAR MAX",
            "gram_buy_rate": "GRAM BUY RET", "gram_sell_rate": "GRAM SELL RET", "gram_reserve": "GRAM RESERVE",
            "gram_buy_min": "BUY GRAM MIN", "gram_buy_max": "BUY GRAM MAX",
            "gram_sell_min": "SELL GRAM MIN", "gram_sell_max": "SELL GRAM MAX",
            "bkash_number": "bKash No", "nagad_number": "Nagad No", "rocket_number": "Rocket No",
            "bep20_address": "BEP20 Address", "gram_address": "Gram Address", "support_user": "Support ID", "notice_text": "Notice Text",
        }
        await message.reply_text(
            f"🟢 ✅ <b>{_labels.get(s_key, s_key)}</b> সফলভাবে আপডেট হয়ে <code>{text}</code> সেট করা হয়েছে!",
            reply_markup=main_menu_keyboard(uid),
        )
        if s_key in ("buy_rate", "sell_rate", "usdt_reserve", "buy_min", "buy_max", "sell_min", "sell_max"):
            await message.reply_text(get_dollar_setting_text(), reply_markup=dollar_setting_markup())
        elif s_key.startswith("gram_"):
            await message.reply_text(get_gram_setting_text(), reply_markup=gram_setting_markup())
        elif s_key in ("bkash_number", "nagad_number", "rocket_number", "bep20_address", "gram_address"):
            await message.reply_text(get_payment_setting_text(), reply_markup=payment_setting_markup())
        elif s_key in ("support_user", "notice_text"):
            await message.reply_text(get_bot_setting_text(), reply_markup=bot_setting_markup())
        else:
            await message.reply_text(get_admin_dashboard_text(), reply_markup=admin_panel_inline_markup())
        return

    if step == "ADMIN_ADD_NEW" and is_admin(uid):
        try:
            new_adm_id = int(text)
        except ValueError:
            await message.reply_text("🔴 ❌ সঠিক Numeric Telegram ID দিন!")
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (user_id, username, full_name, joined_at, is_admin) VALUES (?, 'Admin', 'Admin', ?, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET is_admin = 1",
            (new_adm_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()
        user_states.pop(uid, None)
        await message.reply_text(
            f"🟢 ✅ User ID <code>{new_adm_id}</code>-কে সফলভাবে অ্যাডমিন করা হয়েছে!",
            reply_markup=main_menu_keyboard(uid),
        )
        return

    if step == "ADMIN_BROADCAST" and is_admin(uid):
        user_states.pop(uid, None)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        all_uids = [r[0] for r in c.fetchall()]
        conn.close()
        sent_count = 0
        for target_id in all_uids:
            try:
                await context.bot.send_message(target_id, f"📢 <b>অ্যাডমিন ঘোষণা:</b>\n\n{text}")
                sent_count += 1
            except Exception:
                pass
        await message.reply_text(
            f"🟢 ✅ মোট <b>{sent_count}</b> জন ইউজারের কাছে ব্রডকাস্ট মেসেজ পাঠানো হয়েছে!",
            reply_markup=main_menu_keyboard(uid),
        )
        return

    if step == "ENTER_USD_AMOUNT":
        try:
            usd_amount = float(text)
        except ValueError:
            await message.reply_text("🔴 ❌ অনুগ্রহ করে শুধুমাত্র সংখ্যায় ডলারের পরিমাণ লিখুন (যেমন: 10 বা 25.5):")
            return
        _is_gram = state.get("currency") == "GRAM"
        _is_buy = state.get("order_type") == "BUY"
        if _is_gram:
            min_usd = float(get_setting("gram_buy_min" if _is_buy else "gram_sell_min"))
            max_usd = float(get_setting("gram_buy_max" if _is_buy else "gram_sell_max"))
        else:
            min_usd = float(get_setting("buy_min" if _is_buy else "sell_min"))
            max_usd = float(get_setting("buy_max" if _is_buy else "sell_max"))
        _unit_lbl = "Gram" if _is_gram else "USDT"
        if usd_amount < min_usd:
            await message.reply_text(f"🔴 ⚠️ সর্বনিম্ন অর্ডার পরিমাণ <b>{min_usd} {_unit_lbl}</b>। অনুগ্রহ করে আবার লিখুন:")
            return
        if usd_amount > max_usd:
            await message.reply_text(f"🔴 ⚠️ সর্বোচ্চ অর্ডার পরিমাণ <b>{max_usd} {_unit_lbl}</b>। অনুগ্রহ করে আবার লিখুন:")
            return
        if state["order_type"] == "BUY":
            reserve = float(get_setting("gram_reserve" if state.get("currency") == "GRAM" else "usdt_reserve"))
            if usd_amount > reserve:
                await message.reply_text(f"🔴 ⚠️ আমাদের বর্তমান রিজার্ভ <b>{reserve} {_unit_lbl}</b>। এর সমান বা কম পরিমাণ লিখুন:")
                return
        rate = state["rate"]
        bdt_amount = round(usd_amount * rate, 2)
        state["usd_amount"] = usd_amount
        state["bdt_amount"] = bdt_amount
        # NEW Sell flow: amount -> admin address -> TxHash -> screenshot -> method -> number
        if state["order_type"] == "SELL" and state.get("new_sell"):
            _unit2 = state.get("currency", "USDT")
            _unit_disp = "Gram" if _unit2 == "GRAM" else "USDT"
            _addr_lbl = "Gram Address" if _unit2 == "GRAM" else "BEP20 Address"
            _admin_addr = get_setting("gram_address") if _unit2 == "GRAM" else get_setting("bep20_address")
            state["step"] = "SELL_TXHASH"
            await message.reply_text(
                f"🔴 💎 <b>Sell {_unit_disp}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>পরিমাণ:</b> <code>{usd_amount} {_unit_disp}</code> | 💴 <b>পাবেন:</b> <code>{bdt_amount:.2f} BDT</code>\n"
                f"🟡 <b>আমাদের {_addr_lbl}:</b>\n"
                f"👉 <code>{_admin_addr}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "✍️ <b>নিয়ম:</b>\n"
                f"১) উপরের {_addr_lbl} কপি করে {_unit_disp} পাঠান\n"
                "২) পাঠানোর পর শুধু Transaction Hash-টা এখানে দিবেন।\n"
                "৩) তারপর স্ক্রিনশট দিবেন\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "আপনি যে Transaction Hash পাইছেন, সেটা লিখে দেন👇",
                reply_markup=cancel_keyboard(),
            )
            return
        state["step"] = "SELECT_PAYMENT"
        _unit = state.get("currency", "USDT")
        _rate_lbl = "BDT / Gram" if _unit == "GRAM" else "BDT / $1"
        type_badge = f"🟢 💵 BUY {_unit}" if state["order_type"] == "BUY" else f"🔴 💰 SELL {_unit}"
        summary = (
            f"<b>{type_badge} — হিসাব বিবরণী</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>পরিমাণ:</b> <code>{usd_amount} {_unit}</code>\n"
            f"📊 <b>রেট:</b> <code>{rate} {_rate_lbl}</code>\n"
            f"💴 <b>মোট টাকার পরিমাণ:</b> <code>{bdt_amount:.2f} BDT</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>নিচের রঙিন বাটন থেকে আপনার পছন্দের পেমেন্ট মেথড সিলেক্ট করুন:</b>"
        )
        await message.reply_text(summary, reply_markup=active_payment_methods_markup("paymethod"))
        return

    if step == "ENTER_RECEIVE_INFO":
        state["receive_info"] = text
        # NEW Buy flow: after payment, sender number + screenshot only, NO TrxID
        state["step"] = "BUY_SENDER_NUMBER" if state["order_type"] == "BUY" else "ENTER_TRX_PROOF"
        pm = state["payment_method"]
        bdt_amount = state["bdt_amount"]
        usd_amount = state["usd_amount"]
        num_map = {
            "bKash": get_setting("bkash_number"),
            "Nagad": get_setting("nagad_number"),
            "Rocket": get_setting("rocket_number"),
        }
        admin_pay_no = num_map.get(pm, "")
        _pay_unit = state.get("currency", "USDT")
        _pay_disp = "Gram" if _pay_unit == "GRAM" else "USDT"
        _recv_lbl = "Gram Address" if _pay_unit == "GRAM" else "BEP20 Address"
        if state["order_type"] == "BUY":
            pay_instructions = (
                f"🟢 💳 <b>পেমেন্ট করার নিয়মাবলী (Buy {_pay_disp}):</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📲 <b>আমাদের {pm} নাম্বার:</b>\n"
                f"👉 <code>{admin_pay_no}</code>\n\n"
                f"💴 <b>পাঠানোর পরিমাণ:</b> <code>{bdt_amount:.2f} BDT</code>\n"
                f"📥 <b>আপনার {_recv_lbl}:</b> <code>{text}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "✍️ <b>নিয়ম:</b>\n"
                "১) উপরের নাম্বারে টাকা পাঠান\n"
                "২) টাকা পাঠানোর পর শুধু যে নাম্বার থেকে টাকা পাঠিয়েছেন, সেই নাম্বারটা এখানে দিবেন।\n"
                "৩) তারপর পেমেন্টের স্ক্রিনশট দিবেন\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "আপনি যে নাম্বার দিয়ে টাকা পাঠাইছেন, সে নাম্বার লিখে দেন👇"
            )
        else:
            _admin_addr = get_setting("gram_address") if _pay_unit == "GRAM" else get_setting("bep20_address")
            pay_instructions = (
                f"🔴 💎 <b>{_pay_unit} পাঠানোর নিয়মাবলী (Sell {_pay_unit}):</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🟡 <b>আমাদের {_recv_lbl}:</b>\n"
                f"👉 <code>{_admin_addr}</code>\n\n"
                f"💵 <b>পাঠানোর পরিমাণ:</b> <code>{usd_amount} {_pay_unit}</code>\n"
                f"📲 <b>টাকা পাবেন ({pm}):</b> <code>{text}</code> ({bdt_amount:.2f} BDT)\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "✍️ <b>সহজ করে বলছি:</b>\n"
                f"১) উপরের {_recv_lbl}-এ {_pay_unit} পাঠান\n"
                "২) শুধু আপনার Transaction Hash-টা এখানে লিখুন"
            )
        await message.reply_text(pay_instructions, reply_markup=cancel_keyboard())
        return

    if step == "BUY_SENDER_NUMBER":
        state["sender_number"] = text
        state["step"] = "BUY_SCREENSHOT"
        await message.reply_text(
            "📸 <b>আপনি যে টাকা পাঠাইছেন, তার স্ক্রিনশট দেন</b>\n\nনাম্বারটা পেয়েছি। এখন শুধু টাকার স্ক্রিনশটটা ছবি হিসেবে এখানে পাঠান।",
            reply_markup=cancel_keyboard(),
        )
        return

    if step in ("BUY_SCREENSHOT", "SELL_SCREENSHOT"):
        await message.reply_text(
            "📸 অনুগ্রহ করে স্ক্রিনশটটা ছবি হিসেবে পাঠান, লেখা হিসেবে না।",
            reply_markup=cancel_keyboard(),
        )
        return

    if step == "SELL_TXHASH":
        state["trx_proof"] = text
        state["step"] = "SELL_SCREENSHOT"
        _unit_disp2 = "Gram" if state.get("currency") == "GRAM" else "USDT"
        await message.reply_text(
            f"📸 <b>আপনি যে {_unit_disp2} পাঠাইছেন, তার স্ক্রিনশট দেন</b>\n\nTransaction Hash পেয়েছি। এখন শুধু স্ক্রিনশটটা ছবি হিসেবে এখানে পাঠান।",
            reply_markup=cancel_keyboard(),
        )
        return

    if step == "SELL_NUMBER":
        state["receive_info"] = text
        uname = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO orders (user_id, username, order_type, usd_amount, bdt_amount, rate, payment_method, receive_info, trx_proof, status, created_at, currency, sender_number, screenshot_file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?)
            """,
            (uid, uname, state["order_type"], state["usd_amount"], state["bdt_amount"], state["rate"],
             state["payment_method"], state["receive_info"], state.get("trx_proof", ""), created_at, state.get("currency", "USDT"),
             state.get("sender_number", ""), state.get("screenshot_file_id", "")),
        )
        order_id = c.lastrowid
        conn.commit()
        conn.close()
        order_data = dict(state)
        user_states.pop(uid, None)
        await message.reply_text(
            f"🟢 ✅ <b>আপনার অর্ডারটি সফলভাবে জমা হয়েছে!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>Order ID:</b> <code>#{order_id}</code>\n"
            f"📌 <b>ধরণ:</b> {order_data['order_type']} {order_data.get('currency', 'USDT')}\n"
            f"💵 <b>পরিমাণ:</b> <code>{order_data['usd_amount']} {order_data.get('currency', 'USDT')}</code>\n"
            f"💴 <b>টাকা:</b> <code>{order_data['bdt_amount']:.2f} BDT</code>\n"
            f"📲 <b>মেথড:</b> {order_data['payment_method']} | <b>নাম্বার:</b> <code>{order_data['receive_info']}</code>\n"
            f"🧾 <b>Transaction Hash:</b> <code>{order_data.get('trx_proof', '')}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ অ্যাডমিন আপনার লেনদেন যাচাই করে ৫-১০ মিনিটের মধ্যে অর্ডার সম্পন্ন করবেন।",
            reply_markup=main_menu_keyboard(uid),
        )
        badge = "🔴 💰 NEW SELL ORDER"
        admin_alert = (
            f"🔔 <b>{badge} — #{order_id}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {uname} (<code>{uid}</code>)\n"
            f"💵 <b>Amount:</b> <code>{order_data['usd_amount']} {order_data.get('currency', 'USDT')}</code>\n"
            f"💴 <b>Total BDT:</b> <code>{order_data['bdt_amount']:.2f} BDT</code> (Rate: {order_data['rate']})\n"
            f"📲 <b>Method:</b> {order_data['payment_method']} | <b>Number:</b> <code>{order_data['receive_info']}</code>\n"
            f"🧾 <b>Transaction Hash:</b> <code>{order_data.get('trx_proof', '')}</code>\n"
            f"🕒 <b>Time:</b> {created_at}"
        )
        adm_mk = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 ✅ Approve Order", callback_data=f"adm_order_approve_{order_id}"),
             InlineKeyboardButton("🔴 ❌ Reject Order", callback_data=f"adm_order_reject_{order_id}")],
        ])
        for adm_id in get_all_admin_ids():
            try:
                await context.bot.send_message(adm_id, admin_alert, reply_markup=adm_mk)
                if order_data.get("screenshot_file_id"):
                    await context.bot.send_photo(adm_id, order_data["screenshot_file_id"], caption=f"📸 Screenshot — Sell Order #{order_id}")
            except Exception:
                pass
        return

    if step == "ENTER_TRX_PROOF":
        state["trx_proof"] = text
        uname = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO orders (user_id, username, order_type, usd_amount, bdt_amount, rate, payment_method, receive_info, trx_proof, status, created_at, currency, sender_number, screenshot_file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?)
            """,
            (uid, uname, state["order_type"], state["usd_amount"], state["bdt_amount"], state["rate"],
             state["payment_method"], state["receive_info"], state["trx_proof"], created_at, state.get("currency", "USDT"),
             state.get("sender_number", ""), state.get("screenshot_file_id", "")),
        )
        order_id = c.lastrowid
        conn.commit()
        conn.close()
        order_data = dict(state)
        user_states.pop(uid, None)
        await message.reply_text(
            f"🟢 ✅ <b>আপনার অর্ডারটি সফলভাবে জমা হয়েছে!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>Order ID:</b> <code>#{order_id}</code>\n"
            f"📌 <b>ধরণ:</b> {order_data['order_type']} {order_data.get('currency', 'USDT')}\n"
            f"💵 <b>পরিমাণ:</b> <code>{order_data['usd_amount']} {order_data.get('currency', 'USDT')}</code>\n"
            f"💴 <b>টাকা:</b> <code>{order_data['bdt_amount']:.2f} BDT</code>\n"
            f"📲 <b>মেথড:</b> {order_data['payment_method']}\n"
            f"🧾 <b>প্রুফ/TrxID:</b> <code>{order_data['trx_proof']}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ অ্যাডমিন আপনার লেনদেন যাচাই করে ৫-১০ মিনিটের মধ্যে অর্ডার সম্পন্ন করবেন।",
            reply_markup=main_menu_keyboard(uid),
        )
        badge = "🟢 💵 NEW BUY ORDER" if order_data["order_type"] == "BUY" else "🔴 💰 NEW SELL ORDER"
        admin_alert = (
            f"🔔 <b>{badge} — #{order_id}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {uname} (<code>{uid}</code>)\n"
            f"💵 <b>Amount:</b> <code>{order_data['usd_amount']} {order_data.get('currency', 'USDT')}</code>\n"
            f"💴 <b>Total BDT:</b> <code>{order_data['bdt_amount']:.2f} BDT</code> (Rate: {order_data['rate']})\n"
            f"📲 <b>Method:</b> {order_data['payment_method']}\n"
            f"📥 <b>Receive Info:</b> <code>{order_data['receive_info']}</code>\n"
            f"🧾 <b>TrxID / Proof:</b> <code>{order_data['trx_proof']}</code>\n"
            + (f"📲 <b>Sender Number:</b> <code>{order_data.get('sender_number', '')}</code>\n" if order_data.get("sender_number") else "")
            + (f"📸 <b>Screenshot:</b> পাঠানো হয়েছে\n" if order_data.get("screenshot_file_id") else "")
            + f"🕒 <b>Time:</b> {created_at}"
        )
        adm_mk = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 ✅ Approve Order", callback_data=f"adm_order_approve_{order_id}"),
             InlineKeyboardButton("🔴 ❌ Reject Order", callback_data=f"adm_order_reject_{order_id}")],
        ])
        for adm_id in get_all_admin_ids():
            try:
                await context.bot.send_message(adm_id, admin_alert, reply_markup=adm_mk)
                if order_data.get("screenshot_file_id"):
                    await context.bot.send_photo(adm_id, order_data["screenshot_file_id"], caption=f"📸 Screenshot — Order #{order_id}")
            except Exception:
                pass
        return


# ====================================================================
# PHOTO HANDLER — screenshots for new Buy / Sell flows
# ====================================================================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    uid = message.from_user.id
    state = user_states.get(uid)
    if not state:
        await message.reply_text(
            "👇 নিচের রঙিন মেনু বাটন থেকে একটি অপশন সিলেক্ট করুন:",
            reply_markup=main_menu_keyboard(uid),
        )
        return
    step = state.get("step")
    if step == "SELL_SCREENSHOT":
        state["screenshot_file_id"] = message.photo[-1].file_id
        state["step"] = "SELL_PAYMENT_METHOD"
        await message.reply_text(
            "✅ স্ক্রিনশট পেয়েছি।\n\n👇 <b>এখন কিসে টাকা নেবেন, সিলেক্ট করুন:</b>",
            reply_markup=active_payment_methods_markup("sellpaymethod"),
        )
        return
    if step == "BUY_SCREENSHOT":
        # Buy proof is now sender number + screenshot only, NO TrxID (2026-10-29 21:24).
        state["screenshot_file_id"] = message.photo[-1].file_id
        uname = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO orders (user_id, username, order_type, usd_amount, bdt_amount, rate, payment_method, receive_info, trx_proof, status, created_at, currency, sender_number, screenshot_file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 'PENDING', ?, ?, ?, ?)
            """,
            (uid, uname, state["order_type"], state["usd_amount"], state["bdt_amount"], state["rate"],
             state["payment_method"], state["receive_info"], created_at, state.get("currency", "USDT"),
             state.get("sender_number", ""), state.get("screenshot_file_id", "")),
        )
        order_id = c.lastrowid
        conn.commit()
        conn.close()
        order_data = dict(state)
        user_states.pop(uid, None)
        await message.reply_text(
            f"🟢 ✅ <b>আপনার অর্ডারটি সফলভাবে জমা হয়েছে!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>Order ID:</b> <code>#{order_id}</code>\n"
            f"📌 <b>ধরণ:</b> {order_data['order_type']} {order_data.get('currency', 'USDT')}\n"
            f"💵 <b>পরিমাণ:</b> <code>{order_data['usd_amount']} {order_data.get('currency', 'USDT')}</code>\n"
            f"💴 <b>টাকা:</b> <code>{order_data['bdt_amount']:.2f} BDT</code>\n"
            f"📲 <b>মেথড:</b> {order_data['payment_method']} | <b>সেন্ডার নাম্বার:</b> <code>{order_data.get('sender_number', '')}</code>\n"
            "📸 <b>স্ক্রিনশট:</b> পাঠানো হয়েছে\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ অ্যাডমিন আপনার লেনদেন যাচাই করে ৫-১০ মিনিটের মধ্যে অর্ডার সম্পন্ন করবেন।",
            reply_markup=main_menu_keyboard(uid),
        )
        badge = "🟢 💵 NEW BUY ORDER"
        admin_alert = (
            f"🔔 <b>{badge} — #{order_id}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {uname} (<code>{uid}</code>)\n"
            f"💵 <b>Amount:</b> <code>{order_data['usd_amount']} {order_data.get('currency', 'USDT')}</code>\n"
            f"💴 <b>Total BDT:</b> <code>{order_data['bdt_amount']:.2f} BDT</code> (Rate: {order_data['rate']})\n"
            f"📲 <b>Method:</b> {order_data['payment_method']} | <b>Sender Number:</b> <code>{order_data.get('sender_number', '')}</code>\n"
            f"📥 <b>Receive Info:</b> <code>{order_data['receive_info']}</code>\n"
            f"📸 <b>Screenshot:</b> পাঠানো হয়েছে\n"
            f"🕒 <b>Time:</b> {created_at}"
        )
        adm_mk = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 ✅ Approve Order", callback_data=f"adm_order_approve_{order_id}"),
             InlineKeyboardButton("🔴 ❌ Reject Order", callback_data=f"adm_order_reject_{order_id}")],
        ])
        for adm_id in get_all_admin_ids():
            try:
                await context.bot.send_message(adm_id, admin_alert, reply_markup=adm_mk)
                if order_data.get("screenshot_file_id"):
                    await context.bot.send_photo(adm_id, order_data["screenshot_file_id"], caption=f"📸 Screenshot — Buy Order #{order_id}")
            except Exception:
                pass
        return
    if step == "BUY_SENDER_NUMBER":
        await message.reply_text(
            "⚠️ আগে নাম্বারটা লিখুন।\n\nটাকা যে নাম্বার থেকে পাঠিয়েছেন, সেই নাম্বারটা লিখে পাঠান, তারপর আমি আলাদাভাবে স্ক্রিনশট চাইবো।",
            reply_markup=cancel_keyboard(),
        )
        return
    if step == "SELL_TXHASH":
        await message.reply_text(
            "⚠️ আগে Transaction Hash লিখুন।\n\nTransaction Hash লেখার পর আমি আলাদাভাবে স্ক্রিনশট চাইবো।",
            reply_markup=cancel_keyboard(),
        )
        return
    await message.reply_text(
        "📸 স্ক্রিনশট শুধু অর্ডারের ওই ধাপে দিতে হবে।",
        reply_markup=main_menu_keyboard(uid),
    )


# ====================================================================
# CALLBACK QUERY HANDLER
# ====================================================================
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    if data == "user_cancel_flow":
        user_states.pop(uid, None)
        try:
            await query.edit_message_text("🔴 ❌ অর্ডার প্রক্রিয়া বাতিল করা হয়েছে।")
        except Exception:
            pass
        await context.bot.send_message(query.message.chat.id, "মেইন মেনু:", reply_markup=main_menu_keyboard(uid))
        return

    if data in ("buy_choice_usdt", "buy_choice_gram", "sell_choice_bep20", "sell_choice_gram"):
        is_buy = data.startswith("buy_choice")
        is_gram = data.endswith("gram")
        currency = "GRAM" if is_gram else "USDT"
        order_type = "BUY" if is_buy else "SELL"
        if is_gram:
            rate = float(get_setting("gram_buy_rate" if is_buy else "gram_sell_rate"))
            min_usd = float(get_setting("gram_buy_min" if is_buy else "gram_sell_min"))
            max_usd = float(get_setting("gram_buy_max" if is_buy else "gram_sell_max"))
            reserve = float(get_setting("gram_reserve"))
            unit = "Gram"
        else:
            rate = float(get_setting("buy_rate" if is_buy else "sell_rate"))
            min_usd = float(get_setting("buy_min" if is_buy else "sell_min"))
            max_usd = float(get_setting("buy_max" if is_buy else "sell_max"))
            reserve = float(get_setting("usdt_reserve"))
            unit = "USDT"
        user_states[uid] = {"step": "ENTER_USD_AMOUNT", "order_type": order_type, "rate": rate, "currency": currency, "new_buy": is_buy, "new_sell": not is_buy}
        if is_buy:
            prompt = (
                f"🟢 💵 <b>Buy {unit}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💠 <b>আজকের কেনার রেট:</b> <code>{rate} BDT</code>\n"
                f"💎 <b>আমাদের রিজার্ভ:</b> <code>{reserve} {unit}</code>\n"
                f"📉 <b>সর্বনিম্ন অর্ডার:</b> <code>{min_usd} {unit}</code>\n"
                f"📈 <b>সর্বোচ্চ অর্ডার:</b> <code>{max_usd} {unit}</code>\n\n"
                f"✍️ <b>আপনি কত {unit} কিনতে চান? সংখ্যায় লিখুন:</b>"
            )
        else:
            prompt = (
                f"🔴 💰 <b>Sell {unit}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💠 <b>আজকের বিক্রির রেট:</b> <code>{rate} BDT</code>\n"
                f"📉 <b>Minimum sell:</b> <code>{min_usd} {unit}</code>\n"
                f"📈 <b>Maximum sell:</b> <code>{max_usd} {unit}</code>\n\n"
                f"✍️ <b>আপনি কত {unit} বিক্রি করতে চান? সংখ্যায় লিখুন:</b>"
            )
        await context.bot.send_message(query.message.chat.id, prompt, reply_markup=cancel_keyboard())
        return

    if data in ("gram_buy", "gram_sell"):
        is_buy = data == "gram_buy"
        order_type = "BUY" if is_buy else "SELL"
        rate = float(get_setting("gram_buy_rate" if is_buy else "gram_sell_rate"))
        min_usd = float(get_setting("gram_buy_min" if is_buy else "gram_sell_min"))
        max_usd = float(get_setting("gram_buy_max" if is_buy else "gram_sell_max"))
        reserve = float(get_setting("gram_reserve"))
        user_states[uid] = {"step": "ENTER_USD_AMOUNT", "order_type": order_type, "rate": rate, "currency": "GRAM", "new_buy": order_type == "BUY", "new_sell": order_type == "SELL"}
        if is_buy:
            prompt = (
                "🟢 💎 <b>Buy Gram</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💠 <b>আজকের কেনার রেট:</b> <code>{rate} BDT / Gram</code>\n"
                f"💎 <b>আমাদের রিজার্ভ:</b> <code>{reserve} Gram</code>\n"
                f"📉 <b>সর্বনিম্ন অর্ডার:</b> <code>{min_usd} Gram</code>\n"
                f"📈 <b>সর্বোচ্চ অর্ডার:</b> <code>{max_usd} Gram</code>\n\n"
                "✍️ <b>আপনি কত Gram কিনতে চান? সংখ্যায় লিখুন (যেমন: 10 বা 25):</b>"
            )
        else:
            prompt = (
                "🔴 💎 <b>Sell Gram</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💠 <b>আজকের বিক্রির রেট:</b> <code>{rate} BDT / Gram</code>\n"
                f"📉 Minimum gram sell: <code>{min_usd} Gram</code>\n"
                f"📈 Maximum gram sell: <code>{max_usd} Gram</code>\n\n"
                "✍️ <b>আপনি কত Gram বিক্রি করতে চান? সংখ্যায় লিখুন (যেমন: 10 বা 50):</b>"
            )
        await context.bot.send_message(query.message.chat.id, prompt, reply_markup=cancel_keyboard())
        return

    if data.startswith("sellpaymethod_"):
        method = data.split("_", 1)[1]
        state = user_states.get(uid)
        if not state or state.get("step") != "SELL_PAYMENT_METHOD":
            await query.answer("⚠️ সেশন শেষ হয়ে গেছে, আবার শুরু করুন।", show_alert=True)
            return
        key_map = {"bKash": "bkash_active", "Nagad": "nagad_active", "Rocket": "rocket_active"}
        if get_setting(key_map.get(method, "")) != "1":
            await query.answer(f"🔴 {method} বর্তমানে বন্ধ আছে!", show_alert=True)
            return
        state["payment_method"] = method
        state["step"] = "SELL_NUMBER"
        await query.edit_message_text(
            f"🔴 আপনি পেমেন্ট মেথড হিসেবে <b>{method}</b> সিলেক্ট করেছেন।\n\n"
            f"📲 ✍️ <b>এখন আপনার নিজের {method} নাম্বারটি লিখে পাঠান যেখানে আপনি টাকা গ্রহণ করবেন:</b>"
        )
        return

    if data.startswith("paymethod_"):
        method = data.split("_", 1)[1]
        state = user_states.get(uid)
        if not state or state.get("step") != "SELECT_PAYMENT":
            await query.answer("⚠️ সেশন শেষ হয়ে গেছে, আবার শুরু করুন।", show_alert=True)
            return
        key_map = {"bKash": "bkash_active", "Nagad": "nagad_active", "Rocket": "rocket_active"}
        if get_setting(key_map.get(method, "")) != "1":
            await query.answer(f"🔴 {method} বর্তমানে বন্ধ আছে!", show_alert=True)
            return
        state["payment_method"] = method
        state["step"] = "ENTER_RECEIVE_INFO"
        if state["order_type"] == "BUY":
            _recv_lbl = "Gram Address" if state.get("currency") == "GRAM" else "BEP20 Address"
            await query.edit_message_text(
                f"🟢 আপনি পেমেন্ট মেথড হিসেবে <b>{method}</b> সিলেক্ট করেছেন।\n\n"
                f"🟡 ✍️ <b>এখন আপনার {_recv_lbl} লিখে পাঠান যেখানে আপনি {state.get('currency', 'USDT')} গ্রহণ করবেন:</b>"
            )
        else:
            await query.edit_message_text(
                f"🔴 আপনি পেমেন্ট মেথড হিসেবে <b>{method}</b> সিলেক্ট করেছেন।\n\n"
                f"📲 ✍️ <b>এখন আপনার নিজের {method} নাম্বারটি লিখে পাঠান যেখানে আপনি টাকা গ্রহণ করবেন:</b>"
            )
        return

    if data.startswith("adm_"):
        if not is_admin(uid):
            await query.answer("🔴 শুধুমাত্র অ্যাডমিন এটি ব্যবহার করতে পারবেন!", show_alert=True)
            return
        await handle_admin_callbacks(update, context)
        return


async def handle_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data

    toggle_map = {
        "adm_toggle_bot": ("bot_active", "Bot Status"),
        "adm_toggle_bkash": ("bkash_active", "bKash Payment"),
        "adm_toggle_nagad": ("nagad_active", "Nagad Payment"),
        "adm_toggle_rocket": ("rocket_active", "Rocket Payment"),
    }
    if data in toggle_map:
        setting_key, label = toggle_map[data]
        current = get_setting(setting_key)
        new_val = "0" if current == "1" else "1"
        set_setting(setting_key, new_val)
        status_label = "🟢 ON" if new_val == "1" else "🔴 OFF"
        await query.answer(f"✅ {label} এখন {status_label} করা হয়েছে!")
        _t, _m = _admin_section_view(query.message.text or "")
        await query.edit_message_text(_t, reply_markup=_m)
        return

    if data == "adm_refresh":
        await query.answer("🔄 Admin Panel আপডেট করা হয়েছে!")
        try:
            _t, _m = _admin_section_view(query.message.text or "")
            await query.edit_message_text(_t, reply_markup=_m)
        except Exception:
            pass
        return

    if data == "adm_open_dollar":
        await query.answer()
        await query.edit_message_text(get_dollar_setting_text(), reply_markup=dollar_setting_markup())
        return
    if data == "adm_open_gram":
        await query.answer()
        await query.edit_message_text(get_gram_setting_text(), reply_markup=gram_setting_markup())
        return
    if data == "adm_open_payment":
        await query.answer()
        await query.edit_message_text(get_payment_setting_text(), reply_markup=payment_setting_markup())
        return
    if data == "adm_open_bot":
        await query.answer()
        await query.edit_message_text(get_bot_setting_text(), reply_markup=bot_setting_markup())
        return
    if data == "adm_back_admin":
        await query.answer()
        await query.edit_message_text(get_admin_dashboard_text(), reply_markup=admin_panel_inline_markup())
        return
    if data == "adm_main_menu":
        await query.answer()
        await context.bot.send_message(query.message.chat.id, "মেইন মেনু:", reply_markup=main_menu_keyboard(uid))
        return

    setting_prompts = {
        "adm_set_buy_rate": ("buy_rate", "🟢 নতুন <b>BUY RET (BDT)</b> লিখুন (যেমন: 125.5):"),
        "adm_set_sell_rate": ("sell_rate", "🔴 নতুন <b>SELL RET (BDT)</b> লিখুন (যেমন: 121.0):"),
        "adm_set_reserve": ("usdt_reserve", "💎 নতুন <b>RESERVE</b> পরিমাণ লিখুন (যেমন: 500):"),
        "adm_set_buy_min": ("buy_min", "🟢 <b>BUY DOLLAR MIN</b> লিখুন (যেমন: 5):"),
        "adm_set_buy_max": ("buy_max", "🟢 <b>BUY DOLLAR MAX</b> লিখুন (যেমন: 1000):"),
        "adm_set_sell_min": ("sell_min", "🔴 <b>SELL DOLLAR MIN</b> লিখুন (যেমন: 5):"),
        "adm_set_sell_max": ("sell_max", "🔴 <b>SELL DOLLAR MAX</b> লিখুন (যেমন: 1000):"),
        "adm_set_gram_buy_rate": ("gram_buy_rate", "💎 নতুন <b>GRAM BUY RET (BDT)</b> লিখুন (যেমন: 125.5):"),
        "adm_set_gram_sell_rate": ("gram_sell_rate", "💎 নতুন <b>GRAM SELL RET (BDT)</b> লিখুন (যেমন: 121.0):"),
        "adm_set_gram_reserve": ("gram_reserve", "💎 নতুন <b>GRAM RESERVE</b> পরিমাণ লিখুন (যেমন: 500):"),
        "adm_set_gram_buy_min": ("gram_buy_min", "💎 <b>BUY GRAM MIN</b> লিখুন (যেমন: 5):"),
        "adm_set_gram_buy_max": ("gram_buy_max", "💎 <b>BUY GRAM MAX</b> লিখুন (যেমন: 1000):"),
        "adm_set_gram_sell_min": ("gram_sell_min", "💎 <b>SELL GRAM MIN</b> লিখুন (যেমন: 5):"),
        "adm_set_gram_sell_max": ("gram_sell_max", "💎 <b>SELL GRAM MAX</b> লিখুন (যেমন: 1000):"),
        "adm_set_bkash_no": ("bkash_number", "🟣 নতুন <b>bKash নাম্বার</b> লিখুন (যেমন: 017XXXXXXXX Personal):"),
        "adm_set_nagad_no": ("nagad_number", "🟠 নতুন <b>Nagad নাম্বার</b> লিখুন (যেমন: 018XXXXXXXX Personal):"),
        "adm_set_rocket_no": ("rocket_number", "🔵 নতুন <b>Rocket নাম্বার</b> লিখুন (যেমন: 019XXXXXXXX Personal):"),
        "adm_set_bep20_address": ("bep20_address", "🟡 নতুন <b>BEP20 Address</b> লিখুন:"),
        "adm_set_gram_address": ("gram_address", "💎 নতুন <b>Gram Address</b> লিখুন:"),
        "adm_set_support": ("support_user", "📞 নতুন <b>Support Username</b> লিখুন (যেমন: @MySupport):"),
        "adm_set_notice": ("notice_text", "📢 নতুন <b>Notice / ঘোষণা</b> টেক্সট লিখুন:"),
    }
    if data in setting_prompts:
        s_key, prompt_msg = setting_prompts[data]
        user_states[uid] = {"step": "ADMIN_SET_VALUE", "setting_key": s_key}
        await context.bot.send_message(query.message.chat.id, prompt_msg, reply_markup=cancel_keyboard())
        return

    if data == "adm_broadcast":
        user_states[uid] = {"step": "ADMIN_BROADCAST"}
        await context.bot.send_message(
            query.message.chat.id,
            "📣 <b>সকল ইউজারের কাছে যে মেসেজটি পাঠাতে চান তা লিখুন:</b>",
            reply_markup=cancel_keyboard(),
        )
        return

    if data == "adm_add_admin":
        user_states[uid] = {"step": "ADMIN_ADD_NEW"}
        await context.bot.send_message(
            query.message.chat.id,
            "➕ <b>নতুন অ্যাডমিনের Telegram Numeric User ID লিখুন:</b>",
            reply_markup=cancel_keyboard(),
        )
        return

    if data == "adm_pending_orders":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT order_id, user_id, username, order_type, usd_amount, bdt_amount, payment_method, receive_info, trx_proof, created_at "
            "FROM orders WHERE status = 'PENDING' ORDER BY order_id ASC LIMIT 10"
        )
        rows = c.fetchall()
        conn.close()
        if not rows:
            await query.answer("✅ কোনো পেন্ডিং অর্ডার নেই!", show_alert=True)
            return
        for r in rows:
            oid, o_uid, uname, otype, usd, bdt, pm, rec_info, proof, cat = r
            badge = "🟢 BUY ORDER" if otype == "BUY" else "🔴 SELL ORDER"
            msg = (
                f"⏳ <b>{badge} — #{oid}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>User:</b> {uname} (<code>{o_uid}</code>)\n"
                f"💵 <b>Amount:</b> <code>{usd} USDT</code>\n"
                f"💴 <b>Total BDT:</b> <code>{bdt:.2f} BDT</code>\n"
                f"📲 <b>Method:</b> {pm}\n"
                f"📥 <b>Receive Info:</b> <code>{rec_info}</code>\n"
                f"🧾 <b>TrxID / Proof:</b> <code>{proof}</code>\n"
                f"🕒 <b>Time:</b> {cat}"
            )
            mk = InlineKeyboardMarkup([
                [InlineKeyboardButton("🟢 ✅ Approve", callback_data=f"adm_order_approve_{oid}"),
                 InlineKeyboardButton("🔴 ❌ Reject", callback_data=f"adm_order_reject_{oid}")],
            ])
            await context.bot.send_message(query.message.chat.id, msg, reply_markup=mk)
        return

    if data.startswith("adm_order_approve_") or data.startswith("adm_order_reject_"):
        parts = data.split("_")
        action = parts[2]
        order_id = int(parts[3])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute(
                "SELECT user_id, order_type, usd_amount, bdt_amount, payment_method, status, currency FROM orders WHERE order_id = ?",
                (order_id,),
            )
            _r = c.fetchone()
            if _r and len(_r) == 7:
                o_uid, otype, usd, bdt, pm, current_st, _cur = _r
            else:
                raise ValueError("no currency")
        except Exception:
            c.execute(
                "SELECT user_id, order_type, usd_amount, bdt_amount, payment_method, status FROM orders WHERE order_id = ?",
                (order_id,),
            )
            o_uid, otype, usd, bdt, pm, current_st = c.fetchone()
            _cur = "USDT"
        if o_uid is None:
            conn.close()
            await query.answer("⚠️ অর্ডারটি পাওয়া যায়নি!", show_alert=True)
            return
        if current_st != "PENDING":
            conn.close()
            await query.answer(f"⚠️ এই অর্ডারটি আগেই {current_st} করা হয়েছে!", show_alert=True)
            return
        new_status = "APPROVED" if action == "approve" else "REJECTED"
        c.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
        conn.commit()
        conn.close()
        if new_status == "APPROVED" and otype == "BUY":
            try:
                _rk = "gram_reserve" if _cur == "GRAM" else "usdt_reserve"
                cur_res = float(get_setting(_rk))
                set_setting(_rk, f"{max(0.0, cur_res - float(usd)):.2f}")
            except Exception:
                pass
        elif new_status == "APPROVED" and otype == "SELL":
            try:
                _rk = "gram_reserve" if _cur == "GRAM" else "usdt_reserve"
                cur_res = float(get_setting(_rk))
                set_setting(_rk, f"{cur_res + float(usd):.2f}")
            except Exception:
                pass
        badge_text = "🟢 ✅ APPROVED (সম্পন্ন)" if new_status == "APPROVED" else "🔴 ❌ REJECTED (বাতিল)"
        try:
            await query.edit_message_text(
                query.message.text_html + f"\n\n━━━━━━━━━━━━━━\n📌 <b>Final Status:</b> {badge_text}"
            )
        except Exception:
            pass
        await query.answer(f"Order #{order_id} {new_status}!")
        try:
            if new_status == "APPROVED":
                await context.bot.send_message(
                    o_uid,
                    f"🟢 🎉 <b>অভিনন্দন! আপনার Order #{order_id} ({otype} {usd} USDT) সম্পন্ন হয়েছে!</b>\n"
                    f"💵 পরিমাণ: <code>{usd} USDT</code> ({bdt:.2f} BDT)\n"
                    "আমাদের সাথে লেনদেন করার জন্য ধন্যবাদ। ❤️",
                )
            else:
                await context.bot.send_message(
                    o_uid,
                    f"🔴 ❌ <b>দুঃখিত! আপনার Order #{order_id} ({otype} {usd} USDT) বাতিল করা হয়েছে।</b>\n"
                    f"বিস্তারিত জানতে সাপোর্টে যোগাযোগ করুন: {get_setting('support_user')}",
                )
        except Exception:
            pass


# ====================================================================
# WEB KEEP-ALIVE (Render free Web Service er jonno)
# Render Web Service ekta Port khola asha kore; bot shudhu polling
# korle "Timed Out / Deploy failed" hoy. Ei chhoto web server PORT-e
# shone, tai Deploy Live thake. Bot er kaj ager motoi polling-e chole.
# ====================================================================
web_app = Flask(__name__)

@web_app.route("/")
def _web_home():
    return "Binance Dollar Buy-Sell Bot is Running", 200

def _run_web_server():
    _port = int(os.environ.get("PORT", "10000"))
    web_app.run(host="0.0.0.0", port=_port)


# ====================================================================
# MAIN ENTRYPOINT
# ====================================================================
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN environment variable set korun!")
    init_db()
    print("====================================================")
    print("💎 Binance Dollar Buy-Sell Bot is Running...")
    print("⚙️ Use /admin inside Telegram to configure everything!")
    print("====================================================")
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .defaults(Defaults(parse_mode="HTML"))
        .build()
    )
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    threading.Thread(target=_run_web_server, daemon=True).start()
    app.run_polling()


if __name__ == "__main__":
    main()
