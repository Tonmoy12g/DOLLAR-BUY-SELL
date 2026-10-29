#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================
💎 BINANCE DOLLAR (USDT) BUY & SELL TELEGRAM BOT (FULL ADMIN PANEL)
====================================================================
Features:
- Colorful Emoji-Styled Reply & Inline Buttons (🟢 Buy, 🔴 Sell, 🟡 Rate, etc.)
- One-Click ON/OFF Toggle for bKash, Nagad, Rocket & Bot Status from Admin Panel
- 100% Configurable from Telegram Admin Panel (Rates, Numbers, Binance UID,
  Min Limit, USDT Reserve, Support Link, Notice, Broadcast, Order Approval)
- Built-in SQLite Database (auto-creates `dollar_bot.db`, saves everything)

Setup Instructions:
1. Install library:
   pip install pyTelegramBotAPI
2. Put your BOT_TOKEN (from @BotFather) and ADMIN_ID (from @userinfobot) below.
3. Run the bot:
   python binance_dollar_bot.py
====================================================================
"""

import os
import sqlite3
from datetime import datetime
import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# ====================================================================
# 🔧 BASIC CONFIGURATION (শুধুমাত্র এখানে Token ও Admin ID বসান, বাকি সব বট থেকেই সেট করা যাবে)
# ====================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))  # আপনার Telegram Numeric User ID দিন
DB_PATH = "dollar_bot.db"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# In-memory step state tracker for multi-step user & admin inputs
user_states = {}


# ====================================================================
# 🗄️ DATABASE SETUP & HELPER FUNCTIONS
# ====================================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Settings table (key-value)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    # Users table
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

    # Orders table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            order_type TEXT,      -- 'BUY' or 'SELL'
            usd_amount REAL,
            bdt_amount REAL,
            rate REAL,
            payment_method TEXT,  -- 'bKash', 'Nagad', 'Rocket'
            receive_info TEXT,    -- Binance UID (for BUY) or User's Mobile Number (for SELL)
            trx_proof TEXT,       -- TrxID / Sender Number / Binance Pay Proof
            status TEXT DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'REJECTED'
            created_at TEXT
        )
        """
    )

    # Default settings (All configurable via Admin Panel)
    default_settings = {
        "bot_active": "1",               # 1 = 🟢 ON, 0 = 🔴 OFF
        "buy_rate": "125.0",             # 1 USDT Buy Price in BDT
        "sell_rate": "121.0",            # 1 USDT Sell Price in BDT
        "min_usd": "5.0",                # Minimum Buy/Sell USD
        "usdt_reserve": "500.0",         # Available USDT Reserve
        "bkash_active": "1",             # 1 = 🟢 ON, 0 = 🔴 OFF
        "nagad_active": "1",             # 1 = 🟢 ON, 0 = 🔴 OFF
        "rocket_active": "1",            # 1 = 🟢 ON, 0 = 🔴 OFF
        "bkash_number": "017XXXXXXXX (Personal)",
        "nagad_number": "018XXXXXXXX (Personal)",
        "rocket_number": "019XXXXXXXX (Personal)",
        "binance_uid": "889900112 (Binance Pay UID)",
        "support_user": "@YourSupportUsername",
        "notice_text": "⚡ ১০০% ট্রাস্টেড ও দ্রুত Binance USDT Buy-Sell সার্ভিস। অর্ডার করার ৫-১০ মিনিটের মধ্যে ডেলিভারি পাবেন।",
    }

    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Ensure MAIN_ADMIN_ID is registered as admin
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
    if user_id == MAIN_ADMIN_ID:
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
    if MAIN_ADMIN_ID not in ids:
        ids.append(MAIN_ADMIN_ID)
    return ids


# ====================================================================
# 🎨 COLORFUL BUTTON KEYBOARDS (USER & ADMIN)
# ====================================================================
BTN_BUY = "🟢 💵 Buy Dollar (USDT)"
BTN_SELL = "🔴 💰 Sell Dollar (USDT)"
BTN_RATE = "🟡 📊 Today's Rate"
BTN_ORDERS = "🔵 📜 My Orders"
BTN_SUPPORT = "🟣 👨‍💼 Support"
BTN_ADMIN = "⚙️ 👑 Admin Panel"
BTN_CANCEL = "🔴 ❌ Cancel Action"


def main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton(BTN_BUY),
        KeyboardButton(BTN_SELL),
    )
    markup.add(
        KeyboardButton(BTN_RATE),
        KeyboardButton(BTN_ORDERS),
    )
    if is_admin(user_id):
        markup.add(
            KeyboardButton(BTN_SUPPORT),
            KeyboardButton(BTN_ADMIN),
        )
    else:
        markup.add(KeyboardButton(BTN_SUPPORT))
    return markup


