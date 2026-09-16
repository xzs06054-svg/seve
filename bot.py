import os
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    print("ПОМИЛКА: BOT_TOKEN не знайдено у .env")
    raise SystemExit(1)


bot = Bot(token=TOKEN)

dp = Dispatcher(
    storage=MemoryStorage()
)


@dp.business_message()
async def handle_business_message(message: Message):

    print("Отримано Business повідомлення")

    connection_id = message.business_connection_id

    if not connection_id:
        print("ПОМИЛКА: business_connection_id відсутній")
        return

    try:

        # Отримуємо Business-підключення
        connection = await bot.get_business_connection(
            business_connection_id=connection_id
        )

        owner_id = connection.user_chat_id

        print("Business connection:", connection_id)
        print("Власник:", owner_id)
        print("Підключення активне:", connection.is_enabled)

        if not connection.is_enabled:
            print("Business-підключення вимкнене.")
            return

        # Відправляємо копію повідомлення власнику
        await bot(
            message.send_copy(
                chat_id=owner_id
            )
        )

        print("УСПІШНО: повідомлення скопійовано.")
        print()

    except Exception as e:

        print()
        print("ПОМИЛКА ПРИ КОПІЮВАННІ:")
        print(str(e))
        print()


async def main():

    print("Бот запускається...")
    print()

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    me = await bot.get_me()

    print("Бот:", me.username)
    print("ID:", me.id)
    print()
    print("Очікування Business-повідомлень...")
    print()

    await dp.start_polling(bot)


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:

        print()
        print("Бот зупинений.")