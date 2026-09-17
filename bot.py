import asyncio
import logging
import os
import re
import aiohttp
from aiohttp import web
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    print("ПОМИЛКА: BOT_TOKEN не знайдено у змінних середовища")
    raise SystemExit(1)

API_URL = "https://api.telegram.org/bot" + TOKEN

# =========================
# СТАН БОТА
# =========================

muted_users = set()
deleted_messages_cache = {}

# =========================
# АВТОВІДПОВІДАЧ
# =========================

auto_responder_enabled = True

auto_responder_text = (
    "привіт це мій авто відповідач\n"
    "я прийду в найближчий час\n"
    "бульдласка без спаму"
)

waiting_for_text = False


# =========================
# TELEGRAM API
# =========================

async def tg_api(session, method, **kwargs):
    try:
        async with session.post(
            f"{API_URL}/{method}",
            json=kwargs
        ) as resp:
            return await resp.json()

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        return {
            "ok": False,
            "description": f"Network Error: {e}"
        }


# =========================
# RENDER WEB SERVER
# =========================

async def health(request):
    return web.Response(
        text="Telegram bot is running!"
    )


async def start_web_server():
    port = int(os.environ.get("PORT", "10000"))

    app = web.Application()

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    print("================================")
    print("WEB SERVER ЗАПУЩЕНИЙ")
    print("PORT:", port)
    print("================================")

    # Сервер працює постійно
    await asyncio.Event().wait()


# =========================
# SETTINGS KEYBOARD
# =========================

def get_settings_keyboard():
    status = (
        "🟢 Увімкнено"
        if auto_responder_enabled
        else "🔴 Вимкнено"
    )

    return {
        "inline_keyboard": [
            [
                {
                    "text": f"Автовідповідач: {status}",
                    "callback_data": "toggle_ar",
                }
            ],
            [
                {
                    "text": "⚙️ Налаштувати текст",
                    "callback_data": "edit_ar_text",
                }
            ],
        ]
    }


# =========================
# MESSAGE PREVIEW
# =========================

def get_msg_preview(msg):

    if "text" in msg:
        return msg["text"]

    elif "photo" in msg:
        return f"[Фото] {msg.get('caption', '')}".strip()

    elif "video" in msg:
        return f"[Відео] {msg.get('caption', '')}".strip()

    elif "video_note" in msg:
        return "[Кружок / Відеоповідомлення]"

    elif "voice" in msg:
        return "[Голосове повідомлення]"

    elif "document" in msg:
        return (
            f"[Файл: "
            f"{msg['document'].get('file_name', 'документ')}]"
        )

    elif "sticker" in msg:
        emoji = msg["sticker"].get("emoji", "")
        return f"[Наліпка {emoji}]".strip()

    elif "animation" in msg:
        return "[GIF / Анімація]"

    elif "audio" in msg:
        return f"[Аудіо] {msg.get('caption', '')}".strip()

    return "[Медіаповідомлення]"


# =========================
# SEND MEDIA TO OWNER
# =========================