def cancel_keyboard() -> ReplyKeyboardMarkup:
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton(BTN_CANCEL))
    return markup


def active_payment_methods_markup(prefix: str) -> InlineKeyboardMarkup:
    """
    Returns colorful inline buttons ONLY for payment methods that are turned ON by Admin.
    """
    markup = InlineKeyboardMarkup(row_width=1)
    if get_setting("bkash_active") == "1":
        markup.add(InlineKeyboardButton("🟣 📲 bKash (বিকাশ)", callback_data=f"{prefix}_bKash"))
    if get_setting("nagad_active") == "1":
        markup.add(InlineKeyboardButton("🟠 📲 Nagad (নগদ)", callback_data=f"{prefix}_Nagad"))
    if get_setting("rocket_active") == "1":
        markup.add(InlineKeyboardButton("🔵 📲 Rocket (রকেট)", callback_data=f"{prefix}_Rocket"))
    markup.add(InlineKeyboardButton("🔴 ❌ Cancel Order", callback_data="user_cancel_flow"))
    return markup


def has_any_active_payment() -> bool:
    return any(
        get_setting(k) == "1" for k in ("bkash_active", "nagad_active", "rocket_active")
    )


def admin_panel_inline_markup() -> InlineKeyboardMarkup:
    """
    Full Admin Control Panel with live ON/OFF status indicators & all settings buttons.
    """
    bot_st = "🟢 ON" if get_setting("bot_active") == "1" else "🔴 OFF"
    bkash_st = "🟢 ON" if get_setting("bkash_active") == "1" else "🔴 OFF"
    nagad_st = "🟢 ON" if get_setting("nagad_active") == "1" else "🔴 OFF"
    rocket_st = "🟢 ON" if get_setting("rocket_active") == "1" else "🔴 OFF"

    buy_r = get_setting("buy_rate")
    sell_r = get_setting("sell_rate")
    min_u = get_setting("min_usd")
    res_u = get_setting("usdt_reserve")

    markup = InlineKeyboardMarkup(row_width=2)

    # Row 1: Bot Master Switch
    markup.row(
        InlineKeyboardButton(f"🤖 Bot Status: {bot_st} (Click to Toggle)", callback_data="adm_toggle_bot")
    )

    # Row 2 & 3: Payment Methods ON/OFF Toggles
    markup.row(
        InlineKeyboardButton(f"🟣 bKash: {bkash_st}", callback_data="adm_toggle_bkash"),
        InlineKeyboardButton(f"🟠 Nagad: {nagad_st}", callback_data="adm_toggle_nagad"),
    )
    markup.row(
        InlineKeyboardButton(f"🔵 Rocket: {rocket_st}", callback_data="adm_toggle_rocket"),
    )

    # Row 4 & 5: Rate, Reserve & Minimum Limits
    markup.row(
        InlineKeyboardButton(f"🟢 Buy Rate: {buy_r}৳", callback_data="adm_set_buy_rate"),
        InlineKeyboardButton(f"🔴 Sell Rate: {sell_r}৳", callback_data="adm_set_sell_rate"),
    )
    markup.row(
        InlineKeyboardButton(f"💎 Reserve: {res_u}$", callback_data="adm_set_reserve"),
        InlineKeyboardButton(f"📉 Min Order: {min_u}$", callback_data="adm_set_min_usd"),
    )

    # Row 6 & 7: Payment Numbers & Binance UID
    markup.row(
        InlineKeyboardButton("🟣 Set bKash No", callback_data="adm_set_bkash_no"),
        InlineKeyboardButton("🟠 Set Nagad No", callback_data="adm_set_nagad_no"),
    )
    markup.row(
        InlineKeyboardButton("🔵 Set Rocket No", callback_data="adm_set_rocket_no"),
        InlineKeyboardButton("🟡 Set Binance UID", callback_data="adm_set_binance_uid"),
    )

    # Row 8: Support, Notice, Pending Orders, Broadcast
    markup.row(
        InlineKeyboardButton("📞 Set Support ID", callback_data="adm_set_support"),
        InlineKeyboardButton("📢 Set Notice Text", callback_data="adm_set_notice"),
    )
    markup.row(
        InlineKeyboardButton("📦 Pending Orders", callback_data="adm_pending_orders"),
        InlineKeyboardButton("📣 Broadcast Msg", callback_data="adm_broadcast"),
    )
    markup.row(
        InlineKeyboardButton("➕ Add Admin ID", callback_data="adm_add_admin"),
        InlineKeyboardButton("🔄 Refresh Panel", callback_data="adm_refresh"),
    )
    return markup


