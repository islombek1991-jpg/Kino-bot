import os
import sqlite3
import asyncio
from typing import List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# =======================
# ENV
# =======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "data.db").strip()
IG_URL = os.getenv("IG_URL", "").strip()  # Instagram profil (tekshirilmaydi)

# Adminlar (ixtiyoriy)
ADMIN_IDS: List[int] = []
_raw_admins = os.getenv("ADMIN_IDS", "").strip()
if _raw_admins:
    for x in _raw_admins.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.append(int(x))

# Majburiy obuna (Telegram kanallar)
FORCE_CHANNELS: List[str] = []
_raw_channels = os.getenv("FORCE_CHANNELS", "").strip()
if _raw_channels:
    for ch in _raw_channels.split(","):
        ch = ch.strip()
        if ch and not ch.startswith("@"):
            ch = "@" + ch
        if ch:
            FORCE_CHANNELS.append(ch)

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi (Railway Variables ga qo'ying)")

MAIN_CHANNEL_URL = f"https://t.me/{FORCE_CHANNELS[0].lstrip('@')}" if FORCE_CHANNELS else None

# =======================
# DB
# =======================
def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def db_init():
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url   TEXT NOT NULL,
                views INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.commit()

        # eski bazada views bo'lmasa qo'shib yuboradi
        try:
            cur.execute("PRAGMA table_info(movies)")
            cols = [r[1] for r in cur.fetchall()]
            if "views" not in cols:
                cur.execute("ALTER TABLE movies ADD COLUMN views INTEGER NOT NULL DEFAULT 0")
                con.commit()
        except Exception:
            pass

def db_add_movie(code: str, title: str, url: str):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT views FROM movies WHERE code=?", (code,))
        row = cur.fetchone()
        old_views = int(row[0]) if row and row[0] is not None else 0

        cur.execute(
            "INSERT OR REPLACE INTO movies(code,title,url,views) VALUES(?,?,?,?)",
            (code, title, url, old_views),
        )
        con.commit()

def db_get_movie(code: str) -> Optional[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT title, url, views FROM movies WHERE code=?", (code,))
        row = cur.fetchone()
        if not row:
            return None
        title, url, views = row
        return str(title), str(url), int(views or 0)

def db_list_movies(limit: int = 50) -> List[Tuple[str, str]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT code, title FROM movies ORDER BY code LIMIT ?", (limit,))
        return [(str(c), str(t)) for c, t in cur.fetchall()]

def db_inc_view(code: str):
    with db_conn() as con:
        con.execute("UPDATE movies SET views = views + 1 WHERE code=?", (code,))
        con.commit()

def db_top_views(limit: int = 10) -> List[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT code, title, views FROM movies ORDER BY views DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        out = []
        for c, t, v in rows:
            out.append((str(c), str(t), int(v or 0)))
        return out

# =======================
# Helpers
# =======================
def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS

def _make_sub_keyboard(missing_channels: List[str], pending_code: str = "") -> InlineKeyboardMarkup:
    buttons = []

    # Telegram kanallar
    for ch in missing_channels:
        buttons.append([InlineKeyboardButton(f"📢 Obuna bo‘lish: {ch}", url=f"https://t.me/{ch.lstrip('@')}")])

    # Instagram (tekshirilmaydi, faqat tugma)
    if IG_URL:
        buttons.append([InlineKeyboardButton("📸 Instagramga follow", url=IG_URL)])

    # Tekshirish
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data=f"recheck:{pending_code}")])

    return InlineKeyboardMarkup(buttons)

async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE, pending_code: str = "") -> bool:
    if not FORCE_CHANNELS:
        return True

    user = update.effective_user
    if not user:
        return False

    not_joined = []
    for ch in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(ch, user.id)
            if member.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)

    if not not_joined:
        return True

    text = (
        "🔒 Davom etish uchun kanal(lar)ga obuna bo‘ling.\n\n"
        "Obuna bo‘lgach ✅ <b>Tekshirish</b> ni bosing."
    )

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=_make_sub_keyboard(not_joined, pending_code),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=_make_sub_keyboard(not_joined, pending_code),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception:
            pass

    return False

async def send_movie_locked(chat, code: str, title: str, views: int):
    text = (
        f"🎬 <b>{title}</b>\n"
        f"🆔 Kod: <code>{code}</code>\n\n"
        f"⭐ Ko‘rilgan: <b>{views}</b>\n\n"
        "⏳ Kinoni olish uchun <b>“🎬 KINONI KO‘RISH”</b> ni bosing"
    )

    buttons = [
        [InlineKeyboardButton("🎬 KINONI KO‘RISH", callback_data=f"watch:{code}")],
    ]
    if MAIN_CHANNEL_URL:
        buttons.append([InlineKeyboardButton("📢 KANALGA O‘TISH", url=MAIN_CHANNEL_URL)])
    if IG_URL:
        buttons.append([InlineKeyboardButton("📸 Instagram", url=IG_URL)])

    await chat.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def send_movie_unlocked(chat, code: str, title: str, url: str, views: int):
    text = (
        "✅ Tayyor!\n\n"
        f"🎬 <b>{title}</b>\n"
        f"🆔 Kod: <code>{code}</code>\n"
        f"⭐ Ko‘rilgan: <b>{views}</b>\n\n"
        "👇 Endi kinoni ochish uchun tugmani bosing"
    )

    buttons = [
        [InlineKeyboardButton("▶️ KINONI OCHISH", url=url)],
    ]
    if MAIN_CHANNEL_URL:
        buttons.append([InlineKeyboardButton("📢 KANALGA O‘TISH", url=MAIN_CHANNEL_URL)])
    if IG_URL:
        buttons.append([InlineKeyboardButton("📸 Instagram", url=IG_URL)])

    await chat.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# =======================
