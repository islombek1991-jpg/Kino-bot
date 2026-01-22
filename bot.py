import os
import re
import sqlite3
from typing import List, Tuple, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# -------------------------
# ENV SETTINGS
# -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi")

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
if not ADMIN_IDS_RAW:
    raise ValueError("ADMIN_IDS topilmadi (masalan: 5491302235)")

ADMIN_IDS = set()
for x in re.split(r"[,\s]+", ADMIN_IDS_RAW):
    x = x.strip()
    if x.isdigit():
        ADMIN_IDS.add(int(x))

CHANNELS_RAW = os.getenv("FORCE_CHANNELS", "@IsboySkinolar_olami").strip()
FORCE_CHANNELS = [c.strip() for c in re.split(r"[,\s]+", CHANNELS_RAW) if c.strip()]
# kanal username bo'lsa @ bilan bo'lsin
FORCE_CHANNELS = [c if c.startswith("@") else f"@{c}" for c in FORCE_CHANNELS]

DB_PATH = os.getenv("DB_PATH", "movies.db")  # xohlasang Railway Volume uchun /data/movies.db qilasan

# -------------------------
# DB
# -------------------------
def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            link TEXT NOT NULL
        )
        """
    )
    return conn

def db_add_movie(code: str, title: str, link: str) -> None:
    conn = db_conn()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO movies(code, title, link) VALUES (?, ?, ?)",
            (code, title, link),
        )
    conn.close()

def db_get_movie(code: str) -> Optional[Tuple[str, str, str]]:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT code, title, link FROM movies WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()
    return row

def db_list_movies(limit: int = 50) -> List[Tuple[str, str]]:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT code, title FROM movies ORDER BY CAST(code AS INTEGER) ASC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

# -------------------------
# SUBSCRIPTION CHECK
# -------------------------
async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Foydalanuvchi FORCE_CHANNELS dagi hamma kanallarga a'zo bo'lganmi?
    Bot kanalda admin bo'lishi kerak.
    """
    for ch in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=ch, user_id=user_id)
            status = getattr(member, "status", "")
            # creator/administrator/member bo'lsa ok, left/kicked bo'lsa yo'q
            if status in ("left", "kicked"):
                return False
        except Exception:
            # kanalni topolmasa yoki huquq yetmasa ham false qilamiz
            return False
    return True

def join_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for ch in FORCE_CHANNELS:
        url = f"https://t.me/{ch.lstrip('@')}"
        buttons.append([InlineKeyboardButton(f"➕ Obuna bo‘lish: {ch}", url=url)])
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(buttons)

async def must_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return True
    ok = await is_subscribed(user.id, context)
    if ok:
        return False

    text = (
        "🔒 Botdan foydalanish uchun kanalga obuna bo‘ling:\n\n"
        + "\n".join([f"• {c}" for c in FORCE_CHANNELS])
        + "\n\nObuna bo‘lgach ✅ *Tekshirish* ni bosing."
    )

    if update.message:
        await update.message.reply_text(text, reply_markup=join_keyboard(), parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=join_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return True

# -------------------------
# HANDLERS
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await must_subscribe(update, context):
        return

    msg = (
        "✅ *Bot ishlayapti.*\n\n"
        "🎬 Kino kodini yuboring. Masalan: `101`\n\n"
        "👑 Admin buyruqlar:\n"
        "`/add 101 | Avatar (2009) | https://t.me/IsboySkinolar_olami/12`\n"
        "`/list`"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cb_check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ok = await is_subscribed(q.from_user.id, context)
    if ok:
        await q.message.reply_text("✅ Obuna tasdiqlandi. Endi kod yuboring. Masalan: 101")
    else:
        await q.message.reply_text("❌ Hali obuna bo‘lmagansiz. Avval obuna bo‘ling, keyin tekshiring.")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    if await must_subscribe(update, context):
        return

    text = update.message.text.strip()
    # /add 101 | Title | link
    payload = text[4:].strip()  # after /add
    parts = [p.strip() for p in payload.split("|")]
    if len(parts) != 3:
        await update.message.reply_text("❗ Format xato.\nMisol:\n/add 101 | Avatar (2009) | https://t.me/IsboySkinolar_olami/12")
        return

    code, title, link = parts
    code = code.strip()
    if not code.isdigit():
        await update.message.reply_text("❗ Kod faqat raqam bo‘lsin. Masalan: 101")
        return
    if not (link.startswith("http://") or link.startswith("https://")):
        await update.message.reply_text("❗ Link http/https bilan boshlansin.")
        return

    db_add_movie(code, title, link)
    await update.message.reply_text(f"✅ Saqlandi: {code} — {title}\n🔗 {link}")

async def list_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    rows = db_list_movies(50)
    if not rows:
        await update.message.reply_text("Hozircha kino yo‘q. /add bilan qo‘shing.")
        return

    out = ["📃 *Kino ro‘yxati (50 tagacha):*"]
    for code, title in rows:
        out.append(f"{code} — {title}")
    await update.message.reply_text("\n".join(out), parse_mode=ParseMode.MARKDOWN)

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await must_subscribe(update, context):
        return

    text = (update.message.text or "").strip()
    if not text.isdigit():
        await update.message.reply_text("❓ Kod yuboring. Masalan: 101")
        return

    row = db_get_movie(text)
    if not row:
        await update.message.reply_text("❌ Bunday kod topilmadi.")
        return

    code, title, link = row
    await update.message.reply_text(f"🎬 *{code} — {title}*\n🔗 {link}", parse_mode=ParseMode.MARKDOWN)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(cb_check_sub, pattern="^check_sub$"))
    app.add_handler(CommandHandler("add", add_movie))
    app.add_handler(CommandHandler("list", list_movies))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))

    app.run_polling()

if __name__ == "__main__":
    main()
