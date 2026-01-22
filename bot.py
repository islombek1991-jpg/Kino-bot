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

# Admin ID
ADMIN_ID = 5491302235

# Kino bazasi (oddiy dict)
MOVIES = {
    "101": "🎬 Avatar (2009)\n🔗 https://t.me/IsboySkinolar_olami",
    "102": "🎬 Spider-Man (2002)\n🔗 https://t.me/IsboySkinolar_olami",
}

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        ["🎬 Kino qidirish", "🔥 Top kinolar"],
        ["🎲 Tasodifiy kino"]
    ]
    await update.message.reply_text(
        "🎥 Kino botga xush kelibsiz!\n\nKino kodini yuboring (masalan: 101)",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

# /add (faqat admin)
async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin emassiz.")
        return

    try:
        text = update.message.text.replace("/add", "").strip()
        code, title, link = [x.strip() for x in text.split("|")]
        MOVIES[code] = f"🎬 {title}\n🔗 {link}"
        await update.message.reply_text(f"✅ Kino qo‘shildi: {code}")
    except:
        await update.message.reply_text(
            "❌ Format xato.\n\nTo‘g‘ri format:\n/add 101 | Avatar | https://t.me/kanal/123"
        )

# Kino kodi bilan qidirish
async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code in MOVIES:
        await update.message.reply_text(MOVIES[code])
    else:
        await update.message.reply_text("❌ Bunday kod topilmadi.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_movie))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, find_movie))

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