def get_admin_dashboard_text() -> str:
    bot_st = "🟢 ACTIVE" if get_setting("bot_active") == "1" else "🔴 OFF (Maintenance)"
    bkash_st = "🟢 ON" if get_setting("bkash_active") == "1" else "🔴 OFF"
    nagad_st = "🟢 ON" if get_setting("nagad_active") == "1" else "🔴 OFF"
    rocket_st = "🟢 ON" if get_setting("rocket_active") == "1" else "🔴 OFF"

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
        f"🟢 <b>Buy Rate:</b> <code>{get_setting('buy_rate')} BDT/$</code>\n"
        f"🔴 <b>Sell Rate:</b> <code>{get_setting('sell_rate')} BDT/$</code>\n"
        f"💎 <b>USDT Reserve:</b> <code>{get_setting('usdt_reserve')} USDT</code>\n"
        f"📉 <b>Min Limit:</b> <code>{get_setting('min_usd')} USDT</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💳 <b>PAYMENT METHODS STATUS & NUMBERS:</b>\n"
        f"🟣 <b>bKash [{bkash_st}]:</b> <code>{get_setting('bkash_number')}</code>\n"
        f"🟠 <b>Nagad [{nagad_st}]:</b> <code>{get_setting('nagad_number')}</code>\n"
        f"🔵 <b>Rocket [{rocket_st}]:</b> <code>{get_setting('rocket_number')}</code>\n"
        f"🟡 <b>Binance UID:</b> <code>{get_setting('binance_uid')}</code>\n"
        f"🟣 <b>Support:</b> {get_setting('support_user')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <i>নিচের রঙিন বাটনগুলোতে ক্লিক করে যেকোনো অপশন ON/OFF বা পরিবর্তন করুন:</i>"
    )


# ====================================================================
# 🚀 START & RATE DISPLAY HANDLERS
# ====================================================================
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    register_user(message.from_user)
    user_states.pop(message.from_user.id, None)

    welcome_text = (
        f"👋 <b>স্বাগতম {message.from_user.first_name}!</b>\n"
        "💎 <b>Binance Dollar (USDT) Buy & Sell Bot</b>-এ আপনাকে স্বাগতম।\n\n"
        f"📢 <b>নোটিশ:</b> {get_setting('notice_text')}\n\n"
        f"🟢 <b>ডলার কেনার রেট (Buy):</b> <code>{get_setting('buy_rate')} BDT</code>\n"
        f"🔴 <b>ডলার বিক্রির রেট (Sell):</b> <code>{get_setting('sell_rate')} BDT</code>\n"
        f"💎 <b>আমাদের রিজার্ভ:</b> <code>{get_setting('usdt_reserve')} USDT</code>\n\n"
        "👇 <b>লেনদেন শুরু করতে নিচের রঙিন বাটন ব্যবহার করুন:</b>"
    )
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=main_menu_keyboard(message.from_user.id),
    )


@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🔴 ❌ দুঃখিত! শুধুমাত্র অ্যাডমিন এই প্যানেলে প্রবেশ করতে পারবেন।")
        return
    user_states.pop(message.from_user.id, None)
    bot.send_message(
        message.chat.id,
        get_admin_dashboard_text(),
        reply_markup=admin_panel_inline_markup(),
    )


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
        f"📉 <b>Minimum Order:</b> <code>{get_setting('min_usd')} USDT</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📲 <b>সক্রিয় পেমেন্ট মেথডসমূহ:</b>\n"
        f"🟣 <b>bKash:</b> {bk}\n"
        f"🟠 <b>Nagad:</b> {ng}\n"
        f"🔵 <b>Rocket:</b> {rk}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 {get_setting('notice_text')}"
    )