# Handlers
# =======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return
    await update.message.reply_text(
        "🎬 Kino botga xush kelibsiz!\n\n"
        "Kino kodini yuboring (masalan: 01)\n"
        "Yordam: /help"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Buyruqlar:\n"
        "/start — boshlash\n"
        "/help — yordam\n"
        "/list — 50 ta kino ro‘yxati\n"
        "/top — TOP-10 eng ko‘p ko‘rilgan\n\n"
        "🛠 Admin uchun:\n"
        "/add <kod> | <nom> | <link>\n"
        "Misol: /add 01 | Troll | https://t.me/kanal/4"
    )

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return
    rows = db_list_movies(50)
    if not rows:
        await update.message.reply_text("Hozircha kino yo‘q. Admin /add bilan qo‘shadi.")
        return
    text = "📃 Kino ro‘yxati:\n" + "\n".join([f"{c} — {t}" for c, t in rows])
    await update.message.reply_text(text)

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return
    rows = db_top_views(10)
    if not rows:
        await update.message.reply_text("Hali kino yo‘q.")
        return
    text = "🔥 <b>TOP-10 Eng ko‘p ko‘rilgan</b>\n\n"
    for code, title, views in rows:
        text += f"⭐ <b>{views}</b> — <code>{code}</code> | {title}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if not is_admin(msg.from_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return

    raw = msg.text or ""
    raw = raw.replace("/add", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3:
        await msg.reply_text(
            "❌ Noto‘g‘ri format.\n"
            "To‘g‘risi: /add <kod> | <nom> | <link>"
        )
        return

    code, title, url = parts
    if not code:
        await msg.reply_text("❌ Kod bo‘sh bo‘lmasin.")
        return
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("t.me/")):
        await msg.reply_text("❌ Link noto‘g‘ri.")
        return

    db_add_movie(code, title, url)
    await msg.reply_text(f"✅ Kino qo‘shildi: {code}")

async def code_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    text = (msg.text or "").strip()
    if text.startswith("/"):
        return

    row = db_get_movie(text)
    if not row:
        await msg.reply_text("❌ Bunday kod topilmadi.")
        return

    ok = await check_force_sub(update, context, pending_code=text)
    if not ok:
        return

    title, url, views = row

    wait_msg = await msg.reply_text("⏳ 5 soniya… tekshirilyapti…")
    await asyncio.sleep(5)
    try:
        await wait_msg.delete()
    except Exception:
        pass

    await send_movie_locked(msg, text, title, views)

async def recheck_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    pending_code = ""
    if ":" in (q.data or ""):
        pending_code = (q.data or "").split(":", 1)[1].strip()

    ok = await check_force_sub(update, context, pending_code=pending_code)
    if not ok:
        return

    try:
        await q.edit_message_text("✅ Obuna tasdiqlandi! Endi kino kodini yuboring.")
    except Exception:
        pass

    if pending_code:
        row = db_get_movie(pending_code)
        if not row:
            await q.message.reply_text("❌ Bu kod topilmadi.")
            return
        title, url, views = row
        await q.message.reply_text("⏳ 5 soniya… tekshirilyapti…")
        await asyncio.sleep(5)
        await send_movie_locked(q.message, pending_code, title, views)

async def watch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    code = ""
    data = q.data or ""
    if ":" in data:
        code = data.split(":", 1)[1].strip()
    if not code:
        return

    ok = await check_force_sub(update, context, pending_code=code)
    if not ok:
        return

    row = db_get_movie(code)
    if not row:
        await q.message.reply_text("❌ Bu kod topilmadi.")
        return

    title, url, views = row

    db_inc_view(code)  # views faqat shu yerda oshadi
    title, url, views = db_get_movie(code)

    await q.message.reply_text("✅ Tayyor! ⏳ 2 soniya…")
    await asyncio.sleep(2)
    await send_movie_unlocked(q.message, code, title, url, views)

# =======================
# Main
# =======================
def main():
    db_init()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("add", add_cmd))

    app.add_handler(CallbackQueryHandler(recheck_callback, pattern=r"^recheck:"))
    app.add_handler(CallbackQueryHandler(watch_callback, pattern=r"^watch:"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, code_message))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
