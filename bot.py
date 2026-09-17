import asyncio
import logging
import os
import re

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не знайдено")

API_URL = "https://api.telegram.org/bot" + TOKEN

PORT = int(os.getenv("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv(
    "WEBHOOK_SECRET",
    "seve_bot_webhook_secret"
)

muted_users = set()
deleted_messages_cache = {}

auto_responder_enabled = True

auto_responder_text = (
    "привіт це мій авто відповідач\n"
    "я прийду в найближчий час\n"
    "будьласка без спаму"
)

waiting_for_text = False


async def tg_api(session, method, **kwargs):
    try:
        async with session.post(
            API_URL + "/" + method,
            json=kwargs
        ) as response:

            try:
                data = await response.json()
            except Exception:
                text = await response.text()
                return {
                    "ok": False,
                    "description": text
                }

            if not data.get("ok"):
                print(
                    "Telegram API ERROR:",
                    method,
                    data.get("description")
                )

            return data

    except Exception as e:
        print("NETWORK ERROR:", method, str(e))
        return {
            "ok": False,
            "description": str(e)
        }


def settings_keyboard():
    status = (
        "🟢 Увімкнено"
        if auto_responder_enabled
        else "🔴 Вимкнено"
    )

    return {
        "inline_keyboard": [
            [
                {
                    "text": "Автовідповідач: " + status,
                    "callback_data": "toggle_ar"
                }
            ],
            [
                {
                    "text": "⚙️ Налаштувати текст",
                    "callback_data": "edit_ar_text"
                }
            ]
        ]
    }


def msg_preview(msg):
    if "text" in msg:
        return msg["text"]

    if "photo" in msg:
        return "[Фото] " + msg.get("caption", "")

    if "video" in msg:
        return "[Відео] " + msg.get("caption", "")

    if "video_note" in msg:
        return "[Кружок]"

    if "voice" in msg:
        return "[Голосове повідомлення]"

    if "document" in msg:
        return "[Файл: " + msg["document"].get(
            "file_name",
            "документ"
        ) + "]"

    if "sticker" in msg:
        return "[Стікер]"

    if "animation" in msg:
        return "[GIF / Анімація]"

    if "audio" in msg:
        return "[Аудіо]"

    return "[Медіаповідомлення]"


async def send_media_to_owner(session, owner_id, msg):
    sender = msg.get("from", {})

    name = sender.get("first_name", "Клієнт")
    username = sender.get("username")
    sender_id = sender.get("id", "?")

    if username:
        user_info = "@" + username
    else:
        user_info = "ID: " + str(sender_id)

    header = (
        "📥 Нове повідомлення від "
        + name
        + " ("
        + user_info
        + "):"
    )

    caption = msg.get("caption", "")

    if caption:
        caption_text = header + "\n\n" + caption
    else:
        caption_text = header

    if "text" in msg:
        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=header + "\n\n" + msg["text"]
        )

    elif "photo" in msg:
        await tg_api(
            session,
            "sendPhoto",
            chat_id=owner_id,
            photo=msg["photo"][-1]["file_id"],
            caption=caption_text
        )

    elif "video" in msg:
        await tg_api(
            session,
            "sendVideo",
            chat_id=owner_id,
            video=msg["video"]["file_id"],
            caption=caption_text
        )

    elif "document" in msg:
        await tg_api(
            session,
            "sendDocument",
            chat_id=owner_id,
            document=msg["document"]["file_id"],
            caption=caption_text
        )

    elif "voice" in msg:
        await tg_api(
            session,
            "sendVoice",
            chat_id=owner_id,
            voice=msg["voice"]["file_id"],
            caption=caption_text
        )

    elif "video_note" in msg:
        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=header + " [кружок]"
        )

        await tg_api(
            session,
            "sendVideoNote",
            chat_id=owner_id,
            video_note=msg["video_note"]["file_id"]
        )

    elif "sticker" in msg:
        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=header + " [стікер]"
        )

        await tg_api(
            session,
            "sendSticker",
            chat_id=owner_id,
            sticker=msg["sticker"]["file_id"]
        )

    elif "animation" in msg:
        await tg_api(
            session,
            "sendAnimation",
            chat_id=owner_id,
            animation=msg["animation"]["file_id"],
            caption=caption_text
        )

    elif "audio" in msg:
        await tg_api(
            session,
            "sendAudio",
            chat_id=owner_id,
            audio=msg["audio"]["file_id"],
            caption=caption_text
        )


