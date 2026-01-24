import os
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

# Telegram majburiy obuna (kanallar): "@kanal1,@kanal2"
FORCE_CHANNELS: List[str] = []
_raw_channels = os.getenv("FORCE_CHANNELS", "").strip()
if _raw_channels:
    for ch in _raw_channels.split(","):
        ch = ch.strip()
        if ch and not ch.startswith("@"):
            ch = "@" + ch
        if ch:
            FORCE_CHANNELS.append(ch)

# Instagram (tekshirilmaydi, faqat tugma)
IG_URL = os.getenv("IG_URL", "").strip()

# Adminlar (faqat /add uchun). Bo‘sh bo‘lsa — hamma /add qila oladi.
ADMIN_IDS: List[int] = []
_raw_admins = os.getenv("ADMIN_IDS", "").strip()
if _raw_admins:
    for x in _raw_admins.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.append(int(x))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi (Railway Variables ga qo'ying)")

MAIN_CHANNEL_URL = f"https://t.me/{FORCE_CHANNELS[0].lstrip('@')}" if FORCE_CHANNELS else None


# =======================
# DB (WAL + busy_timeout = qotib qolmasin)
# =======================
def db_conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA busy_timeout=5000;")  # 5s kutib ko‘radi
    return con

def db_init():
    with db_conn() as con:
        con.execute("""
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
        # views saqlanib qolsin
        cur = con.execute("SELECT views FROM movies WHERE code=?", (code,))
        row = cur.fetchone()
        old_views = int(row[0]) if row and row[0] is not None else 0

        con.execute(
            "INSERT OR REPLACE INTO movies(code,title,url,views) VALUES(?,?,?,?)",
            (code, title, url, old_views),
        )
        con.commit()

def db_get_movie(code: str) -> Optional[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.execute("SELECT title, url, views FROM movies WHERE code=?", (code,))
        row = cur.fetchone()
        if not row:
            return None
        return str(row[0]), str(row[1]), int(row[2] or 0)

def db_list_movies(limit: int = 50) -> List[Tuple[str, str]]:
    with db_conn() as con:
        cur = con.execute("SELECT code, title FROM movies ORDER BY code LIMIT ?", (limit,))
        return [(str(c), str(t)) for c, t in cur.fetchall()]

def db_inc_view(code: str):
    with db_conn() as con:
        con.execute("UPDATE movies SET views = views + 1 WHERE code=?", (code,))
        con.commit()

def db_top(limit: int = 10) -> List[Tuple[str, str, int]]:
    with db_conn() as con:
        cur = con.execute("SELECT code, title, views FROM movies ORDER BY views DESC LIMIT ?", (limit,))
        return [(str(c), str(t), int(v or 0)) for c, t, v in cur.fetchall()]


# =======================
# Helpers
# =======================
def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS

async def must_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE, pending_code: str = "") -> bool:
    """
    True -> ruxsat
    False -> obuna so‘raydi (Telegram tekshiradi, Instagram faqat tugma)
    """
    if not FORCE_CHANNELS:
        return True

    user = update.effective_user
    if not user:
        return False

    missing = []
    for ch in FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(ch, user.id)
            if member.status in ("left", "kicked"):
                missing.append(ch)
        except Exception:
            # bot admin bo'lmasa ham shu yerga tushadi => userdan obuna so'raymiz
            missing.append(ch)

    if not missing:
        return True

    buttons = []
    for ch in missing:
        buttons.append([InlineKeyboardButton(f"📢 Obuna bo‘lish: {ch}", url=f"https://t.me/{ch.lstrip('@')}")])
    if IG_URL:
        buttons.append([InlineKeyboardButton("📸 Instagramga follow", url=IG_URL)])
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data=f"recheck:{pending_code}")])

    text = (
        "🔒 Davom etish uchun kanal(lar)ga obuna bo‘ling.\n\n"
        "Obuna bo‘lgach ✅ <b>Tekshirish</b> ni bosing."
    )

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception:
            pass

    return False

async def send_locked_card(chat, code: str, title: str, views: int):
    """
    1-bosqich: user bosadi -> views oshadi -> keyin link tugma chiqadi
    """
    text = (
        f"🎬 <b>{title}</b>\n"
        f"🆔 Kod: <code>{code}</code>\n"
        f"⭐ Ko‘rilgan: <b>{views}</b>\n\n"
        "👇 Kinoni olish uchun tugmani bosing"
    )

    buttons = [[InlineKeyboardButton("🎬 KINONI KO‘RISH", callback_data=f"watch:{code}")]]
    if MAIN_CHANNEL_URL:
        buttons.append([InlineKeyboardButton("📢 Kanal", url=MAIN_CHANNEL_URL)])
    if IG_URL:
        buttons.append([InlineKeyboardButton("📸 Instagram", url=IG_URL)])

    await chat.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def send_unlocked_card(chat, code: str, title: str, url: str, views: int):
    """
    2-bosqich: views oshgan, endi linkli tugma
    """
    text = (
        f"✅ Tayyor!\n\n"
        f"🎬 <b>{title}</b>\n"
        f"🆔 Kod: <code>{code}</code>\n"
        f"⭐ Ko‘rilgan: <b>{views}</b>\n\n"
        "👇 Kinoni ochish uchun tugmani bosing"
    )

    buttons = [[InlineKeyboardButton("▶️ KINONI OCHISH", url=url)]]
    if MAIN_CHANNEL_URL:
        buttons.append([InlineKeyboardButton("📢 Kanal", url=MAIN_CHANNEL_URL)])
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
    if not await must_subscribe(update, context):
        return
    await update.message.reply_text(
        "🎬 Kino botga xush kelibsiz!\n\n"
        "Kino kodini yuboring (masalan: 01)\n"
        "/help — yordam"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Buyruqlar:\n"
        "/start — boshlash\n"
        "/help — yordam\n"
        "/list — 50 ta kino ro‘yxati\n"
        "/top — TOP-10 eng ko‘p ko‘rilgan\n\n"
        "🛠 Admin:\n"
        "/add <kod> | <nom> | <link>\n"
        "Misol: /add 01 | Troll | https://t.me/IsboySkinolar_olami/4"
    )

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await must_subscribe(update, context):
        return
    rows = db_list_movies(50)
    if not rows:
        await update.message.reply_text("Hozircha kino yo‘q. Admin /add bilan qo‘shadi.")
        return
    text = "📃 Kino ro‘yxati:\n" + "\n".join([f"{c} — {t}" for c, t in rows])
    await update.message.reply_text(text)

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await must_subscribe(update, context):
        return
    rows = db_top(10)
    if not rows:
        await update.message.reply_text("Hali ko‘rilgan kino yo‘q.")
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

    raw = (msg.text or "").replace("/add", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3:
        await msg.reply_text("❌ Format: /add KOD | NOMI | LINK")
        return

    code, title, url = parts
    if not code:
        await msg.reply_text("❌ Kod bo‘sh bo‘lmasin.")
        return
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("t.me/")):
        await msg.reply_text("❌ Link noto‘g‘ri (https://... bo‘lsin).")
        return

    db_add_movie(code, title, url)
    await msg.reply_text(f"✅ Qo‘shildi: {code}")

async def code_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    code = (msg.text or "").strip()
    if code.startswith("/"):
        return

    row = db_get_movie(code)
    if not row:
        await msg.reply_text("❌ Bunday kod topilmadi.")
        return

    if not await must_subscribe(update, context, pending_code=code):
        return

    title, url, views = row
    await send_locked_card(msg, code, title, views)

async def recheck_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    data = q.data or ""
    pending_code = data.split(":", 1)[1].strip() if ":" in data else ""

    # qayta tekshir
    if not await must_subscribe(update, context, pending_code=pending_code):
        return

    try:
        await q.edit_message_text("✅ Obuna tasdiqlandi!")
    except Exception:
        pass

    # agar kod bo'lsa, kino kartani qayta chiqaramiz
    if pending_code:
        row = db_get_movie(pending_code)
        if not row:
            await q.message.reply_text("❌ Bu kod topilmadi.")
            return
        title, url, views = row
        await send_locked_card(q.message, pending_code, title, views)
    else:
        await q.message.reply_text("Endi kino kodini yuboring (masalan: 01).")

async def watch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    data = q.data or ""
    code = data.split(":", 1)[1].strip() if ":" in data else ""
    if not code:
        return

    # yana obuna tekshir
    if not await must_subscribe(update, context, pending_code=code):
        return

    row = db_get_movie(code)
    if not row:
        await q.message.reply_text("❌ Bu kod topilmadi.")
        return

    title, url, views = row

    # views faqat shu yerda oshadi ✅
    db_inc_view(code)
    title, url, views = db_get_movie(code)

    await send_unlocked_card(q.message, code, title, url, views)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # bot qotib qolmasligi uchun xatolarni yutib yuboramiz
    try:
        print("ERROR:", context.error)
    except Exception:
        pass


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

    app.add_error_handler(error_handler)

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
