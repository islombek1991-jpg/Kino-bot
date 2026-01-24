import os
import re
import sqlite3
from typing import List, Tuple

from telegram import Update
from telegram.ext import (
Application,
CommandHandler,
ContextTypes,
MessageHandler,
filters,
)

=======================

ENV (faqat BOT_TOKEN shart)

=======================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "data.db").strip()

Adminlar (ixtiyoriy): "5491302235,123456789"

ADMIN_IDS = []
_raw_admins = os.getenv("ADMIN_IDS", "").strip()
if _raw_admins:
for x in _raw_admins.split(","):
x = x.strip()
if x.isdigit():
ADMIN_IDS.append(int(x))

Majburiy obuna (ixtiyoriy): "@kanal1,@kanal2"

FORCE_CHANNELS = []
_raw_channels = os.getenv("FORCE_CHANNELS", "").strip()
if _raw_channels:
for ch in _raw_channels.split(","):
ch = ch.strip()
if ch:
FORCE_CHANNELS.append(ch)

if not BOT_TOKEN:
raise ValueError("BOT_TOKEN topilmadi (Railway Variables ga qo'ying)")

=======================

DB

=======================

def db_conn():
return sqlite3.connect(DB_PATH)

def db_init():
with db_conn() as con:
cur = con.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS movies (
code TEXT PRIMARY KEY,
title TEXT NOT NULL,
url   TEXT NOT NULL
)
""")
con.commit()

def db_add_movie(code: str, title: str, url: str):
with db_conn() as con:
cur = con.cursor()
cur.execute(
"INSERT OR REPLACE INTO movies(code,title,url) VALUES(?,?,?)",
(code, title, url),
)
con.commit()

def db_get_movie(code: str):
with db_conn() as con:
cur = con.cursor()
cur.execute("SELECT title, url FROM movies WHERE code=?", (code,))
row = cur.fetchone()
return row  # (title, url) or None

def db_list_movies(limit: int = 50) -> List[Tuple[str, str]]:
with db_conn() as con:
cur = con.cursor()
cur.execute("SELECT code, title FROM movies ORDER BY code LIMIT ?", (limit,))
return cur.fetchall()

=======================

Helpers

=======================

def is_admin(user_id: int) -> bool:
# Agar ADMIN_IDS bo'sh bo'lsa — hamma /add qila oladi (xohlasang xavfsizroq qilish uchun pastdagi qatorni o'zgartiramiz)
if not ADMIN_IDS:
return True
return user_id in ADMIN_IDS

async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
"""True -> ruxsat, False -> blok."""
if not FORCE_CHANNELS:
return True

user = update.effective_user  
if not user:  
    return False  

not_joined = []  
for ch in FORCE_CHANNELS:  
    try:  
        member = await context.bot.get_chat_member(ch, user.id)  
        # member.status: 'left', 'kicked', 'member', 'administrator', 'creator'  
        if member.status in ("left", "kicked"):  
            not_joined.append(ch)  
    except Exception:  
        # kanal topilmasa yoki bot admin bo'lmasa — majburiy obuna ishlamaydi  
        not_joined.append(ch)  

if not_joined:  
    txt = "🔒 Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo‘ling:\n\n"  
    txt += "\n".join([f"👉 {c}" for c in not_joined])  
    txt += "\n\n✅ Obuna bo‘lgach /start bosing."  
    await update.message.reply_text(txt, disable_web_page_preview=True)  
    return False  

return True

=======================

Handlers

=======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
if update.message and not await check_force_sub(update, context):
return
await update.message.reply_text(
"🎬 Kino botga xush kelibsiz!\n\n"
"Kino kodini yuboring (masalan: 101)\n"
"Yordam: /help"
)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
"📌 Buyruqlar:\n"
"/start — boshlash\n"
"/help — yordam\n"
"/list — 50 ta kino ro‘yxati\n\n"
"🛠 Admin uchun:\n"
"/add <kod> | <nom> | <link>\n"
"Misol: /add 101 | Avatar (2009) | https://t.me/kanal/123"
)

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
if update.message and not await check_force_sub(update, context):
return
rows = db_list_movies(50)
if not rows:
await update.message.reply_text("Hozircha kino yo‘q. Admin /add bilan qo‘shadi.")
return
text = "📃 Kino ro‘yxati:\n" + "\n".join([f"{c} — {t}" for c, t in rows])
await update.message.reply_text(text)

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
msg = update.message
if not msg:
return

if not is_admin(msg.from_user.id):  
    await msg.reply_text("⛔ Admin emassiz.")  
    return  

# Format: /add code | title | url  
raw = msg.text or ""  
raw = raw.replace("/add", "", 1).strip()  
parts = [p.strip() for p in raw.split("|")]  
if len(parts) != 3:  
    await msg.reply_text(  
        "❌ Noto‘g‘ri format.\n"  
        "To‘g‘risi: /add <kod> | <nom> | <link>\n"  
        "Misol: /add 101 | Test kino | https://t.me/kanal/123"  
    )  
    return  

code, title, url = parts  
code = code.strip()  
if not code:  
    await msg.reply_text("❌ Kod bo‘sh bo‘lmasin.")  
    return  
if not (url.startswith("http://") or url.startswith("https://") or url.startswith("t.me/")):  
    await msg.reply_text("❌ Link noto‘g‘ri. https://... bo‘lsin.")  
    return  

db_add_movie(code, title, url)  
await msg.reply_text(f"✅ Kino qo‘shildi: {code}")

async def code_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
msg = update.message
if not msg:
return

if not await check_force_sub(update, context):  
    return  

text = (msg.text or "").strip()  

# agar odam /add yozib yuborsa, bu yerga tushmasin  
if text.startswith("/"):  
    return  

# kod faqat raqam/harf bo‘lishi mumkin — lekin sen xohlagancha qoldiraman  
row = db_get_movie(text)  
if not row:  
    await msg.reply_text("❌ Bunday kod topilmadi.")  
    return  

title, url = row  
await msg.reply_text(f"🎬 {title}\n🔗 {url}", disable_web_page_preview=False)

def main():
db_init()
app = Application.builder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))  
app.add_handler(CommandHandler("help", help_cmd))  
app.add_handler(CommandHandler("list", list_cmd))  
app.add_handler(CommandHandler("add", add_cmd))  

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, code_message))  

app.run_polling(drop_pending_updates=True)

if name == "main":
main()