async def send_auto_responder(
    session,
    connection_id,
    chat_id,
    message_id,
    sender_id
):
    global auto_responder_enabled

    if not auto_responder_enabled:
        print("AUTO RESPONDER: вимкнений")
        return

    print("")
    print("🤖 АВТОВІДПОВІДАЧ")
    print("connection:", connection_id)
    print("chat:", chat_id)
    print("message:", message_id)
    print("sender:", sender_id)
    print("text:", repr(auto_responder_text))

    # Головне:
    # НЕ використовуємо reply_to_message_id.
    # Відправляємо звичайне Business-повідомлення.
    result = await tg_api(
        session,
        "sendMessage",
        business_connection_id=connection_id,
        chat_id=chat_id,
        text=auto_responder_text
    )

    if result.get("ok"):
        print(
            "✅ АВТОВІДПОВІДЬ ВІДПРАВЛЕНА"
        )
    else:
        print(
            "❌ АВТОВІДПОВІДЬ НЕ ВІДПРАВЛЕНА:",
            result.get("description")
        )


async def handle_business_message(session, msg):
    connection_id = msg.get("business_connection_id")

    if not connection_id:
        print("❌ Нема business_connection_id")
        return

    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type")

    message_id = msg.get("message_id")

    sender = msg.get("from", {})
    sender_id = sender.get("id")

    text = msg.get("text", "")

    reply_to = msg.get("reply_to_message")

    print("")
    print("=" * 50)
    print("📩 BUSINESS MESSAGE")
    print("connection:", connection_id)
    print("chat:", chat_id)
    print("type:", chat_type)
    print("sender:", sender_id)
    print("message:", message_id)
    print("text:", repr(text))
    print("=" * 50)

    if chat_type != "private":
        return

    # Отримуємо Business Connection
    connection_result = await tg_api(
        session,
        "getBusinessConnection",
        business_connection_id=connection_id
    )

    if not connection_result.get("ok"):
        print(
            "❌ getBusinessConnection:",
            connection_result.get("description")
        )
        return

    connection = connection_result.get("result", {})

    if not connection.get("is_enabled"):
        print("❌ Business connection вимкнений")
        return

    owner_user = connection.get("user", {})
    owner_id = owner_user.get("id")

    rights = connection.get("rights", {})

    print("Business owner:", owner_id)
    print("can_reply:", rights.get("can_reply"))
    print("can_delete_messages:", rights.get("can_delete_messages"))

    # =====================================================
    # ПОВІДОМЛЕННЯ ВІД КЛІЄНТА
    # =====================================================

    if sender_id != owner_id:

        # Передаємо повідомлення власнику
        await send_media_to_owner(
            session,
            connection.get("user_chat_id"),
            msg
        )

        # Автовідповідач
        await send_auto_responder(
            session,
            connection_id,
            chat_id,
            message_id,
            sender_id
        )

        # MUTЕ
        if sender_id in muted_users:

            print(
                "🤐 Користувач зам'ючений:",
                sender_id
            )

            if sender_id not in deleted_messages_cache:
                deleted_messages_cache[sender_id] = []

            deleted_messages_cache[sender_id].append(
                msg_preview(msg)
            )

            delete_result = await tg_api(
                session,
                "deleteMessage",
                business_connection_id=connection_id,
                chat_id=chat_id,
                message_id=message_id
            )

            if delete_result.get("ok"):
                print("🗑 Повідомлення видалено")
            else:
                print(
                    "❌ deleteMessage:",
                    delete_result.get("description")
                )

        return

    # =====================================================
    # КОМАНДИ ВЛАСНИКА
    # =====================================================

    if not text.startswith("."):
        return

    # .mute
    if text.startswith(".mute"):

        if not reply_to:
            await tg_api(
                session,
                "editMessageText",
                business_connection_id=connection_id,
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Відповідай на повідомлення юзера!"
            )
            return

        target_id = reply_to.get("from", {}).get("id")

        if target_id:
            muted_users.add(target_id)

        await tg_api(
            session,
            "editMessageText",
            business_connection_id=connection_id,
            chat_id=chat_id,
            message_id=message_id,
            text="🤐 Користувача зам'ючено."
        )

        return

    # .unmute
    if text.startswith(".unmute") or text.startswith(".umute"):

        if not reply_to:
            await tg_api(
                session,
                "editMessageText",
                business_connection_id=connection_id,
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Відповідай на повідомлення юзера!"
            )
            return

        target_id = reply_to.get("from", {}).get("id")

        if target_id:
            muted_users.discard(target_id)

        await tg_api(
            session,
            "editMessageText",
            business_connection_id=connection_id,
            chat_id=chat_id,
            message_id=message_id,
            text="🔊 Користувача розм'ючено."
        )

        return

    # .nomute
    if text.startswith(".nomute"):

        if not reply_to:
            await tg_api(
                session,
                "editMessageText",
                business_connection_id=connection_id,
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Відповідай на повідомлення!"
            )
            return

        target_id = reply_to.get("from", {}).get("id")

        messages = deleted_messages_cache.get(
            target_id,
            []
        )

        if messages:
            history = "\n".join(
                "• " + x for x in messages
            )

            result_text = (
                "📥 Збережені повідомлення:\n\n"
                + history
            )

            deleted_messages_cache[target_id] = []

        else:
            result_text = (
                "📭 Немає збережених повідомлень."
            )

        await tg_api(
            session,
            "editMessageText",
            business_connection_id=connection_id,
            chat_id=chat_id,
            message_id=message_id,
            text=result_text
        )

        return

    # .spam текст кількість
    spam_match = re.match(
        r"^\.spam\s+(.+)\s+(\d+)$",
        text
    )

    if spam_match:

        spam_text = spam_match.group(1)

        count = min(
            int(spam_match.group(2)),
            100
        )

        await tg_api(
            session,
            "deleteMessage",
            business_connection_id=connection_id,
            chat_id=chat_id,
            message_id=message_id
        )

        for _ in range(count):

            await tg_api(
                session,
                "sendMessage",
                business_connection_id=connection_id,
                chat_id=chat_id,
                text=spam_text
            )

            await asyncio.sleep(0.1)

        return

    # .v / .v20
    anim_match = re.match(
        r"^\.v(\d*)\s+(.+)$",
        text,
        re.DOTALL
    )

    if anim_match:

        seconds_text = anim_match.group(1)
        animation_text = anim_match.group(2)

        seconds = (
            int(seconds_text)
            if seconds_text
            else 10
        )

        max_spaces = 8

        frames = []

        for i in range(max_spaces + 1):
            frames.append(
                "\u00A0" * i + animation_text
            )

        for i in range(max_spaces - 1, 0, -1):
            frames.append(
                "\u00A0" * i + animation_text
            )

        delay = max(
            1.0,
            seconds / len(frames)
        )

        end_time = (
            asyncio.get_event_loop().time()
            + seconds
        )

        index = 0

        while (
            asyncio.get_event_loop().time()
            < end_time
        ):

            frame = frames[
                index % len(frames)
            ]

            index += 1

            result = await tg_api(
                session,
                "editMessageText",
                business_connection_id=connection_id,
                chat_id=chat_id,
                message_id=message_id,
                text=frame
            )

            if not result.get("ok"):

                description = result.get(
                    "description",
                    ""
                )

                if (
                    "message is not modified"
                    in description
                    or "BUSINESS_PEER_INVALID"
                    in description
                ):
                    break

                await asyncio.sleep(1.5)

            else:
                await asyncio.sleep(delay)

        return