async def send_media_to_owner(session, owner_id, msg):

    sender_name = msg.get(
        "from",
        {}
    ).get(
        "first_name",
        "Клієнт"
    )

    sender_username = msg.get(
        "from",
        {}
    ).get(
        "username"
    )

    user_info = (
        f"@{sender_username}"
        if sender_username
        else
        f"ID: {msg.get('from', {}).get('id')}"
    )

    header = (
        f"📥 Нове повідомлення від "
        f"{sender_name} ({user_info}):"
    )

    user_caption = msg.get(
        "caption",
        ""
    )

    caption_text = (
        f"{header}\n\n{user_caption}".strip()
        if user_caption
        else
        header
    )

    # =========================
    # TEXT
    # =========================

    if (
        "text" in msg
        and not any(
            k in msg
            for k in [
                "photo",
                "video",
                "document",
                "voice",
                "video_note",
                "sticker",
                "audio",
                "animation",
            ]
        )
    ):

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=f"{header}\n\n{msg['text']}",
        )

    # =========================
    # PHOTO
    # =========================

    elif "photo" in msg:

        photo_id = msg["photo"][-1]["file_id"]

        await tg_api(
            session,
            "sendPhoto",
            chat_id=owner_id,
            photo=photo_id,
            caption=caption_text,
        )

    # =========================
    # VIDEO
    # =========================

    elif "video" in msg:

        video_id = msg["video"]["file_id"]

        await tg_api(
            session,
            "sendVideo",
            chat_id=owner_id,
            video=video_id,
            caption=caption_text,
        )

    # =========================
    # DOCUMENT
    # =========================

    elif "document" in msg:

        doc_id = msg["document"]["file_id"]

        await tg_api(
            session,
            "sendDocument",
            chat_id=owner_id,
            document=doc_id,
            caption=caption_text,
        )

    # =========================
    # VOICE
    # =========================

    elif "voice" in msg:

        voice_id = msg["voice"]["file_id"]

        await tg_api(
            session,
            "sendVoice",
            chat_id=owner_id,
            voice=voice_id,
            caption=caption_text,
        )

    # =========================
    # VIDEO NOTE
    # =========================

    elif "video_note" in msg:

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=f"{header} (кружок):",
        )

        vn_id = msg["video_note"]["file_id"]

        await tg_api(
            session,
            "sendVideoNote",
            chat_id=owner_id,
            video_note=vn_id
        )

    # =========================
    # STICKER
    # =========================

    elif "sticker" in msg:

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=f"{header} (стікер):",
        )

        sticker_id = msg["sticker"]["file_id"]

        await tg_api(
            session,
            "sendSticker",
            chat_id=owner_id,
            sticker=sticker_id
        )

    # =========================
    # ANIMATION
    # =========================

    elif "animation" in msg:

        anim_id = msg["animation"]["file_id"]

        await tg_api(
            session,
            "sendAnimation",
            chat_id=owner_id,
            animation=anim_id,
            caption=caption_text,
        )

    # =========================
    # AUDIO
    # =========================

    elif "audio" in msg:

        audio_id = msg["audio"]["file_id"]

        await tg_api(
            session,
            "sendAudio",
            chat_id=owner_id,
            audio=audio_id,
            caption=caption_text,
        )

    # =========================
    # OTHER
    # =========================

    else:

        await tg_api(
            session,
            "copyMessage",
            chat_id=owner_id,
            from_chat_id=msg["chat"]["id"],
            message_id=msg["message_id"],
        )


# =========================
# PRIVATE MESSAGE
# =========================

async def handle_private_message(session, msg):

    global waiting_for_text
    global auto_responder_text

    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")

    # =========================
    # CHANGE AUTO RESPONSE
    # =========================

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
                "**Новий текст:**\n"
                f"{auto_responder_text}"
            ),
            parse_mode="Markdown",
            reply_markup=get_settings_keyboard(),
        )

        return

    # =========================
    # SETTINGS
    # =========================

    if text in [
        "/start",
        "/settings",
        "/seting"
    ]:

        waiting_for_text = False

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text="⚙️ **Меню керування автовідповідачем:**",
            parse_mode="Markdown",
            reply_markup=get_settings_keyboard(),
        )


# =========================
# CALLBACK QUERY
# =========================

async def handle_callback_query(session, cb):

    global auto_responder_enabled
    global waiting_for_text

    cb_id = cb["id"]

    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]

    data = cb.get("data")

    # =========================
    # TOGGLE AUTO RESPONDER
    # =========================

    if data == "toggle_ar":

        auto_responder_enabled = not auto_responder_enabled

        status_msg = (
            "увімкнено"
            if auto_responder_enabled
            else
            "вимкнено"
        )

        await tg_api(
            session,
            "answerCallbackQuery",
            callback_query_id=cb_id,
            text=f"Автовідповідач {status_msg}",
        )

        await tg_api(
            session,
            "editMessageText",
            chat_id=chat_id,
            message_id=msg_id,
            text="⚙️ **Меню керування автовідповідачем:**",
            parse_mode="Markdown",
            reply_markup=get_settings_keyboard(),
        )

    # =========================
    # EDIT AUTO RESPONSE
    # =========================

    elif data == "edit_ar_text":

        waiting_for_text = True

        await tg_api(
            session,
            "answerCallbackQuery",
            callback_query_id=cb_id
        )

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=(
                "будьласка напишить текст "
                "який будеть писати автовідповідач"
            ),
        )


