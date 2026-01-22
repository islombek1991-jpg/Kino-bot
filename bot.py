import os
import re
import sqlite3
import random
from typing import List, Optional, Tuple

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
    ContextTypes,
    filters,
)

# =========================
#   ENV / SETTINGS
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
DB_PATH = os.getenv("DB_PATH", "data.db").strip()

# Majburiy obuna kanallari (usernamelar)
# Masalan: @IsboySkinolar_olami
FORCE_CHANNELS_RAW = os.getenv("FORCE_CHANNELS", "@IsboySkinolar_olami").strip()

# --- validations ---
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi (Railway Variables ga qo'ying)")
if OWNER_ID == 0:
    raise ValueError("OWNER_ID topilmadi (Railway Variables ga qo'ying)")

def parse_admin_ids(raw: str) -> List[int]:
    # raw: "5491302235,123456"
    ids = []
    for x in raw.split(","):
        x = x.strip()
        if x.isdigit():
            ids.append(int(x))
    return ids

ADMIN_IDS = parse_admin_ids(ADMIN_IDS_RAW)
if OWNER_ID not in ADMIN_IDS:
    ADMIN_IDS = [OWNER_ID] + ADMIN_IDS

def parse_channels(raw: str) -> List[str]:
    # "@a,@b" yoki "@a"
    chans = []
    for c in raw.split(","):
        c = c.strip()
        if not c:
            continue
        if not c.startswith("@"):
            c = "@" + c
        chans.append(c)
    # duplicate remove
    uniq = []
    for c in chans:
        if c not in uniq:
            uniq.append(c)
    return uniq

FORCE_CHANNELS = parse_channels(FORCE_CHANNELS_RAW)


# =========================
#   DB
# =========================
def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def db_init():
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            added_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            k TEXT PRIMARY KEY,
            v TEXT
        )
    """)
    con.commit()
    con.close()

def db_add_movie(code: str, title: str, url: str, added_by: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO movies(code,title,url,added_by) VALUES(?,?,?,?)",
        (code, title, url, added_by),
    )
    con.commit()
    con.close()

def db_get_movie(code: str) -> Optional[Tuple[str, str, str]]:
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT code,title,url FROM movies WHERE code = ?", (code,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return (row[0], row[1], row[2])

def db_list_recent(limit: int = 30) -> List[Tuple[str, str]]:
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT code,title FROM movies ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    con.close()
    return [(r[0], r[1]) for r in rows]

def db_random_movie() -> Optional[Tuple[str, str, str]]:
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT code,title,url FROM movies ORDER BY RANDOM() LIMIT 1")
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return (row[0], row[1], row[2])

def db_count() -> int:
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM movies")
    n = cur.fetchone()[0]
    con.close()
    return int(n)


# =========================
#   HELPERS
# =========================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def normalize_code(code: str) -> str:
    # "01" -> "01" (saqlab qolamiz), "1" -> "1"
    code = code.strip()
    # faqat raqam bo'lsa
    if re.fullmatch(r"\d+", code):
        return code
    return code

def parse_add_payload(text: str) -> Optional[Tuple[str, str, str]]:
    """
    /add 01 | Qabir azobi | https://t.me/IsboySkinolar_olami/4
    """
    # /add dan keyin
    m = re.match(r"^/add\s+(.+)$", text, flags=re.IGNORECASE)
    if not m:
        return None
    payload = m.group(1).strip()
    parts = [p.strip() for p in payload.split("|")]
    if len(parts) != 3:
        return None
    code, title, url = parts
    if not code or not title or not url:
        return None
    return normalize_code(code), title, url

async def is_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Foydalanuvchi FORCE_CHANNELS dagi hamma kanallarga obuna bo'lganini tekshiradi.
    Bot kanal ichida admin bo'lishi shart (kamida 'Read Messages' bo'lsa yaxshi).
    """
    if not FORCE_CHANNELS:
        return True

    user = update.effective_user
    if not user:
        return False

    user_id = user.id

    # admin/owner bo'lsa, tekshiruvni o'tkazib yuboramiz (xohlasang olib tashlaymiz)
    if is_admin(user_id):
        return True

    for channel in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            status = getattr(member, "status", None)
            if status not in ("member", "administrator", "creator"):
                return False
        except Exception:
            # bot kanalga kira olmasa yoki username xato bo'lsa:
            # xavfsiz tomondan "obuna emas" deymiz
            return False

    return True

