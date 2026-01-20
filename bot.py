import os
from aiogram import Bot, Dispatcher, executor, types

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start(m: types.Message):
    await m.answer("✅ Bot ishlayapti. GitHub + Railway tayyor.")

if __name__ == "__main__":
    executor.start_polling(dp)