# =========================
# BUSINESS MESSAGE
# =========================

async def handle_business_message(session, msg):

    conn_id = msg.get(
        "business_connection_id"
    )

    if not conn_id:
        return

    chat_id = msg["chat"]["id"]

    chat_type = msg.get(
        "chat",
        {}
    ).get(
        "type"
    )

    msg_id = msg["message_id"]

    sender_id = msg.get(
        "from",
        {}
    ).get(
        "id"
    )

    text = msg.get(
        "text",
        ""
    )

    reply_to = msg.get(
        "reply_to_message"
    )

    if chat_type != "private":
        return

    # =========================
    # BUSINESS CONNECTION
    # =========================

    conn_info = await tg_api(
        session,
        "getBusinessConnection",
        business_connection_id=conn_id
    )

    if not conn_info.get("ok"):
        return

    conn_data = conn_info.get(
        "result",
        {}
    )

    if not conn_data.get(
        "is_enabled"
    ):
        return

    owner_id = conn_data.get(
        "user_chat_id"
    )

    # =========================
    # MESSAGE FROM CLIENT
    # =========================

    if sender_id != owner_id:

        await send_media_to_owner(
            session,
            owner_id,
            msg
        )

        # =========================
        # AUTO RESPONDER
        # =========================

        if auto_responder_enabled:

            ar_res = await tg_api(
                session,
                "sendMessage",
                chat_id=chat_id,
                text=auto_responder_text,
                business_connection_id=conn_id,
                reply_to_message_id=msg_id,
            )

            if not ar_res.get("ok"):

                print(
                    "❌ ПОМИЛКА АВТОВІДПОВІДАЧА: "
                    f"{ar_res.get('description')}"
                )

            else:

                print(
                    "🤖 Автовідповідь успішно "
                    f"відправлена користувачу {sender_id}"
                )

        # =========================
        # MUTE
        # =========================

        if sender_id in muted_users:

            if sender_id not in deleted_messages_cache:
                deleted_messages_cache[sender_id] = []

            deleted_messages_cache[sender_id].append(
                get_msg_preview(msg)
            )

            await tg_api(
                session,
                "deleteMessage",
                chat_id=chat_id,
                message_id=msg_id,
                business_connection_id=conn_id,
            )

        return

    # =========================
    # OWNER COMMANDS
    # =========================

    if text.startswith("."):

        # =========================
        # MUTE
        # =========================

        if text == ".mute":

            if not reply_to:

                await tg_api(
                    session,
                    "editMessageText",
                    chat_id=chat_id,
                    message_id=msg_id,
                    text="❌ Відповой на повідомлення юзера!",
                    business_connection_id=conn_id,
                )

                return

            target_id = reply_to["from"]["id"]

            muted_users.add(target_id)

            await tg_api(
                session,
                "editMessageText",
                chat_id=chat_id,
                message_id=msg_id,
                text=(
                    f"🤐 Користувача `{target_id}` "
                    "зам'ючено."
                ),
                business_connection_id=conn_id,
            )

        # =========================
        # UNMUTE
        # =========================

        elif text in [".unmute", ".umute"]:

            if not reply_to:

                await tg_api(
                    session,
                    "editMessageText",
                    chat_id=chat_id,
                    message_id=msg_id,
                    text="❌ Відповой на повідомлення юзера!",
                    business_connection_id=conn_id,
                )

                return

            target_id = reply_to["from"]["id"]

            muted_users.discard(target_id)

            await tg_api(
                session,
                "editMessageText",
                chat_id=chat_id,
                message_id=msg_id,
                text=(
                    f"🔊 Користувача `{target_id}` "
                    "розм'ючено."
                ),
                business_connection_id=conn_id,
            )

        # =========================
        # NOMUTE
        # =========================

        elif text == ".nomute":

            if not reply_to:

                await tg_api(
                    session,
                    "editMessageText",
                    chat_id=chat_id,
                    message_id=msg_id,
                    text="❌ Відповой на повідомлення!",
                    business_connection_id=conn_id,
                )

                return

            target_id = reply_to["from"]["id"]

            msgs = deleted_messages_cache.get(
                target_id,
                []
            )

            if msgs:

                history = "\n".join(
                    [
                        f"• {m}"
                        for m in msgs
                    ]
                )

                await tg_api(
                    session,
                    "editMessageText",
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=(
                        "📥 **Відновлені повідомлення:**\n\n"
                        f"{history}"
                    ),
                    business_connection_id=conn_id,
                )

                deleted_messages_cache[target_id] = []

            else:

                await tg_api(
                    session,
                    "editMessageText",
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=(
                        "📭 Немає збережених "
                        "видалених повідомлень."
                    ),
                    business_connection_id=conn_id,
                )

        # =========================
        # SPAM
        # .spam текст кількість
        # =========================

        elif re.match(
            r"^\.spam\s+(.+)\s+(\d+)$",
            text
        ):

            spam_m = re.match(
                r"^\.spam\s+(.+)\s+(\d+)$",
                text
            )

            spam_text = spam_m.group(1)

            count = min(
                int(spam_m.group(2)),
                100
            )

            await tg_api(
                session,
                "deleteMessage",
                chat_id=chat_id,
                message_id=msg_id,
                business_connection_id=conn_id,
            )

            for _ in range(count):

                await tg_api(
                    session,
                    "sendMessage",
                    chat_id=chat_id,
                    text=spam_text,
                    business_connection_id=conn_id,
                )

                await asyncio.sleep(0.1)

        # =========================
        # V ANIMATION
        # =========================

        elif re.match(
            r"^\.v(\d*)\s+(.+)$",
            text,
            re.DOTALL
        ):

            anim_m = re.match(
                r"^\.v(\d*)\s+(.+)$",
                text,
                re.DOTALL
            )

            sec_str = anim_m.group(1)

            anim_text = anim_m.group(2)

            seconds = (
                int(sec_str)
                if sec_str
                else 10
            )

            max_spaces = 8

            frames = []

            for i in range(
                max_spaces + 1
            ):

                frames.append(
                    "\u00A0" * i
                    + anim_text
                )

            for i in range(
                max_spaces - 1,
                0,
                -1
            ):

                frames.append(
                    "\u00A0" * i
                    + anim_text
                )

            delay = max(
                1.0,
                seconds / len(frames)
            )

            end_time = (
                asyncio.get_event_loop().time()
                + seconds
            )

            idx = 0

            while (
                asyncio.get_event_loop().time()
                < end_time
            ):

                frame = frames[
                    idx % len(frames)
                ]

                idx += 1

                res = await tg_api(
                    session,
                    "editMessageText",
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=frame,
                    business_connection_id=conn_id,
                )

                if not res.get("ok"):

                    err_desc = res.get(
                        "description",
                        ""
                    )

                    if (
                        "BUSINESS_PEER_INVALID"
                        in err_desc
                        or
                        "message is not modified"
                        in err_desc
                    ):
                        break

                    await asyncio.sleep(1.5)

                else:

                    await asyncio.sleep(
                        delay
                    )


