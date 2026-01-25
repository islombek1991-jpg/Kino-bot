import os
import sqlite3
from typing import List, Tuple

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =======================
# ENV
# =======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN yo‘q. Railway Variables ga BOT_TOKEN qo‘ying.")

DB_PATH = os.getenv("DB_PATH", "data.db").strip()

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = []
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.append(int(x))

FORCE_CHANNELS_RAW = os.getenv("FORCE_CHANNELS", "").strip()
FORCE_CHANNELS = []
if FORCE_CHANNELS_RAW:
    for ch in FORCE_CHANNELS_RAW.split(","):
        ch = ch.strip()
        if ch:
            FORCE_CHANNELS.append(ch)

EXTRA_LINKS = os.getenv("EXTRA_LINKS", "").strip()  # Instagram/website uchun (tekshirmaydi)

# =======================
# DB (SQLite)
# =======================
def db_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) if "/" in DB_PATH else None
    return sqlite3.connect(DB_PATH)

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

def db_add_movie(code: str, title: str, url: str):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO movies(code,title,url,views) VALUES(?,?,?,COALESCE((SELECT views FROM movies WHERE code=?),0))",
            (code, title, url, code),
        )
        con.commit()

def db_get_movie(code: str):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT title, url, views FROM movies WHERE code=?", (code,))
        return cur.fetchone()

def db_inc_views(code: str):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("UPDATE movies SET views = views + 1 WHERE code=?", (code,))
        con.commit()

def db_list_movies(limit: int = 50) -> List[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT code, title, views FROM movies ORDER BY code LIMIT ?", (limit,))
        return cur.fetchall()

def db_top_movies(limit: int = 10) -> List[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT code, title, views FROM movies ORDER BY views DESC, code ASC LIMIT ?", (limit,))
        return cur.fetchall()

# =======================
# Helpers
# =======================
def is_admin(user_id: int) -> bool:
    # ADMIN_IDS bo‘sh bo‘lsa hamma admin bo‘lib ketmasin — xavfsiz qilib qo‘ydim
    if not ADMIN_IDS:
        return False
    return user_id in ADMIN_IDS

async def force_sub_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Majburiy obuna: kanal(lar) tekshiradi. True bo‘lsa davom etadi."""
    if not FORCE_CHANNELS:
        return True

    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return False

    not_joined = []
    for ch in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(ch, user.id)
            if member.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception:
            # Bot kanalda admin bo‘lmasa yoki kanal topilmasa — foydalanuvchini o‘tkazmaymiz
            not_joined.append(ch)

    if not_joined:
        text = "🔒 <b>Botdan foydalanish uchun avval obuna bo‘ling:</b>\n\n"
        text += "\n".join([f"👉 {c}" for c in not_joined])
        if EXTRA_LINKS:
            text += f"\n\n🔗 <b>Qo‘shimcha:</b> {EXTRA_LINKS}"
        text += "\n\n✅ Obuna bo‘lgach <b>/start</b> bosing."
        await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        return False

    return True

# =======================
# Handlers
# =======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_sub_gate(update, context):
        return
    msg = update.effective_message
    await msg.reply_text(
        "🎬 <b>Kino botga xush kelibsiz!</b>\n\n"
        "🔎 Kino kodini yuboring (masalan: <b>01</b> yoki <b>101</b>)\n"
        "📃 Ro‘yxat: /list\n"
        "🔥 Top: /top\n"
        "🆘 Yordam: /help",
        parse_mode=ParseMode.HTML
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = (
        "📌 <b>Buyruqlar:</b>\n"
        "/start — boshlash\n"
        "/help — yordam\n"
        "/list — 50 ta kino ro‘yxati\n"
        "/top — eng ko‘p ko‘rilganlar\n\n"
        "🛠 <b>Admin:</b>\n"
        "/add <kod> | <nom> | <link>\n"
        "Misol:\n"
        "<code>/add 01 | Troll | https://t.me/IsboySkinolar_olami/4</code>\n\n"
        "💡 Link Telegram post bo‘lsa ham bo‘ladi."
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_sub_gate(update, context):
        return
    msg = update.effective_message
    rows = db_list_movies(50)
    if not rows:
        await msg.reply_text("Hozircha kino yo‘q. Admin /add bilan qo‘shadi.")
        return
    text = "📃 <b>Kino ro‘yxati:</b>\n\n" + "\n".join([f"{c} — {t}  ({v}👀)" for c, t, v in rows])
    await msg.reply_text(text, parse_mode=ParseMode.HTML)

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_sub_gate(update, context):
        return
    msg = update.effective_message
    rows = db_top_movies(10)
    if not rows:
        await msg.reply_text("Hozircha top kino yo‘q.")
        return
    text = "🔥 <b>Eng ko‘p ko‘rilgan kinolar:</b>\n\n" + "\n".join([f"{i+1}) {c} — {t}  ({v}👀)" for i, (c, t, v) in enumerate(rows)])
    await msg.reply_text(text, parse_mode=ParseMode.HTML)

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not update.effective_user:
        return

    if not is_admin(update.effective_user.id):
        await msg.reply_text("⛔ Admin emassiz.")
        return

    raw = (msg.text or "").replace("/add", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3:
        await msg.reply_text(
            "❌ Format xato.\n\n"
            "To‘g‘risi:\n"
            "<code>/add 01 | Troll | https://t.me/IsboySkinolar_olami/4</code>",
            parse_mode=ParseMode.HTML
        )
        return

    code, title, url = parts
    if not code:
        await msg.reply_text("❌ Kod bo‘sh bo‘lmasin.")
        return
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("t.me/")):
        await msg.reply_text("❌ Link noto‘g‘ri. https://... bo‘lsin.")
        return

    db_add_movie(code, title, url)
    await msg.reply_text(f"✅ Qo‘shildi: <b>{code}</b> — {title}", parse_mode=ParseMode.HTML)

async def code_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    if not await force_sub_gate(update, context):
        return

    code = (msg.text or "").strip()
    if not code or code.startswith("/"):
        return

    row = db_get_movie(code)
    if not row:
        await msg.reply_text("❌ Bunday kod topilmadi.\n📃 /list yoki 🔥 /top")
        return

    title, url, views = row
    db_inc_views(code)

    text = (
        f"🎬 <b>{title}</b>\n"
        f"🔗 {url}\n\n"
        f"👀 Ko‘rildi: <b>{views + 1}</b>"
    )
    if EXTRA_LINKS:
        text += f"\n\n🔗 <b>Qo‘shimcha:</b> {EXTRA_LINKS}"

    await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=False)

def main():
    db_init()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("add", add_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, code_message))

    # Railway uchun polling normal ishlaydi
    app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()
