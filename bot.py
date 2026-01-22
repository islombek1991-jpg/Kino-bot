import os
import json
from aiogram import Bot, Dispatcher, executor, types

# ========= CONFIG =========
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN topilmadi")

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]

DATA_FILE = "movies.json"

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ========= STORAGE =========
def load_movies() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_movies(movies: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)

movies = load_movies()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ========= COMMANDS =========
@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    text = (
        "✅ Bot ishlayapti. Railway tayyor.\n\n"
        "🎬 Kino olish: 101 (kodni yozing)\n"
        "📌 Yoki: /get 101\n\n"
        "👮 Admin bo‘lsangiz kino qo‘shish:\n"
        "/add 101 | Kino nomi | https://t.me/kanal/123\n\n"
        "📃 Ro‘yxat: /list"
    )
    await message.answer(text)

@dp.message_handler(commands=["add"])
async def add_movie(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Admin emassiz.")
        return

    # Format: /add 101 | Kino nomi | https://t.me/kanal/123
    data = message.text.replace("/add", "", 1).strip()
    try:
        code, title, link = [x.strip() for x in data.split("|")]
        if not code.isdigit():
            await message.reply("❌ Kod faqat raqam bo‘lsin. Masalan: 101")
            return
        if not title or not link:
            await message.reply("❌ Kino nomi va link bo‘sh bo‘lmasin.")
            return
    except:
        await message.reply(
            "❌ Format xato.\n\n"
            "✅ To‘g‘ri misol:\n"
            "/add 101 | Test kino | https://t.me/kanal/123"
        )
        return

    movies[code] = {"title": title, "link": link}
    save_movies(movies)
    await message.reply(f"✅ Qo‘shildi!\n\n🎬 {code} — {title}\n🔗 {link}")

@dp.message_handler(commands=["get"])
async def get_movie_cmd(message: types.Message):
    args = message.get_args().strip()
    if not args:
        await message.reply("❌ Kod yozing. Misol: /get 101")
        return
    code = args.split()[0].strip()
    await send_movie(message, code)

@dp.message_handler(commands=["list"])
async def list_movies(message: types.Message):
    if not movies:
        await message.reply("📭 Hozircha kino yo‘q.")
        return

    # Juda uzun bo‘lib ketmasin deb 50 tagacha ko‘rsatamiz
    items = sorted(movies.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0])
    items = items[:50]

    lines = ["📃 Kino ro‘yxati (1-50):\n"]
    for code, info in items:
        title = info.get("title", "")
        lines.append(f"{code} — {title}")

    await message.reply("\n".join(lines))

# ========= TEXT HANDLER (kod yozsa) =========
async def send_movie(message: types.Message, code: str):
    info = movies.get(code)
    if not info:
        await message.reply("❌ Bunday kod topilmadi.")
        return

    title = info.get("title", "Kino")
    link = info.get("link", "")

    await message.reply(f"🎬 {code} — {title}\n🔗 {link}")

@dp.message_handler()
async def any_text(message: types.Message):
    text = message.text.strip()
    # Faqat raqam bo‘lsa — kino kodi deb olamiz
    if text.isdigit():
        await send_movie(message, text)
    else:
        await message.reply("❓ Kod yuboring. Masalan: 101")

# ========= RUN =========
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