# =========================
# TELEGRAM POLLING
# =========================

async def telegram_polling():

    offset = 0

    timeout = aiohttp.ClientTimeout(
        total=35
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        await tg_api(
            session,
            "deleteWebhook",
            drop_pending_updates=True
        )

        print(
            "================================"
        )

        print(
            "Telegram бот запущений!"
        )

        print(
            "Очікування повідомлень..."
        )

        print(
            "================================"
        )

        while True:

            try:

                res = await tg_api(
                    session,
                    "getUpdates",
                    offset=offset,
                    timeout=30
                )

                if not res.get("ok"):

                    await asyncio.sleep(3)

                    continue

                for update in res.get(
                    "result",
                    []
                ):

                    offset = (
                        update["update_id"]
                        + 1
                    )

                    if "message" in update:

                        await handle_private_message(
                            session,
                            update["message"]
                        )

                    elif "business_message" in update:

                        await handle_business_message(
                            session,
                            update["business_message"]
                        )

                    elif "callback_query" in update:

                        await handle_callback_query(
                            session,
                            update["callback_query"]
                        )

            except Exception as e:

                print(
                    f"Тимчасова помилка мережі: {e}"
                )

                await asyncio.sleep(3)


# =========================
# MAIN
# =========================

async def main():

    await asyncio.gather(
        telegram_polling(),
        start_web_server()
    )


# =========================
# START
# =========================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "Бот зупинений."
        )