import os
import re
import sqlite3
from typing import List, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
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
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi")

ADMIN_IDS = os.getenv("ADMIN_IDS", "").strip()
ADMIN_SET = set()
if ADMIN_IDS:
    for x in ADMIN_IDS.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_SET.add(int(x))

# FORCE_CHANNELS: @channel1,@channel2
FORCE_CHANNELS_ENV = os.getenv("FORCE_CHANNELS", "").strip()

# DB
DB_PATH = os.getenv("DB_PATH", "data.db")


# -------------------------
# DB INIT
# -------------------------
def db_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    con = db_conn()
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS movies (
            code INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS force_channels (
            username TEXT PRIMARY KEY
        )
        """
    )
    con.commit()
    con.close()


def seed_force_channels_from_env():
    if not FORCE_CHANNELS_ENV:
        return
    chans = [c.strip() for c in FORCE_CHANNELS_ENV.split(",") if c.strip()]
    con = db_conn()
    cur = con.cursor()
    for ch in chans:
        if not ch.startswith("@"):
            ch = "@" + ch
        cur.execute("INSERT OR IGNORE INTO force_channels(username) VALUES(?)", (ch,))
    con.commit()
    con.close()


def get_force_channels() -> List[str]:
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT username FROM force_channels ORDER BY username")
    rows = cur.fetchall()
    con.close()
    return [r[0] for r in rows]


def add_force_channel(username: str):
    if not username.startswith("@"):
        username = "@" + username
    con = db_conn()
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO force_channels(username) VALUES(?)", (username,))
    con.commit()
    con.close()


def del_force_channel(username: str):
    if not username.startswith("@"):
        username = "@" + username
    con = db_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM force_channels WHERE username=?", (username,))
    con.commit()
    con.close()


def upsert_movie(code: int, title: str, url: str):
    con = db_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO movies(code,title,url) VALUES(?,?,?) "
        "ON CONFLICT(code) DO UPDATE SET title=excluded.title, url=excluded.url",
        (code, title, url),
    )
    con.commit()
    con.close()


def get_movie(code: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT code,title,url FROM movies WHERE code=?", (code,))
    row = cur.fetchone()
    con.close()
    return row


def list_movies(limit: int = 30) -> List[Tuple[int, str]]:
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT code,title FROM movies ORDER BY code DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    con.close()
    return rows


# -------------------------
# HELPERS
# -------------------------
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_SET


async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    True => allowed
    False => user must subscribe
    """
    channels = get_force_channels()
    if not channels:
        return True  # no forced sub

    user = update.effective_user
    if not user:
        return True

    not_joined = []
    for ch in channels:
        try:
            member = await context.bot.get_chat_member(chat_id=ch, user_id=user.id)
            status = getattr(member, "status", "")
            # allowed: member/administrator/creator
            if status not in ("member", "administrator", "creator"):
                not_joined.append(ch)
        except Exception:
            # if channel is private or bot has no access, treat as not joined
            not_joined.append(ch)

    if not_joined:
        btns = []
        for ch in not_joined:
            link = f"https://t.me/{ch.lstrip('@')}"
            btns.append([InlineKeyboardButton(f"✅ Obuna bo‘lish: {ch}", url=link)])
        btns.append([InlineKeyboardButton("🔄 Tekshirish", callback_data="check_sub")])
        await update.effective_message.reply_text(
            "❗ Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo‘ling:",
            reply_markup=InlineKeyboardMarkup(btns),
        )
        return False

    return True


def main_menu():
    kb = [
        [KeyboardButton("🎬 Kino qidirish")],
        [KeyboardButton("🔥 Eng mashhur kinolar"), KeyboardButton("🎲 Tasodifiy kino")],
        [KeyboardButton("ℹ️ Yordam")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def parse_add(text: str):
    """
    /add 101 | Title | url
    """
    m = re.match(r"^/add\s+(\d+)\s*\|\s*(.+?)\s*\|\s*(https?://\S+)\s*$", text.strip())
    if not m:
        return None
    return int(m.group(1)), m.group(2).strip(), m.group(3).strip()


# -------------------------
# HANDLERS
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return

    await update.message.reply_text(
        "🎥 Kino botga xush kelibsiz!\n\n"
        "✅ Kino kodini yuboring (masalan: 101)\n"
        "yoki menyudan tanlang.",
        reply_markup=main_menu(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return

    msg = (
        "📌 Buyruqlar:\n"
        "/start — botni ishga tushirish\n"
        "/get 101 — kod bo‘yicha kino olish\n"
        "/top — oxirgi qo‘shilgan kinolar ro‘yxati\n\n"
        "🔐 Admin uchun:\n"
        "/add 101 | Kino nomi | https://t.me/kanal/123\n"
        "/channels — majburiy obuna kanallarini boshqarish\n"
    )
    await update.message.reply_text(msg, reply_markup=main_menu())


async def get_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("❌ Kod yozing. Misol: /get 101")
        return
    code = int(context.args[0])
    row = get_movie(code)
    if not row:
        await update.message.reply_text("❌ Bunday kod topilmadi.")
        return
    _, title, url = row
    await update.message.reply_text(f"🎬 <b>{title}</b>\n🔗 {url}", parse_mode=ParseMode.HTML)


async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return

    rows = list_movies(30)
    if not rows:
        await update.message.reply_text("Hozircha kino yo‘q.")
        return
    text = "🔥 Oxirgi qo‘shilgan kinolar:\n\n" + "\n".join([f"{c} — {t}" for c, t in rows])
    await update.message.reply_text(text)


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /add should work even if not subscribed? Usually YES only for admins.
    user = update.effective_user
    if not user:
        return

    if not is_admin(user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    parsed = parse_add(update.message.text)
    if not parsed:
        await update.message.reply_text("❌ Format xato.\nMisol:\n/add 101 | Test kino | https://t.me/kanal/123")
        return

    code, title, url = parsed
    upsert_movie(code, title, url)
    await update.message.reply_text(f"✅ Kino qo‘shildi: {code}")


async def channels_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    if not is_admin(user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    chans = get_force_channels()
    if not chans:
        await update.message.reply_text(
            "Majburiy obuna kanali yo‘q.\n"
            "Qo‘shish: /chadd @kanal\n"
            "O‘chirish: /chdel @kanal"
        )
    else:
        await update.message.reply_text(
            "📌 Majburiy obuna kanallari:\n" + "\n".join(chans) +
            "\n\nQo‘shish: /chadd @kanal\nO‘chirish: /chdel @kanal"
        )


async def chadd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("❌ Misol: /chadd @IsboySkinolar_olami")
        return
    add_force_channel(context.args[0])
    await update.message.reply_text("✅ Kanal qo‘shildi.")


async def chdel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("❌ Misol: /chdel @IsboySkinolar_olami")
        return
    del_force_channel(context.args[0])
    await update.message.reply_text("✅ Kanal o‘chirildi.")


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return

    text = (update.message.text or "").strip()

    # menu buttons
    if text == "🎬 Kino qidirish":
        await update.message.reply_text("🔎 Kino kodini yuboring. Masalan: 101")
        return
    if text == "🔥 Eng mashhur kinolar":
        await top_cmd(update, context)
        return
    if text == "🎲 Tasodifiy kino":
        rows = list_movies(1)
        if not rows:
            await update.message.reply_text("Hozircha kino yo‘q.")
            return
        # fallback: last added (simple)
        code, title = rows[0]
        row = get_movie(code)
        _, t, url = row
        await update.message.reply_text(f"🎲 <b>{t}</b>\n🔗 {url}", parse_mode=ParseMode.HTML)
        return
    if text == "ℹ️ Yordam":
        await help_cmd(update, context)
        return

    # numeric code
    if text.isdigit():
        code = int(text)
        row = get_movie(code)
        if not row:
            await update.message.reply_text("❌ Bunday kod topilmadi.")
            return
        _, title, url = row
        await update.message.reply_text(f"🎬 <b>{title}</b>\n🔗 {url}", parse_mode=ParseMode.HTML)
        return

    await update.message.reply_text("❓ Tushunmadim. Kod yuboring (101) yoki /help.")


# -------------------------
# CALLBACKS (optional)
# -------------------------
from telegram.ext import CallbackQueryHandler

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "check_sub":
        # re-check
        # we can just send a new prompt if still not subscribed
        if await check_force_sub(update, context):
            await q.message.reply_text("✅ Obuna tekshirildi. Endi botdan foydalanishingiz mumkin.")
        return


def build_app():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("get", get_cmd))
    app.add_handler(CommandHandler("top", top_cmd))

    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("channels", channels_cmd))
    app.add_handler(CommandHandler("chadd", chadd_cmd))
    app.add_handler(CommandHandler("chdel", chdel_cmd))

    app.add_handler(CallbackQueryHandler(cb_handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    return app


if __name__ == "__main__":
    init_db()
    seed_force_channels_from_env()
    app = build_app()
    app.run_polling()
