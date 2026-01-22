import os
import json
import base64
import asyncio
import re
import requests

from aiogram import Bot, Dispatcher, executor, types

# ========= ENV =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi")

# Adminlar: "123,456" ko'rinishida
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = set()
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.add(int(x))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()     # masalan: islombek1991-jpg/Kino-bot
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()
MOVIES_PATH = os.getenv("MOVIES_PATH", "movies.json").strip()

# GitHub orqali saqlash yoqiladimi?
USE_GITHUB_STORAGE = bool(GITHUB_TOKEN and GITHUB_REPO)

# ========= BOT =========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
lock = asyncio.Lock()

HELP_TEXT = (
    "🎬 Kino-bot\n\n"
    "Oddiy foydalanuvchi:\n"
    "• Kino kodini yuboring (masalan: 101)\n\n"
    "Admin buyruqlar:\n"
    "• /add 101 | Kino nomi | https://t.me/kanal/123\n"
    "• /del 101\n"
    "• /get 101\n"
    "• /list (50 tagacha)\n"
)

# ========= GitHub API helpers =========
def gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "kino-bot"
    }

def gh_api_url(path: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"

def gh_load_movies():
    """GitHub'dan movies.json o'qiydi"""
    url = gh_api_url(MOVIES_PATH)
    r = requests.get(url, headers=gh_headers(), params={"ref": GITHUB_BRANCH}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"GitHub GET error: {r.status_code} {r.text}")
    data = r.json()
    content_b64 = data.get("content", "")
    sha = data.get("sha")
    raw = base64.b64decode(content_b64).decode("utf-8") if content_b64 else "{}"
    movies = json.loads(raw or "{}")
    if not isinstance(movies, dict):
        movies = {}
    return movies, sha

def gh_save_movies(movies: dict, sha: str, message: str):
    """GitHub'ga movies.json commit qiladi"""
    url = gh_api_url(MOVIES_PATH)
    raw = json.dumps(movies, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(raw.encode("utf-8")).decode("utf-8")

    payload = {
        "message": message,
        "content": content_b64,
        "sha": sha,
        "branch": GITHUB_BRANCH
    }
    r = requests.put(url, headers=gh_headers(), json=payload, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GitHub PUT error: {r.status_code} {r.text}")
    return True

def local_load_movies():
    """Fallback: fayldan o'qiydi (restartda yo'qolishi mumkin)"""
    try:
        with open(MOVIES_PATH, "r", encoding="utf-8") as f:
            movies = json.load(f)
        if not isinstance(movies, dict):
            return {}
        return movies
    except Exception:
        return {}

def local_save_movies(movies: dict):
    with open(MOVIES_PATH, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)

def is_admin(user_id: int) -> bool:
    return (user_id in ADMIN_IDS)

def parse_add_args(text: str):
    """
    /add 101 | Title | URL
    """
    # /add dan keyingi qism
    rest = text.split(" ", 1)
    if len(rest) < 2:
        return None
    payload = rest[1].strip()
    parts = [p.strip() for p in payload.split("|")]
    if len(parts) < 3:
        return None
    code = parts[0]
    title = parts[1]
    url = parts[2]
    return code, title, url

def clean_code(code: str) -> str:
    code = code.strip()
    # faqat raqam
    if not re.fullmatch(r"\d{1,20}", code):
        return ""
    return code

def validate_url(url: str) -> bool:
    url = url.strip()
    return url.startswith("http://") or url.startswith("https://")

async def get_movies_and_sha():
    if USE_GITHUB_STORAGE:
        return gh_load_movies()
    else:
        return local_load_movies(), None

async def save_movies(movies: dict, sha: str, message: str):
    if USE_GITHUB_STORAGE:
        gh_save_movies(movies, sha, message)
    else:
        local_save_movies(movies)

# ========= Handlers =========
@dp.message_handler(commands=["start", "help"])
async def cmd_start(m: types.Message):
    await m.answer(HELP_TEXT)

@dp.message_handler(commands=["add"])
async def cmd_add(m: types.Message):
    if not is_admin(m.from_user.id):
        return await m.reply("⛔ Admin emassiz.")
    args = parse_add_args(m.text)
    if not args:
        return await m.reply("❌ Format xato.\nMisol:\n/add 101 | Kino nomi | https://t.me/kanal/123")
    code, title, url = args
    code = clean_code(code)
    title = title.strip()
    url = url.strip()

    if not code:
        return await m.reply("❌ Kod faqat raqam bo‘lsin. Misol: 101")
    if len(title) < 1 or len(title) > 120:
        return await m.reply("❌ Kino nomi 1-120 belgi oralig‘ida bo‘lsin.")
    if not validate_url(url):
        return await m.reply("❌ URL http/https bilan boshlansin.\nMisol: https://t.me/kanal/123")

    async with lock:
        movies, sha = await get_movies_and_sha()

        movies[code] = {"title": title, "url": url}

        try:
            await save_movies(movies, sha, f"Add movie {code}")
        except Exception as e:
            return await m.reply(f"❌ Saqlashda xato: {e}")

    await m.reply(f"✅ Qo‘shildi!\nKod: {code}\n🎬 {title}\n🔗 {url}")

@dp.message_handler(commands=["del"])
async def cmd_del(m: types.Message):
    if not is_admin(m.from_user.id):
        return await m.reply("⛔ Admin emassiz.")
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        return await m.reply("❌ Misol: /del 101")
    code = clean_code(parts[1])
    if not code:
        return await m.reply("❌ Kod faqat raqam bo‘lsin. Misol: 101")

    async with lock:
        movies, sha = await get_movies_and_sha()

        if code not in movies:
            return await m.reply("⚠️ Bu kod topilmadi.")
        deleted = movies.pop(code)

        try:
            await save_movies(movies, sha, f"Delete movie {code}")
        except Exception as e:
            return await m.reply(f"❌ O‘chirishda xato: {e}")

    await m.reply(f"✅ O‘chirildi: {code} — {deleted.get('title','')}")

@dp.message_handler(commands=["get"])
async def cmd_get(m: types.Message):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        return await m.reply("❌ Misol: /get 101")
    code = clean_code(parts[1])
    if not code:
        return await m.reply("❌ Kod faqat raqam bo‘lsin. Misol: 101")

    movies, _ = await get_movies_and_sha()
    item = movies.get(code)
    if not item:
        return await m.reply("😕 Topilmadi. Kodni tekshiring.")
    await m.reply(f"🎬 {item.get('title','(nom yo‘q)')}\n🔗 {item.get('url','')}")

@dp.message_handler(commands=["list"])
async def cmd_list(m: types.Message):
    if not is_admin(m.from_user.id):
        return await m.reply("⛔ Admin emassiz.")
    movies, _ = await get_movies_and_sha()
    if not movies:
        return await m.reply("Hali kino yo‘q.")
    # 50 tagacha ko'rsatamiz
    items = sorted(movies.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)[:50]
    lines = ["📜 Kino ro‘yxati (50 tagacha):\n"]
    for code, info in items:
        lines.append(f"{code} — {info.get('title','')}")
    await m.reply("\n".join(lines))

@dp.message_handler()
async def any_text(m: types.Message):
    # Foydalanuvchi kod yuborsa
    code = clean_code(m.text)
    if not code:
        return  # boshqa gaplarga javob bermaymiz (spam bo'lmasin)

    movies, _ = await get_movies_and_sha()
    item = movies.get(code)
    if not item:
        return await m.reply("😕 Bu kod bo‘yicha kino topilmadi. Kodni tekshiring.")
    title = item.get("title", "Kino")
    url = item.get("url", "")
    if url:
        await m.reply(f"🎬 {title}\n🔗 {url}")
    else:
        await m.reply(f"🎬 {title}\n⚠️ Link topilmadi.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
