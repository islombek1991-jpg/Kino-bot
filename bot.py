import os
import sqlite3
from typing import List, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------------------
# ENV
# ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip() or "0")
DB_PATH = os.getenv("DB_PATH", "data.db").strip() or "data.db"

_admin_raw = os.getenv("ADMIN_IDS", "").replace(" ", "")
ADMIN_IDS = [int(x) for x in _admin_raw.split(",") if x.isdigit()]

_force_raw = os.getenv("FORCE_CHANNELS", "").replace(" ", "")
FORCE_CHANNELS = [x for x in _force_raw.split(",") if x.startswith("@")]

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi (Railway Variables ga qo'ying)")
if OWNER_ID == 0:
    raise ValueError("OWNER_ID topilmadi (Railway Variables ga qo'ying)")

# Owner har doim admin bo‘lsin
if OWNER_ID not in ADMIN_IDS:
    ADMIN_IDS.append(OWNER_ID)


# ---------------------------
# DB
# ---------------------------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
        """
    )
    conn.commit()
    return conn


def seed_admins():
    conn = db()
    for uid in ADMIN_IDS:
        conn.execute("INSERT OR IGNORE INTO admins(user_id) VALUES(?)", (uid,))
    conn.commit()
    conn.close()


def is_admin(user_id: int) -> bool:
    conn = db()
    cur = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
    ok = cur.fetchone() is not None
    conn.close()
    return ok


def add_admin(user_id: int):
    conn = db()
    conn.execute("INSERT OR IGNORE INTO admins(user_id) VALUES(?)", (user_id,))
    conn.commit()
    conn.close()


def del_admin(user_id: int):
    # OWNER ni o‘chirishga ruxsat yo‘q
    if user_id == OWNER_ID:
        return
    conn = db()
    conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def add_movie(code: str, title: str, url: str):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO movies(code, title, url) VALUES(?,?,?)",
        (code, title, url),
    )
    conn.commit()
    conn.close()


def del_movie(code: str):
    conn = db()
    conn.execute("DELETE FROM movies WHERE code=?", (code,))
    conn.commit()
    conn.close()


def get_movie(code: str) -> Tuple[str, str] | None:
    conn = db()
    cur = conn.execute("SELECT title, url FROM movies WHERE code=?", (code,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return row[0], row[1]


def list_movies(limit: int = 30) -> List[Tuple[str, str]]:
    conn = db()
    cur = conn.execute(
        "SELECT code, title FROM movies ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ---------------------------
# FORCE SUBSCRIBE
# ---------------------------
async def user_in_channel(app: Application, user_id: int, channel: str) -> bool:
    try:
        member = await app.bot.get_chat_member(chat_id=channel, user_id=user_id)
        # status: creator/administrator/member/left/kicked
        return member.status in ("creator", "administrator", "member")
    except Exception:
        # kanal topilmasa yoki bot admin bo‘lmasa ham foydalanuvchiga "obuna bo‘ling" deymiz
        return False


async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not FORCE_CHANNELS:
        return True

    user = update.effective_user
    if not user:
        return False

    # admin/owner tekshiruvi: adminlar majburiy obunadan ozod
    if is_admin(user.id):
        return True

    missing = []
    for ch in FORCE_CHANNELS:
        ok = await user_in_channel(context.application, user.id, ch)
        if not ok:
            missing.append(ch)

    if not missing:
        return True

    buttons = [[InlineKeyboardButton(f"✅ Obuna bo‘lish: {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in missing]
    buttons.append([InlineKeyboardButton("🔄 Tekshirish", callback_data="recheck_sub")])

    await update.message.reply_text(
        "🔒 Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo‘ling, keyin qayta tekshiring:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return False


# callback uchun
from telegram.ext import CallbackQueryHandler

async def recheck_sub_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    user_id = q.from_user.id
    missing = []
    for ch in FORCE_CHANNELS:
        ok = await user_in_channel(context.application, user_id, ch)
        if not ok:
            missing.append(ch)

    if missing:
        await q.edit_message_text(
            "❗ Hali obuna bo‘lmagansiz. Iltimos, obuna bo‘ling va yana 'Tekshirish' bosing."
        )
        return

    await q.edit_message_text("✅ Obuna tekshirildi! Endi kino kodini yuboring (masalan: 101).")


# ---------------------------
# HANDLERS
# ---------------------------
HELP_TEXT = (
    "📌 Buyruqlar:\n"
    "/start — botni ishga tushirish\n"
    "/help — yordam\n\n"
    "Adminlar uchun:\n"
    "/add KOD | NOMI | LINK\n"
    "/del KOD\n"
    "/list\n"
    "/admin_add ID\n"
    "/admin_del ID\n\n"
    "Oddiy foydalanuvchi:\n"
    "Kino kodini yuboradi (masalan: 101) → bot link beradi.\n"
)

def parse_add(text: str):
    # /add 01 | Qabir azobi | https://t.me/...
    parts = text.split(" ", 1)
    if len(parts) < 2:
        return None
    payload = parts[1]
    items = [x.strip() for x in payload.split("|")]
    if len(items) < 3:
        return None
    code = items[0]
    title = items[1]
    url = items[2]
    return code, title, url


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    ok = await check_force_sub(update, context)
    if not ok:
        return

    await update.message.reply_text(
        "🎬 Kino botga xush kelibsiz!\n\n"
        "Kino kodini yuboring (masalan: 101)\n"
        "Yordam: /help"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    ok = await check_force_sub(update, context)
    if not ok:
        return

    await update.message.reply_text(HELP_TEXT)


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    parsed = parse_add(update.message.text)
    if not parsed:
        await update.message.reply_text("❗ Format: /add KOD | NOMI | LINK\nMasalan: /add 101 | Avatar | https://t.me/kanal/3")
        return

    code, title, url = parsed
    add_movie(code, title, url)
    await update.message.reply_text(f"✅ Kino qo‘shildi: {code}\n🎬 {title}\n🔗 {url}")


async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("❗ Format: /del KOD\nMasalan: /del 101")
        return

    code = parts[1].strip()
    del_movie(code)
    await update.message.reply_text(f"🗑 O‘chirildi: {code}")


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    rows = list_movies(50)
    if not rows:
        await update.message.reply_text("Hali kino yo‘q.")
        return

    msg = "📃 Oxirgi kinolar:\n" + "\n".join([f"{c} — {t}" for c, t in rows])
    await update.message.reply_text(msg)


async def admin_add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    # faqat OWNER qo‘shadi
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Faqat egasi (OWNER) admin qo‘sha oladi.")
        return

    parts = update.message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await update.message.reply_text("❗ Format: /admin_add 123456789")
        return

    uid = int(parts[1])
    add_admin(uid)
    await update.message.reply_text(f"✅ Admin qo‘shildi: {uid}")


async def admin_del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Faqat egasi (OWNER) admin o‘chira oladi.")
        return

    parts = update.message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await update.message.reply_text("❗ Format: /admin_del 123456789")
        return

    uid = int(parts[1])
    if uid == OWNER_ID:
        await update.message.reply_text("❗ OWNER’ni o‘chirib bo‘lmaydi.")
        return

    del_admin(uid)
    await update.message.reply_text(f"🗑 Admin o‘chirildi: {uid}")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    ok = await check_force_sub(update, context)
    if not ok:
        return

    txt = (update.message.text or "").strip()

    # agar user kod yuborsa
    movie = get_movie(txt)
    if not movie:
        await update.message.reply_text("❌ Bunday kod topilmadi.\nKod yuboring (masalan: 101) yoki /help.")
        return

    title, url = movie
    await update.message.reply_text(f"🎬 {title}\n🔗 {url}")


def main():
    seed_admins()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CallbackQueryHandler(recheck_sub_cb, pattern="^recheck_sub$"))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # admin
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("del", del_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("admin_add", admin_add_cmd))
    app.add_handler(CommandHandler("admin_del", admin_del_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