# ====================================================================
# 🟢 BUY & 🔴 SELL USER FLOWS
# ====================================================================
@bot.message_handler(func=lambda m: m.text == BTN_CANCEL)
def handle_cancel_button(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(
        message.chat.id,
        "🔴 ❌ আপনার চলমান কার্যক্রম বাতিল করা হয়েছে। মেইন মেনুতে ফিরে আসা হলো:",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )


@bot.message_handler(func=lambda m: m.text == BTN_RATE)
def handle_rate_button(message):
    bot.send_message(
        message.chat.id,
        build_rate_card(),
        reply_markup=main_menu_keyboard(message.from_user.id),
    )


@bot.message_handler(func=lambda m: m.text == BTN_SUPPORT)
def handle_support_button(message):
    sup = get_setting("support_user")
    bot.send_message(
        message.chat.id,
        f"🟣 👨‍💼 <b>লাইভ সাপোর্ট সেন্টার</b>\n\n"
        f"যেকোনো সমস্যা বা জরুরি প্রয়োজনে আমাদের অ্যাডমিনের সাথে যোগাযোগ করুন:\n"
        f"👉 <b>Support:</b> {sup}",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )


@bot.message_handler(func=lambda m: m.text == BTN_ORDERS)
def handle_my_orders(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT order_id, order_type, usd_amount, bdt_amount, payment_method, status, created_at "
        "FROM orders WHERE user_id = ? ORDER BY order_id DESC LIMIT 10",
        (message.from_user.id,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        bot.send_message(
            message.chat.id,
            "🔵 📜 আপনার এখনো কোনো অর্ডার নেই।",
            reply_markup=main_menu_keyboard(message.from_user.id),
        )
        return

    text = "🔵 📜 <b>আপনার সর্বশেষ ১০টি অর্ডার:</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for r in rows:
        oid, otype, usd, bdt, pm, status, cat = r
        st_icon = "🟡 PENDING" if status == "PENDING" else ("🟢 APPROVED" if status == "APPROVED" else "🔴 REJECTED")
        type_icon = "🟢 BUY" if otype == "BUY" else "🔴 SELL"
        text += (
            f"🆔 <b>Order #{oid}</b> ({type_icon})\n"
            f"💵 Amount: <code>{usd}$</code> ({bdt:.2f} BDT) | 📲 {pm}\n"
            f"📌 Status: <b>{st_icon}</b> | 🕒 {cat}\n"
            "──────────────────────\n"
        )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard(message.from_user.id))


@bot.message_handler(func=lambda m: m.text == BTN_ADMIN)
def handle_admin_button(message):
    cmd_admin(message)


@bot.message_handler(func=lambda m: m.text in [BTN_BUY, BTN_SELL])
def handle_start_buy_or_sell(message):
    register_user(message.from_user)

    if get_setting("bot_active") != "1" and not is_admin(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "🔴 ⚠️ বট বর্তমানে সাময়িক বিরতিতে (Maintenance) আছে। অনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন।",
        )
        return

    if not has_any_active_payment():
        bot.send_message(
            message.chat.id,
            "🔴 ⚠️ বর্তমানে সকল পেমেন্ট মেথড (bKash/Nagad/Rocket) সাময়িকভাবে বন্ধ আছে। পরে চেষ্টা করুন।",
        )
        return

    is_buy = message.text == BTN_BUY
    order_type = "BUY" if is_buy else "SELL"
    rate = float(get_setting("buy_rate" if is_buy else "sell_rate"))
    min_usd = float(get_setting("min_usd"))
    reserve = float(get_setting("usdt_reserve"))

    user_states[message.from_user.id] = {
        "step": "ENTER_USD_AMOUNT",
        "order_type": order_type,
        "rate": rate,
    }

    if is_buy:
        prompt = (
            "🟢 💵 <b>Buy Binance Dollar (USDT)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💠 <b>আজকের কেনার রেট:</b> <code>{rate} BDT / $1</code>\n"
            f"💎 <b>আমাদের রিজার্ভ:</b> <code>{reserve} USDT</code>\n"
            f"📉 <b>সর্বনিম্ন অর্ডার:</b> <code>{min_usd} USDT</code>\n\n"
            "✍️ <b>আপনি কত ডলার (USDT) কিনতে চান? সংখ্যায় লিখুন (যেমন: 10 বা 25):</b>"
        )
    else:
        prompt = (
            "🔴 💰 <b>Sell Binance Dollar (USDT)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💠 <b>আজকের বিক্রির রেট:</b> <code>{rate} BDT / $1</code>\n"
            f"📉 <b>সর্বনিম্ন অর্ডার:</b> <code>{min_usd} USDT</code>\n\n"
            "✍️ <b>আপনি কত ডলার (USDT) বিক্রি করতে চান? সংখ্যায় লিখুন (যেমন: 10 বা 50):</b>"
        )

    bot.send_message(message.chat.id, prompt, reply_markup=cancel_keyboard())


# ====================================================================
# 🔄 CALLBACK QUERY HANDLER (PAYMENT SELECT, CONFIRM, ADMIN CONTROLS)
# ====================================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.from_user.id
    data = call.data

    # 1. User cancels flow
    if data == "user_cancel_flow":
        user_states.pop(uid, None)
        bot.edit_message_text(
            "🔴 ❌ অর্ডার প্রক্রিয়া বাতিল করা হয়েছে।",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.send_message(
            call.message.chat.id,
            "মেইন মেনু:",
            reply_markup=main_menu_keyboard(uid),
        )
        return

    # 2. User selects payment method (bKash / Nagad / Rocket)
    if data.startswith("paymethod_"):
        method = data.split("_", 1)[1]
        state = user_states.get(uid)
        if not state or state.get("step") != "SELECT_PAYMENT":
            bot.answer_callback_query(call.id, "⚠️ সেশন শেষ হয়ে গেছে, আবার শুরু করুন।", show_alert=True)
            return

        # Verify payment method is still active
        key_map = {"bKash": "bkash_active", "Nagad": "nagad_active", "Rocket": "rocket_active"}
        if get_setting(key_map.get(method, "")) != "1":
            bot.answer_callback_query(call.id, f"🔴 {method} বর্তমানে বন্ধ আছে!", show_alert=True)
            return

        state["payment_method"] = method
        state["step"] = "ENTER_RECEIVE_INFO"

        if state["order_type"] == "BUY":
            bot.edit_message_text(
                f"🟢 আপনি পেমেন্ট মেথড হিসেবে <b>{method}</b> সিলেক্ট করেছেন।\n\n"
                "🟡 ✍️ <b>এখন আপনার Binance Pay ID / UID (অথবা Binance Email) লিখে পাঠান যেখানে আপনি ডলার (USDT) গ্রহণ করবেন:</b>",
                call.message.chat.id,
                call.message.message_id,
            )
        else:
            bot.edit_message_text(
                f"🔴 আপনি পেমেন্ট মেথড হিসেবে <b>{method}</b> সিলেক্ট করেছেন।\n\n"
                f"📲 ✍️ <b>এখন আপনার নিজের {method} নাম্বারটি লিখে পাঠান যেখানে আপনি টাকা গ্রহণ করবেন:</b>",
                call.message.chat.id,
                call.message.message_id,
            )
        return

    # 3. Admin Panel Callbacks
    if data.startswith("adm_"):
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "🔴 শুধুমাত্র অ্যাডমিন এটি ব্যবহার করতে পারবেন!", show_alert=True)
            return
        handle_admin_callbacks(call)
        return


def handle_admin_callbacks(call):
    uid = call.from_user.id
    data = call.data

    # One-Click Toggles for Bot Status, bKash, Nagad, Rocket
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
        bot.answer_callback_query(call.id, f"✅ {label} এখন {status_label} করা হয়েছে!")
        bot.edit_message_text(
            get_admin_dashboard_text(),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=admin_panel_inline_markup(),
        )
        return

    if data == "adm_refresh":
        bot.answer_callback_query(call.id, "🔄 Admin Panel আপডেট করা হয়েছে!")
        try:
            bot.edit_message_text(
                get_admin_dashboard_text(),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=admin_panel_inline_markup(),
            )
        except Exception:
            pass
        return

    # Settings change prompts from Admin Panel
    setting_prompts = {
        "adm_set_buy_rate": ("buy_rate", "🟢 নতুন <b>Buy Rate (BDT)</b> লিখুন (যেমন: 125.5):"),
        "adm_set_sell_rate": ("sell_rate", "🔴 নতুন <b>Sell Rate (BDT)</b> লিখুন (যেমন: 121.0):"),
        "adm_set_reserve": ("usdt_reserve", "💎 নতুন <b>USDT Reserve</b> পরিমাণ লিখুন (যেমন: 500):"),
        "adm_set_min_usd": ("min_usd", "📉 সর্বনিম্ন কত ডলার অর্ডার করা যাবে (<b>Min USD</b>) লিখুন (যেমন: 5):"),
        "adm_set_bkash_no": ("bkash_number", "🟣 নতুন <b>bKash নাম্বার</b> লিখুন (যেমন: 017XXXXXXXX Personal):"),
        "adm_set_nagad_no": ("nagad_number", "🟠 নতুন <b>Nagad নাম্বার</b> লিখুন (যেমন: 018XXXXXXXX Personal):"),
        "adm_set_rocket_no": ("rocket_number", "🔵 নতুন <b>Rocket নাম্বার</b> লিখুন (যেমন: 019XXXXXXXX Personal):"),
        "adm_set_binance_uid": ("binance_uid", "🟡 নতুন <b>Binance Pay ID / UID</b> লিখুন:"),
        "adm_set_support": ("support_user", "🟣 নতুন <b>Support Username</b> লিখুন (যেমন: @MySupport):"),
        "adm_set_notice": ("notice_text", "📢 নতুন <b>Notice / ঘোষণা</b> টেক্সট লিখুন:"),
    }

    if data in setting_prompts:
        s_key, prompt_msg = setting_prompts[data]
        user_states[uid] = {"step": "ADMIN_SET_VALUE", "setting_key": s_key}
        bot.send_message(call.message.chat.id, prompt_msg, reply_markup=cancel_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "adm_broadcast":
        user_states[uid] = {"step": "ADMIN_BROADCAST"}
        bot.send_message(
            call.message.chat.id,
            "📣 <b>সকল ইউজারের কাছে যে মেসেজটি পাঠাতে চান তা লিখুন:</b>",
            reply_markup=cancel_keyboard(),
        )
        bot.answer_callback_query(call.id)
        return

    if data == "adm_add_admin":
        user_states[uid] = {"step": "ADMIN_ADD_NEW"}
        bot.send_message(
            call.message.chat.id,
            "➕ <b>নতুন অ্যাডমিনের Telegram Numeric User ID লিখুন:</b>",
            reply_markup=cancel_keyboard(),
        )
        bot.answer_callback_query(call.id)
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
            bot.answer_callback_query(call.id, "✅ কোনো পেন্ডিং অর্ডার নেই!", show_alert=True)
            return

        bot.answer_callback_query(call.id)
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
            mk = InlineKeyboardMarkup(row_width=2)
            mk.add(
                InlineKeyboardButton("🟢 ✅ Approve", callback_data=f"adm_order_approve_{oid}"),
                InlineKeyboardButton("🔴 ❌ Reject", callback_data=f"adm_order_reject_{oid}"),
            )
            bot.send_message(call.message.chat.id, msg, reply_markup=mk)
        return

    # Approve or Reject Order
    if data.startswith("adm_order_approve_") or data.startswith("adm_order_reject_"):
        parts = data.split("_")
        action = parts[2]  # 'approve' or 'reject'
        order_id = int(parts[3])

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT user_id, order_type, usd_amount, bdt_amount, payment_method, status FROM orders WHERE order_id = ?",
            (order_id,),
        )
        row = c.fetchone()
        if not row:
            conn.close()
            bot.answer_callback_query(call.id, "⚠️ অর্ডারটি পাওয়া যায়নি!", show_alert=True)
            return

        o_uid, otype, usd, bdt, pm, current_st = row
        if current_st != "PENDING":
            conn.close()
            bot.answer_callback_query(call.id, f"⚠️ এই অর্ডারটি আগেই {current_st} করা হয়েছে!", show_alert=True)
            return

        new_status = "APPROVED" if action == "approve" else "REJECTED"
        c.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
        conn.commit()
        conn.close()

        # Adjust reserve automatically if BUY order is approved
        if new_status == "APPROVED" and otype == "BUY":
            try:
                cur_res = float(get_setting("usdt_reserve"))
                set_setting("usdt_reserve", f"{max(0.0, cur_res - float(usd)):.2f}")
            except Exception:
                pass
        elif new_status == "APPROVED" and otype == "SELL":
            try:
                cur_res = float(get_setting("usdt_reserve"))
                set_setting("usdt_reserve", f"{cur_res + float(usd):.2f}")
            except Exception:
                pass

        badge_text = "🟢 ✅ APPROVED (সম্পন্ন)" if new_status == "APPROVED" else "🔴 ❌ REJECTED (বাতিল)"
        bot.edit_message_text(
            call.message.html_text + f"\n\n━━━━━━━━━━━━━━\n📌 <b>Final Status:</b> {badge_text}",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.answer_callback_query(call.id, f"Order #{order_id} {new_status}!")

        # Notify Customer
        try:
            if new_status == "APPROVED":
                bot.send_message(
                    o_uid,
                    f"🟢 🎉 <b>অভিনন্দন! আপনার Order #{order_id} ({otype} {usd} USDT) সম্পন্ন হয়েছে!</b>\n"
                    f"💵 পরিমাণ: <code>{usd} USDT</code> ({bdt:.2f} BDT)\n"
                    "আমাদের সাথে লেনদেন করার জন্য ধন্যবাদ। ❤️",
                )
            else:
                bot.send_message(
                    o_uid,
                    f"🔴 ❌ <b>দুঃখিত! আপনার Order #{order_id} ({otype} {usd} USDT) বাতিল করা হয়েছে।</b>\n"
                    f"বিস্তারিত জানতে সাপোর্টে যোগাযোগ করুন: {get_setting('support_user')}",
                )
        except Exception:
            pass


# ====================================================================
# 💬 MULTI-STEP TEXT INPUT HANDLER (USER ORDERS & ADMIN INPUTS)
# ====================================================================
@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text_steps(message):
    uid = message.from_user.id
    text = message.text.strip()
    state = user_states.get(uid)

    if not state:
        bot.send_message(
            message.chat.id,
            "👇 নিচের রঙিন মেনু বাটন থেকে একটি অপশন সিলেক্ট করুন:",
            reply_markup=main_menu_keyboard(uid),
        )
        return

    step = state.get("step")

    # ----------------------------------------------------------------
    # ADMIN SETTING INPUTS
    # ----------------------------------------------------------------
    if step == "ADMIN_SET_VALUE" and is_admin(uid):
        s_key = state["setting_key"]
        if s_key in ("buy_rate", "sell_rate", "usdt_reserve", "min_usd"):
            try:
                val = float(text)
                if val <= 0 and s_key != "usdt_reserve":
                    raise ValueError()
                text = str(val)
            except ValueError:
                bot.reply_to(message, "🔴 ❌ অনুগ্রহ করে সঠিক সংখ্যা (Number) লিখুন!")
                return

        set_setting(s_key, text)
        user_states.pop(uid, None)
        bot.send_message(
            message.chat.id,
            f"🟢 ✅ <b>{s_key}</b> সফলভাবে আপডেট হয়ে <code>{text}</code> সেট করা হয়েছে!",
            reply_markup=main_menu_keyboard(uid),
        )
        bot.send_message(
            message.chat.id,
            get_admin_dashboard_text(),
            reply_markup=admin_panel_inline_markup(),
        )
        return

    if step == "ADMIN_ADD_NEW" and is_admin(uid):
        try:
            new_adm_id = int(text)
        except ValueError:
            bot.reply_to(message, "🔴 ❌ সঠিক Numeric Telegram ID দিন!")
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
        bot.send_message(
            message.chat.id,
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
                bot.send_message(target_id, f"📢 <b>অ্যাডমিন ঘোষণা:</b>\n\n{text}")
                sent_count += 1
            except Exception:
                pass

        bot.send_message(
            message.chat.id,
            f"🟢 ✅ মোট <b>{sent_count}</b> জন ইউজারের কাছে ব্রডকাস্ট মেসেজ পাঠানো হয়েছে!",
            reply_markup=main_menu_keyboard(uid),
        )
        return

    # ----------------------------------------------------------------
    # USER ORDER STEPS
    # ----------------------------------------------------------------
    if step == "ENTER_USD_AMOUNT":
        try:
            usd_amount = float(text)
        except ValueError:
            bot.reply_to(message, "🔴 ❌ অনুগ্রহ করে শুধুমাত্র সংখ্যায় ডলারের পরিমাণ লিখুন (যেমন: 10 বা 25.5):")
            return

        min_usd = float(get_setting("min_usd"))
        if usd_amount < min_usd:
            bot.reply_to(message, f"🔴 ⚠️ সর্বনিম্ন অর্ডার পরিমাণ <b>{min_usd} USDT</b>। অনুগ্রহ করে আবার লিখুন:")
            return

        if state["order_type"] == "BUY":
            reserve = float(get_setting("usdt_reserve"))
            if usd_amount > reserve:
                bot.reply_to(
                    message,
                    f"🔴 ⚠️ আমাদের বর্তমান রিজার্ভ <b>{reserve} USDT</b>। এর সমান বা কম পরিমাণ লিখুন:",
                )
                return

        rate = state["rate"]
        bdt_amount = round(usd_amount * rate, 2)
        state["usd_amount"] = usd_amount
        state["bdt_amount"] = bdt_amount
        state["step"] = "SELECT_PAYMENT"

        type_badge = "🟢 💵 BUY USDT" if state["order_type"] == "BUY" else "🔴 💰 SELL USDT"
        summary = (
            f"<b>{type_badge} — হিসাব বিবরণী</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>ডলারের পরিমাণ:</b> <code>{usd_amount} USDT</code>\n"
            f"📊 <b>রেট:</b> <code>{rate} BDT / $1</code>\n"
            f"💴 <b>মোট টাকার পরিমাণ:</b> <code>{bdt_amount:.2f} BDT</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>নিচের রঙিন বাটন থেকে আপনার পছন্দের পেমেন্ট মেথড সিলেক্ট করুন:</b>"
        )
        bot.send_message(
            message.chat.id,
            summary,
            reply_markup=active_payment_methods_markup("paymethod"),
        )
        return

    if step == "ENTER_RECEIVE_INFO":
        state["receive_info"] = text
        state["step"] = "ENTER_TRX_PROOF"
        pm = state["payment_method"]
        bdt_amount = state["bdt_amount"]
        usd_amount = state["usd_amount"]

        num_map = {
            "bKash": get_setting("bkash_number"),
            "Nagad": get_setting("nagad_number"),
            "Rocket": get_setting("rocket_number"),
        }
        admin_pay_no = num_map.get(pm, "")

        if state["order_type"] == "BUY":
            pay_instructions = (
                "🟢 💳 <b>পেমেন্ট করার নিয়মাবলী (Buy USDT):</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📲 <b>আমাদের {pm} নাম্বার:</b>\n"
                f"👉 <code>{admin_pay_no}</code>\n\n"
                f"💴 <b>পাঠানোর পরিমাণ:</b> <code>{bdt_amount:.2f} BDT</code>\n"
                f"📥 <b>আপনার Binance UID:</b> <code>{text}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "✍️ উপরের নাম্বারে টাকা পাঠিয়ে আপনার <b>Transaction ID (TrxID) এবং যে নাম্বার থেকে টাকা পাঠিয়েছেন তার শেষ ৪ ডিজিট</b> লিখে পাঠান:"
            )
        else:
            binance_uid = get_setting("binance_uid")
            pay_instructions = (
                "🔴 💎 <b>ডলার পাঠানোর নিয়মাবলী (Sell USDT):</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🟡 <b>আমাদের Binance Pay ID / UID:</b>\n"
                f"👉 <code>{binance_uid}</code>\n\n"
                f"💵 <b>পাঠানোর পরিমাণ:</b> <code>{usd_amount} USDT</code>\n"
                f"📲 <b>টাকা পাবেন ({pm}):</b> <code>{text}</code> ({bdt_amount:.2f} BDT)\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "✍️ উপরের Binance UID-তে ডলার (USDT) পাঠিয়ে আপনার <b>Binance Order ID / আপনার Binance নেম বা UID</b> লিখে পাঠান:"
            )

        bot.send_message(message.chat.id, pay_instructions, reply_markup=cancel_keyboard())
        return

    if step == "ENTER_TRX_PROOF":
        state["trx_proof"] = text
        uname = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO orders (user_id, username, order_type, usd_amount, bdt_amount, rate, payment_method, receive_info, trx_proof, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                uid,
                uname,
                state["order_type"],
                state["usd_amount"],
                state["bdt_amount"],
                state["rate"],
                state["payment_method"],
                state["receive_info"],
                state["trx_proof"],
                created_at,
            ),
        )
        order_id = c.lastrowid
        conn.commit()
        conn.close()

        order_data = dict(state)
        user_states.pop(uid, None)

        # Confirm to User
        bot.send_message(
            message.chat.id,
            f"🟢 ✅ <b>আপনার অর্ডারটি সফলভাবে জমা হয়েছে!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>Order ID:</b> <code>#{order_id}</code>\n"
            f"📌 <b>ধরণ:</b> {order_data['order_type']} USDT\n"
            f"💵 <b>ডলার:</b> <code>{order_data['usd_amount']} USDT</code>\n"
            f"💴 <b>টাকা:</b> <code>{order_data['bdt_amount']:.2f} BDT</code>\n"
            f"📲 <b>মেথড:</b> {order_data['payment_method']}\n"
            f"🧾 <b>প্রুফ/TrxID:</b> <code>{order_data['trx_proof']}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ অ্যাডমিন আপনার লেনদেন যাচাই করে ৫-১০ মিনিটের মধ্যে অর্ডার সম্পন্ন করবেন।",
            reply_markup=main_menu_keyboard(uid),
        )

        # Instant Notification to All Admins with Approve/Reject Buttons
        badge = "🟢 💵 NEW BUY ORDER" if order_data["order_type"] == "BUY" else "🔴 💰 NEW SELL ORDER"
        admin_alert = (
            f"🔔 <b>{badge} — #{order_id}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {uname} (<code>{uid}</code>)\n"
            f"💵 <b>Amount:</b> <code>{order_data['usd_amount']} USDT</code>\n"
            f"💴 <b>Total BDT:</b> <code>{order_data['bdt_amount']:.2f} BDT</code> (Rate: {order_data['rate']})\n"
            f"📲 <b>Method:</b> {order_data['payment_method']}\n"
            f"📥 <b>Receive Info:</b> <code>{order_data['receive_info']}</code>\n"
            f"🧾 <b>TrxID / Proof:</b> <code>{order_data['trx_proof']}</code>\n"
            f"🕒 <b>Time:</b> {created_at}"
        )
        adm_mk = InlineKeyboardMarkup(row_width=2)
        adm_mk.add(
            InlineKeyboardButton("🟢 ✅ Approve Order", callback_data=f"adm_order_approve_{order_id}"),
            InlineKeyboardButton("🔴 ❌ Reject Order", callback_data=f"adm_order_reject_{order_id}"),
        )
        for adm_id in get_all_admin_ids():
            try:
                bot.send_message(adm_id, admin_alert, reply_markup=adm_mk)
            except Exception:
                pass
        return


# ====================================================================
# ▶️ MAIN ENTRYPOINT
# ====================================================================
if __name__ == "__main__":
    init_db()
    print("====================================================")
    print("💎 Binance Dollar Buy-Sell Bot is Running...")
    print("⚙️ Use /admin inside Telegram to configure everything!")
    print("====================================================")
    bot.infinity_polling(skip_pending=True)