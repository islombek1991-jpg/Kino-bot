import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi")

ADMIN_ID = 5491302235  # 👈 SENING TELEGRAM ID

MOVIES = {}

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["🎬 Kino qidirish"],
        ["🎲 Tasodifiy kino"]
    ]
    await update.message.reply_text(
        "🎥 Kino botga xush kelibsiz!\n\n"
        "Kino kodini yuboring (masalan: 01)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# /add
async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    try:
        text = update.message.text.replace("/add", "").strip()
        code, title, link = [x.strip() for x in text.split("|")]
        MOVIES[code] = (title, link)
        await update.message.reply_text(f"✅ Kino qo‘shildi: {code}")
    except:
        await update.message.reply_text(
            "❌ Noto‘g‘ri format.\n\n"
            "To‘g‘ri format:\n"
            "/add 01 | Kino nomi | https://t.me/kanal/123"
        )

# kino kodi
async def get_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code in MOVIES:
        title, link = MOVIES[code]
        await update.message.reply_text(f"🎬 {title}\n🔗 {link}")
    else:
        await update.message.reply_text("❌ Bunday kod topilmadi.")

# random
async def random_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not MOVIES:
        await update.message.reply_text("📭 Hali kino yo‘q.")
        return
    import random
    code = random.choice(list(MOVIES.keys()))
    title, link = MOVIES[code]
    await update.message.reply_text(f"🎲 {title}\n🔗 {link}")

# main
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_movie))
app.add_handler(CommandHandler("random", random_movie))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_movie))

app.run_polling()