async def handle_private_message(session, msg):
    global waiting_for_text
    global auto_responder_text

    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")

    if (
        waiting_for_text
        and text
        and not text.startswith("/")
    ):

        auto_responder_text = text
        waiting_for_text = False

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=(
                "✅ Текст автовідповідача збережено!\n\n"
                + auto_responder_text
            ),
            reply_markup=settings_keyboard()
        )

        return

    if text in (
        "/start",
        "/settings",
        "/seting"
    ):

        waiting_for_text = False

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text="⚙️ Меню керування автовідповідачем:",
            reply_markup=settings_keyboard()
        )


async def handle_callback_query(session, cb):
    global auto_responder_enabled
    global waiting_for_text

    callback_id = cb["id"]

    message = cb.get("message", {})

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    message_id = message.get("message_id")

    data = cb.get("data")

    if data == "toggle_ar":

        auto_responder_enabled = (
            not auto_responder_enabled
        )

        status = (
            "увімкнено"
            if auto_responder_enabled
            else "вимкнено"
        )

        await tg_api(
            session,
            "answerCallbackQuery",
            callback_query_id=callback_id,
            text="Автовідповідач " + status
        )

        await tg_api(
            session,
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text="⚙️ Меню керування автовідповідачем:",
            reply_markup=settings_keyboard()
        )

    elif data == "edit_ar_text":

        waiting_for_text = True

        await tg_api(
            session,
            "answerCallbackQuery",
            callback_query_id=callback_id
        )

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=(
                "Напиши текст, який буде "
                "відправляти автовідповідач:"
            )
        )


