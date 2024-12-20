import telegram
from app.core import settings

api_key = settings.TELEGRAM_API_KEY
user_id = settings.TELEGRAM_USER_ID

prefix = "**【AutoFilm 任务通知】**\n"

async def send_message(text: str):
    if api_key and user_id:
        bot = telegram.Bot(token=api_key)
        await bot.send_message(chat_id=user_id, text=prefix + text)
    else:
        print("Telegram API key or user ID is not set.")