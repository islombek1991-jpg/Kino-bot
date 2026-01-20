import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi! Railway Variables ga BOT_TOKEN ni kiriting.")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=["start"])
async def start(m: types.Message):
    await m.answer("✅ Bot ishlayapti. Railway + GitHub tayyor.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