async def process_update(session, update):

    if "business_message" in update:
        await handle_business_message(
            session,
            update["business_message"]
        )

    elif "message" in update:
        await handle_private_message(
            session,
            update["message"]
        )

    elif "callback_query" in update:
        await handle_callback_query(
            session,
            update["callback_query"]
        )


async def health(request):
    return web.Response(
        text="SEVE BOT OK"
    )


async def root(request):
    return web.Response(
        text="SEVE BOT RUNNING"
    )


async def telegram_webhook(request):

    if request.match_info["secret"] != WEBHOOK_SECRET:
        return web.Response(
            status=403,
            text="Forbidden"
        )

    try:
        update = await request.json()

        session = request.app["session"]

        await process_update(
            session,
            update
        )

        return web.json_response(
            {"ok": True}
        )

    except Exception as e:

        print(
            "WEBHOOK ERROR:",
            repr(e)
        )

        return web.json_response(
            {
                "ok": False,
                "error": str(e)
            },
            status=200
        )


async def setup_webhook(session):

    if not RENDER_URL:
        print(
            "RENDER_EXTERNAL_URL не заданий."
        )
        return

    webhook_url = (
        RENDER_URL
        + "/telegram/webhook/"
        + WEBHOOK_SECRET
    )

    print(
        "Встановлюю webhook:",
        webhook_url
    )

    result = await tg_api(
        session,
        "setWebhook",
        url=webhook_url,
        allowed_updates=[
            "message",
            "callback_query",
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages"
        ]
    )

    print(
        "setWebhook:",
        result
    )


async def create_app():

    timeout = aiohttp.ClientTimeout(
        total=60
    )

    session = aiohttp.ClientSession(
        timeout=timeout
    )

    app = web.Application()

    app["session"] = session

    app.router.add_get(
        "/",
        root
    )

    app.router.add_get(
        "/health",
        health
    )

    app.router.add_post(
        "/telegram/webhook/{secret}",
        telegram_webhook
    )

    await setup_webhook(session)

    async def cleanup(app):
        await app["session"].close()

    app.on_cleanup.append(cleanup)

    return app


async def main():

    print("")
    print("===================================")
    print("       SEVE BOT ЗАПУЩЕНО")
    print("===================================")
    print("PORT:", PORT)
    print("RENDER URL:", RENDER_URL)
    print("AUTO RESPONDER:", auto_responder_enabled)
    print("===================================")

    app = await create_app()

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )

    await site.start()

    print(
        "HTTP SERVER:",
        "0.0.0.0:" + str(PORT)
    )

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот зупинений.")

