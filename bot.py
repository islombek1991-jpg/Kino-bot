import os
import sqlite3
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi (Railway Variables ga qo'ying)")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
if OWNER_ID == 0:
    raise ValueError("OWNER_ID topilmadi (Railway Variables ga qo'ying)")

# SQLite fayl yo'li (Railway Volume ishlatsang /data juda yaxshi)
DB_PATH = os.getenv("DB_PATH", "data.db")

# ===== DB =====
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS admins(
        user_id INTEGER PRIMARY KEY,
        added_at TEXT
      )
    """)
    cur.execute("""
      CREATE TABLE IF NOT EXISTS channels(
        username TEXT PRIMARY KEY,
        added_at TEXT
      )
    """)
    cur.execute("""
      CREATE TABLE IF NOT EXISTS movies(
        code TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        link TEXT NOT NULL,
        added_at TEXT NOT NULL
      )
    """)
    # OWNER ni admin qilamiz
    cur.execute("INSERT OR IGNORE INTO admins(user_id, added_at) VALUES(?,?)",
                (OWNER_ID, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def is_admin(user_id: int) -> bool:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
    ok = cur.fetchone() is not None
    conn.close()
    return ok

def add_admin(user_id: int):
    conn = db()
    conn.execute("INSERT OR IGNORE INTO admins(user_id, added_at) VALUES(?,?)",
                 (user_id, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def del_admin(user_id: int):
    if user_id == OWNER_ID:
        return
    conn = db()
    conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def list_admins():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins ORDER BY user_id ASC")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows

def add_channel(username: str):
    username = username.strip()
    if not username:
        return
    if username.startswith("https://t.me/"):
        username = username.replace("https://t.me/", "").strip("/")
    if username.startswith("@"):
        username = username[1:]
    conn = db()
    conn.execute("INSERT OR IGNORE INTO channels(username, added_at) VALUES(?,?)",
                 (username, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def del_channel(username: str):
    username = username.strip()
    if username.startswith("@"):
        username = username[1:]
    conn = db()
    conn.execute("DELETE FROM channels WHERE username=?", (username,))
    conn.commit()
    conn.close()

def list_channels():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT username FROM channels ORDER BY username ASC")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows

def add_movie(code: str, title: str, link: str):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO movies(code,title,link,added_at) VALUES(?,?,?,?)",
        (code, title, link, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def get_movie(code: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT title, link FROM movies WHERE code=?", (code,))
    row = cur.fetchone()
    conn.close()
    return row

def del_movie(code: str):
    conn = db()
    conn.execute("DELETE FROM movies WHERE code=?", (code,))
    conn.commit()
    conn.close()

def list_movies(limit: int = 30):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT code, title FROM movies ORDER BY added_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def random_movie():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT code, title, link FROM movies ORDER BY RANDOM() LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row

# ===== Majburiy obuna tekshirish =====
async def is_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    channels = list_channels()
    if not channels:
        return True  # kanal qo'shilmagan bo'lsa tekshirmaydi

    user_id = update.effective_user.id

    for ch in channels:
        chat = f"@{ch}"
        try:
            member = await context.bot.get_chat_member(chat_id=chat, user_id=user_id)
            status = member.status  # "member", "administrator", "creator", "left", "kicked"
            if status in ("left", "kicked"):
                return False
        except Exception:
            # Bot kanalga admin qilinmagan bo'lsa yoki kanal topilmasa shu yerda yiqiladi
            return False
    return True

def join_keyboard():
    channels = list_channels()
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(f"➕ @{ch} ga obuna bo‘ling", url=f"https://t.me/{ch}")])
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(buttons)

def main_keyboard():
    return ReplyKeyboardMarkup(
        [["🎬 Kino qidirish", "🎲 Tasodifiy kino"],
         ["⭐ Top kinolar", "ℹ️ Yordam"]],
        resize_keyboard=True
    )

async def need_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔒 Botdan foydalanish uchun kanal(lar)ga obuna bo‘lish kerak.\n\n"
        "Obuna bo‘lib, keyin ✅ Tekshirish ni bosing.",
        reply_markup=join_keyboard()
    )

async def cb_check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ok = await is_subscribed(update, context)
    if ok:
        await q.message.reply_text("✅ Rahmat! Endi kino kodini yuboring (masalan: 01).", reply_markup=main_keyboard())
    else:
        await q.message.reply_text("❌ Hali obuna bo‘lmadingiz yoki bot kanalni tekshira olmayapti.\n"
                                   "Kanalga obuna bo‘ling va botni kanalga ADMIN qiling.",
                                   reply_markup=join_keyboard())

# ===== Handlers =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = await is_subscribed(update, context)
    if not ok:
        await need_subscribe(update, context)
        return

    await update.message.reply_text(
        "🎥 Kino botga xush kelibsiz!\n\n"
        "📌 Kino kodini yuboring (masalan: 01)\n"
        "🧩 Admin bo‘lsangiz /add bilan kino qo‘shasiz.",
        reply_markup=main_keyboard()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 Buyruqlar:\n"
        "/start — botni boshlash\n"
        "/random — tasodifiy kino\n"
        "/list — oxirgi 30 ta kino\n\n"
        "👑 Admin buyruqlar:\n"
        "/add KOD | NOMI | LINK\n"
        "Misol: /add 01 | Qabir azobi | https://t.me/IsboySkinolar_olami/4\n"
        "/del KOD\n"
        "/admin_add 123456789\n"
        "/admin_del 123456789\n"
        "/admins\n"
        "/ch_add @kanal\n"
        "/ch_del @kanal\n"
        "/channels\n\n"
        "🔒 Majburiy obuna ishlashi uchun:\n"
        "Botni kanalga ADMIN qilib qo‘ying."
    )
    await update.message.reply_text(text)

async def random_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = await is_subscribed(update, context)
    if not ok:
        await need_subscribe(update, context)
        return

    row = random_movie()
    if not row:
        await update.message.reply_text("📭 Hali kino yo‘q.")
        return
    code, title, link = row
    await update.message.reply_text(f"🎲 {code} — {title}\n🔗 {link}")

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = await is_subscribed(update, context)
    if not ok:
        await need_subscribe(update, context)
        return

    rows = list_movies(30)
    if not rows:
        await update.message.reply_text("📭 Hali kino yo‘q.")
        return
    msg = "⭐ Oxirgi kinolar:\n" + "\n".join([f"{c} — {t}" for c, t in rows])
    await update.message.reply_text(msg)

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    try:
        text = update.message.text.replace("/add", "").strip()
        code, title, link = [x.strip() for x in text.split("|")]
        if not code or not title or not link:
            raise ValueError()
        add_movie(code, title, link)
        await update.message.reply_text(f"✅ Kino qo‘shildi: {code}")
    except:
        await update.message.reply_text(
            "❌ Format xato.\n\n"
            "To‘g‘ri:\n"
            "/add 01 | Qabir azobi | https://t.me/IsboySkinolar_olami/4"
        )

async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Misol: /del 01")
        return
    code = parts[1].strip()
    del_movie(code)
    await update.message.reply_text(f"🗑 O‘chirildi: {code}")

async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # faqat OWNER admin qo'shsin
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Faqat OWNER admin qo‘sha oladi.")
        return
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Misol: /admin_add 5491302235")
        return
    uid = int(parts[1])
    add_admin(uid)
    await update.message.reply_text(f"✅ Admin qo‘shildi: {uid}")

async def admin_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Faqat OWNER admin o‘chira oladi.")
        return
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Misol: /admin_del 123456789")
        return
    uid = int(parts[1])
    del_admin(uid)
    await update.message.reply_text(f"🗑 Admin o‘chirildi: {uid}")

async def admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin emassiz.")
        return
    ids = list_admins()
    await update.message.reply_text("👥 Adminlar:\n" + "\n".join([str(x) for x in ids]))

async def ch_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Faqat OWNER kanal qo‘sha oladi.")
        return
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("❌ Misol: /ch_add @IsboySkinolar_olami")
        return
    add_channel(parts[1].strip())
    await update.message.reply_text("✅ Kanal qo‘shildi. Endi botni o‘sha kanalga ADMIN qiling.")

async def ch_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Faqat OWNER kanal o‘chira oladi.")
        return
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("❌ Misol: /ch_del @IsboySkinolar_olami")
        return
    del_channel(parts[1].strip())
    await update.message.reply_text("🗑 Kanal o‘chirildi.")

async def channels_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chs = list_channels()
    if not chs:
        await update.message.reply_text("📭 Majburiy obuna kanali yo‘q. /ch_add bilan qo‘shasiz.")
        return
    await update.message.reply_text("🔒 Majburiy obuna kanallari:\n" + "\n".join([f"@{x}" for x in chs]))

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()

    # tugmalar
    if txt == "🎬 Kino qidirish":
        ok = await is_subscribed(update, context)
        if not ok:
            await need_subscribe(update, context)
            return
        await update.message.reply_text("🔎 Kino kodini yuboring (masalan: 01).")
        return

    if txt == "🎲 Tasodifiy kino":
        await random_cmd(update, context)
        return

    if txt == "⭐ Top kinolar":
        await list_cmd(update, context)
        return

    if txt == "ℹ️ Yordam":
        await help_cmd(update, context)
        return

    # oddiy kod
    ok = await is_subscribed(update, context)
    if not ok:
        await need_subscribe(update, context)
        return

    row = get_movie(txt)
    if row:
        title, link = row
        await update.message.reply_text(f"🎬 {txt} — {title}\n🔗 {link}")
    else:
        await update.message.reply_text("❌ Bunday kod topilmadi. /list yoki /random.")

def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("random", random_cmd))
    app.add_handler(CommandHandler("list", list_cmd))

    # admin
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("del", del_cmd))
    app.add_handler(CommandHandler("admin_add", admin_add))
    app.add_handler(CommandHandler("admin_del", admin_del))
    app.add_handler(CommandHandler("admins", admins_cmd))

    # channels
    app.add_handler(CommandHandler("ch_add", ch_add))
    app.add_handler(CommandHandler("ch_del", ch_del))
    app.add_handler(CommandHandler("channels", channels_cmd))

    # callback
    app.add_handler(CallbackQueryHandler(cb_check_sub, pattern="^check_sub$"))

    # text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    app.run_polling()

if __name__ == "__main__":
    main()