def force_sub_keyboard() -> InlineKeyboardMarkup:
    btns = []
    for ch in FORCE_CHANNELS:
        link = f"https://t.me/{ch.lstrip('@')}"
        btns.append([InlineKeyboardButton(f"➕ {ch}", url=link)])
    btns.append([InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(btns)


# =========================
#   HANDLERS
# =========================
WELCOME_TEXT = (
    "🎬 <b>Kino botga xush kelibsiz!</b>\n\n"
    "📩 Kino kodini yuboring (masalan: <code>101</code>)\n"
    "yoki <code>/help</code>."
)

HELP_TEXT = (
    "📌 <b>Buyruqlar:</b>\n"
    "• <code>/start</code> — botni ishga tushirish\n"
    "• <code>/help</code> — yordam\n"
    "• <code>/top</code> — oxirgi qo‘shilgan kinolar\n"
    "• <code>/random</code> — tasodifiy kino\n"
    "• <code>/get 101</code> — kod bilan kino olish\n\n"
    "👑 <b>Adminlar uchun:</b>\n"
    "• <code>/add 01 | Qabir azobi | https://t.me/IsboySkinolar_olami/4</code>\n"
)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_subscribed(update, context):
        await update.message.reply_text(
            "🔒 Avval kanal(lar)ga obuna bo‘ling, keyin davom etasiz:",
            reply_markup=force_sub_keyboard()
        )
        return
    await update.message.reply_text(WELCOME_TEXT, parse_mode=ParseMode.HTML)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_subscribed(update, context):
        await update.message.reply_text(
            "🔒 Avval kanal(lar)ga obuna bo‘ling:",
            reply_markup=force_sub_keyboard()
        )
        return

    rows = db_list_recent(30)
    if not rows:
        await update.message.reply_text("Hali kino yo‘q. Admin kino qo‘shishi kerak.")
        return

    text = "🔥 <b>Oxirgi qo‘shilgan kinolar:</b>\n\n"
    for code, title in rows:
        text += f"<code>{code}</code> — {title}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def random_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_subscribed(update, context):
        await update.message.reply_text(
            "🔒 Avval kanal(lar)ga obuna bo‘ling:",
            reply_markup=force_sub_keyboard()
        )
        return

    m = db_random_movie()
    if not m:
        await update.message.reply_text("Hali kino yo‘q. Admin kino qo‘shishi kerak.")
        return
    code, title, url = m
    await update.message.reply_text(
        f"🎲 <b>Tasodifiy kino</b>\n\n🎬 <b>{title}</b>\n🔗 {url}\n\n<code>{code}</code>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )

async def get_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_subscribed(update, context):
        await update.message.reply_text(
            "🔒 Avval kanal(lar)ga obuna bo‘ling:",
            reply_markup=force_sub_keyboard()
        )
        return

    if not context.args:
        await update.message.reply_text("❌ Kod yozing. Misol: /get 101")
        return
    code = normalize_code(context.args[0])
    m = db_get_movie(code)
    if not m:
        await update.message.reply_text("❌ Bunday kod topilmadi.")
        return
    _, title, url = m
    await update.message.reply_text(
        f"🎬 <b>{title}</b>\n🔗 {url}",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    payload = parse_add_payload(update.message.text)
    if not payload:
        await update.message.reply_text(
            "❌ Format xato.\n\nTo‘g‘ri misol:\n"
            "/add 01 | Qabir azobi | https://t.me/IsboySkinolar_olami/4"
        )
        return

    code, title, url = payload
    db_add_movie(code, title, url, user.id)
    await update.message.reply_text(f"✅ Kino qo‘shildi: {code}")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_subscribed(update, context):
        await update.message.reply_text(
            "🔒 Avval kanal(lar)ga obuna bo‘ling:",
            reply_markup=force_sub_keyboard()
        )
        return

    text = (update.message.text or "").strip()

    # faqat kod yuborsa
    if re.fullmatch(r"\d+", text):
        code = normalize_code(text)
        m = db_get_movie(code)
        if not m:
            await update.message.reply_text("❌ Bunday kod topilmadi.")
            return
        _, title, url = m
        await update.message.reply_text(
            f"🎬 <b>{title}</b>\n🔗 {url}",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
        return

    # boshqa matn bo'lsa
    await update.message.reply_text("❓ Kod yuboring (masalan: 101) yoki /help")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if query.data == "check_sub":
        ok = await is_subscribed(update, context)
        if ok:
            await query.message.reply_text("✅ Obuna tasdiqlandi! Endi kod yuboring (masalan: 101).")
        else:
            await query.message.reply_text("❌ Hali obuna emassiz. Avval kanal(lar)ga obuna bo‘ling.")

# =========================
#   MAIN
# =========================
def main():
    db_init()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("random", random_cmd))
    app.add_handler(CommandHandler("get", get_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.COMMAND, help_cmd))
    app.add_handler(MessageHandler(filters.Regex(r"^.*$"), text_handler))
    app.add_handler(MessageHandler(filters.ALL, lambda u, c: None))
    app.add_handler(MessageHandler(filters.UpdateType.CALLBACK_QUERY, callback_handler))

    # PTB 20+ uchun
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
