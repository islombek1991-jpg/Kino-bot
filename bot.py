import os
import re
import sqlite3
import random
from typing import List, Tuple, Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -------------------------
# ENV
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

DB_PATH = os.getenv("DB_PATH", "movies.db")

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
            link TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'movie',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )
        """
    )
    return conn

def db_add(code: str, title: str, link: str, kind: str = "movie") -> None:
    conn = db_conn()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO movies(code, title, link, kind) VALUES (?, ?, ?, ?)",
            (code, title, link, kind),
        )
    conn.close()

def db_get(code: str) -> Optional[Tuple[str, str, str, str]]:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT code, title, link, kind FROM movies WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()
    return row

def db_latest(kind: str = "movie", limit: int = 10) -> List[Tuple[str, str]]:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT code, title FROM movies WHERE kind=? ORDER BY created_at DESC LIMIT ?",
        (kind, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def db_random(kind: str = "movie") -> Optional[Tuple[str, str]]:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT code, title FROM movies WHERE kind=? ORDER BY RANDOM() LIMIT 1", (kind,))
    row = cur.fetchone()
    conn.close()
    return row

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# -------------------------
# COMMANDS
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "✅ *Bot ishlayapti!*\n\n"
        "🎬 Kino olish:\n"
        "• Menyudan *Kino qidirish (/kino)* ni bosing yoki `101` kabi kod yuboring.\n"
        "• Yoki: `/get 101`\n\n"
        "🎲 Tasodifiy: `/random`\n"
        "🔥 Yangi qo‘shilganlar: `/top`\n\n"
        "👑 Admin:\n"
        "`/add 101 | Avatar (2009) | https://t.me/IsboySkinolar_olami/12`\n"
        "`/addserial 201 | Serial nomi | https://t.me/IsboySkinolar_olami/55`\n"
        "`/setmenu` (menyuni o‘rnatadi)\n"
        "`/whoami` (admin test)\n"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        return
    await update.message.reply_text(
        f"ID: `{u.id}`\nAdmin: `{is_admin(u.id)}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def kino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Kod yuboring. Masalan: 101")

async def serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # hozircha serial list ko'rsatamiz (agar bo'lsa)
    rows = db_latest(kind="serial", limit=10)
    if not rows:
        await update.message.reply_text("📺 Hozircha seriallar qo‘shilmagan.")
        return
    out = ["📺 *Seriallar (oxirgi 10 ta):*"]
    for code, title in rows:
        out.append(f"{code} — {title}")
    out.append("\nSerial olish: `/get KOD` (masalan: `/get 201`)")
    await update.message.reply_text("\n".join(out), parse_mode=ParseMode.MARKDOWN)

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db_latest(kind="movie", limit=10)
    if not rows:
        await update.message.reply_text("Hozircha kino yo‘q. Admin /add bilan qo‘shadi.")
        return
    out = ["🔥 *Yangi qo‘shilgan kinolar (10 ta):*"]
    for code, title in rows:
        out.append(f"{code} — {title}")
    await update.message.reply_text("\n".join(out), parse_mode=ParseMode.MARKDOWN)

async def random_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r = db_random(kind="movie")
    if not r:
        await update.message.reply_text("Hozircha kino yo‘q.")
        return
    code, title = r
    await update.message.reply_text(f"🎲 Tasodifiy kino: *{code} — {title}*\n`/get {code}`", parse_mode=ParseMode.MARKDOWN)

async def get_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await update.message.reply_text("❌ Kod yozing. Misol: /get 101")
        return

    code = parts[1].strip()
    row = db_get(code)
    if not row:
        await update.message.reply_text("❌ Bunday kod topilmadi.")
        return

    code, title, link, kind = row
    icon = "🎬" if kind == "movie" else "📺"
    await update.message.reply_text(f"{icon} *{code} — {title}*\n🔗 {link}", parse_mode=ParseMode.MARKDOWN)

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or not is_admin(u.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    text = (update.message.text or "").strip()
    payload = text[4:].strip()  # after /add
    parts = [p.strip() for p in payload.split("|")]
    if len(parts) != 3:
        await update.message.reply_text("❗ Format xato.\nMisol:\n/add 101 | Avatar (2009) | https://t.me/IsboySkinolar_olami/12")
        return

    code, title, link = parts
    if not code.isdigit():
        await update.message.reply_text("❗ Kod faqat raqam bo‘lsin. Masalan: 101")
        return
    if not (link.startswith("http://") or link.startswith("https://")):
        await update.message.reply_text("❗ Link http/https bilan boshlansin.")
        return

    db_add(code, title, link, kind="movie")
    await update.message.reply_text(f"✅ Kino saqlandi: {code} — {title}")

async def addserial_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or not is_admin(u.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    text = (update.message.text or "").strip()
    payload = text[len("/addserial"):].strip()
    parts = [p.strip() for p in payload.split("|")]
    if len(parts) != 3:
        await update.message.reply_text("❗ Format xato.\nMisol:\n/addserial 201 | Serial nomi | https://t.me/IsboySkinolar_olami/55")
        return

    code, title, link = parts
    if not code.isdigit():
        await update.message.reply_text("❗ Kod faqat raqam bo‘lsin. Masalan: 201")
        return
    if not (link.startswith("http://") or link.startswith("https://")):
        await update.message.reply_text("❗ Link http/https bilan boshlansin.")
        return

    db_add(code, title, link, kind="serial")
    await update.message.reply_text(f"✅ Serial saqlandi: {code} — {title}")

async def setmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or not is_admin(u.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    cmds = [
        ("start", "Botni ishga tushirish"),
        ("kino", "Kino qidirish"),
        ("serial", "Seriallar bo‘limi"),
        ("top", "Eng mashhur/yangi kinolar"),
        ("random", "Tasodifiy kino"),
        ("get", "Kod bo‘yicha olish: /get 101"),
        ("add", "Admin: kino qo‘shish"),
        ("addserial", "Admin: serial qo‘shish"),
        ("whoami", "Admin test"),
    ]
    await context.bot.set_my_commands(cmds)
    await update.message.reply_text("✅ Menu komandalar o‘rnatildi. Endi Telegram menuda ishlaydi.")

async def handle_plain_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text.isdigit():
        await update.message.reply_text("❓ Kod yuboring. Masalan: 101 yoki /get 101")
        return
    # same as /get
    row = db_get(text)
    if not row:
        await update.message.reply_text("❌ Bunday kod topilmadi.")
        return
    code, title, link, kind = row
    icon = "🎬" if kind == "movie" else "📺"
    await update.message.reply_text(f"{icon} *{code} — {title}*\n🔗 {link}", parse_mode=ParseMode.MARKDOWN)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("whoami", whoami))

    app.add_handler(CommandHandler("kino", kino))
    app.add_handler(CommandHandler("serial", serial))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("random", random_cmd))
    app.add_handler(CommandHandler("get", get_cmd))

    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("addserial", addserial_cmd))
    app.add_handler(CommandHandler("setmenu", setmenu))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plain_code))

    app.run_polling()

if __name__ == "__main__":
    main()
