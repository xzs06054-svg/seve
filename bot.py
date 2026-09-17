import asyncio
import logging
import os
import re
import secrets

import aiohttp
from aiohttp import web
from dotenv import load_dotenv


# ============================================================
# НАЛАШТУВАННЯ
# ============================================================

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not TOKEN:
    print("================================================")
    print("ПОМИЛКА: BOT_TOKEN НЕ ЗНАЙДЕНО")
    print("На Render додай BOT_TOKEN у Environment.")
    print("================================================")


API_URL = ""

if TOKEN:
    API_URL = "https://api.telegram.org/bot" + TOKEN


# Render автоматично дає ці змінні
PORT = int(os.environ.get("PORT", "10000"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip()

IS_RENDER = bool(
    os.environ.get("RENDER")
    or RENDER_EXTERNAL_URL
)


# Секрет для Telegram webhook
WEBHOOK_SECRET = os.environ.get(
    "WEBHOOK_SECRET",
    secrets.token_urlsafe(32)
)


# ============================================================
# СТАН БОТА
# ============================================================

muted_users = set()

deleted_messages_cache = {}

auto_responder_enabled = True

auto_responder_text = (
    "привіт це мій авто відповідач\n"
    "я прийду в найближчий час\n"
    "бульдласка без спаму"
)

waiting_for_text = False

last_update_id = 0

telegram_ready = False

http_ready = False


# ============================================================
# TELEGRAM API
# ============================================================

async def tg_api(session, method, **kwargs):
    if not API_URL:
        return {
            "ok": False,
            "description": "BOT_TOKEN не встановлений"
        }

    url = API_URL + "/" + method

    try:
        async with session.post(
            url,
            json=kwargs
        ) as resp:

            text = await resp.text()

            try:
                data = await resp.json()
            except Exception:
                return {
                    "ok": False,
                    "description": (
                        "Telegram повернув неправильний JSON: "
                        + text[:500]
                    )
                }

            if resp.status != 200:
                print(
                    "Telegram HTTP ERROR:",
                    resp.status,
                    data
                )

            return data

    except asyncio.CancelledError:
        raise

    except Exception as e:
        print(
            "Telegram API ERROR:",
            method,
            str(e)
        )

        return {
            "ok": False,
            "description": str(e)
        }


# ============================================================
# SETTINGS
# ============================================================

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


# ============================================================
# HELP
# ============================================================

def get_help_text():

    return (
        "📚 КОМАНДИ БОТА\n\n"

        "/start — головне меню\n"
        "/seting — налаштування\n"
        "/settings — налаштування\n"
        "/help — список команд\n\n"

        "👤 КЕРУВАННЯ КОРИСТУВАЧАМИ\n\n"

        ".mute — зам'ютити користувача\n"
        "Використовуй відповіддю на його повідомлення.\n\n"

        ".umute — розм'ютити користувача\n"
        "Використовуй відповіддю на його повідомлення.\n\n"

        ".unmute — те саме, що .umute\n\n"

        ".nomute — показати збережені повідомлення зам'юченого\n"
        "користувача.\n\n"

        "📨 СПАМ\n\n"

        ".spam текст кількість\n"
        "Наприклад:\n"
        ".spam привіт 5\n\n"

        "🎬 АНІМАЦІЯ\n\n"

        ".v текст\n"
        "або\n"
        ".v20 текст\n\n"

        ".v20 означає анімацію протягом 20 секунд."
    )


# ============================================================
# MESSAGE PREVIEW
# ============================================================

def get_msg_preview(msg):

    if "text" in msg:
        return msg["text"]

    if "photo" in msg:
        return (
            "[Фото] "
            + msg.get("caption", "")
        ).strip()

    if "video" in msg:
        return (
            "[Відео] "
            + msg.get("caption", "")
        ).strip()

    if "video_note" in msg:
        return "[Кружок / Відеоповідомлення]"

    if "voice" in msg:
        return "[Голосове повідомлення]"

    if "document" in msg:
        return (
            "[Файл: "
            + msg["document"].get(
                "file_name",
                "документ"
            )
            + "]"
        )

    if "sticker" in msg:
        emoji = msg["sticker"].get(
            "emoji",
            ""
        )

        return (
            "[Наліпка "
            + emoji
            + "]"
        ).strip()

    if "animation" in msg:
        return "[GIF / Анімація]"

    if "audio" in msg:
        return (
            "[Аудіо] "
            + msg.get("caption", "")
        ).strip()

    return "[Медіаповідомлення]"


# ============================================================
# ВІДПРАВКА МЕДІА ВЛАСНИКУ
# ============================================================

async def send_media_to_owner(
    session,
    owner_id,
    msg
):

    sender = msg.get(
        "from",
        {}
    )

    sender_name = sender.get(
        "first_name",
        "Клієнт"
    )

    sender_username = sender.get(
        "username"
    )

    if sender_username:

        user_info = (
            "@"
            + sender_username
        )

    else:

        user_info = (
            "ID: "
            + str(sender.get("id"))
        )

    header = (
        "📥 Нове повідомлення від "
        + sender_name
        + " ("
        + user_info
        + "):"
    )

    user_caption = msg.get(
        "caption",
        ""
    )

    if user_caption:

        caption_text = (
            header
            + "\n\n"
            + user_caption
        )

    else:

        caption_text = header


    # TEXT
    if (
        "text" in msg
        and not any(
            key in msg
            for key in [
                "photo",
                "video",
                "document",
                "voice",
                "video_note",
                "sticker",
                "audio",
                "animation"
            ]
        )
    ):

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=(
                header
                + "\n\n"
                + msg["text"]
            )
        )

        return


    # PHOTO
    if "photo" in msg:

        photo_id = msg["photo"][-1]["file_id"]

        await tg_api(
            session,
            "sendPhoto",
            chat_id=owner_id,
            photo=photo_id,
            caption=caption_text
        )

        return


    # VIDEO
    if "video" in msg:

        video_id = msg["video"]["file_id"]

        await tg_api(
            session,
            "sendVideo",
            chat_id=owner_id,
            video=video_id,
            caption=caption_text
        )

        return


    # DOCUMENT
    if "document" in msg:

        document_id = msg["document"]["file_id"]

        await tg_api(
            session,
            "sendDocument",
            chat_id=owner_id,
            document=document_id,
            caption=caption_text
        )

        return


    # VOICE
    if "voice" in msg:

        voice_id = msg["voice"]["file_id"]

        await tg_api(
            session,
            "sendVoice",
            chat_id=owner_id,
            voice=voice_id,
            caption=caption_text
        )

        return


    # VIDEO NOTE
    if "video_note" in msg:

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=header + "\n\n[Кружок]"
        )

        await tg_api(
            session,
            "sendVideoNote",
            chat_id=owner_id,
            video_note=msg["video_note"]["file_id"]
        )

        return


    # STICKER
    if "sticker" in msg:

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=header + "\n\n[Стікер]"
        )

        await tg_api(
            session,
            "sendSticker",
            chat_id=owner_id,
            sticker=msg["sticker"]["file_id"]
        )

        return


    # ANIMATION / GIF
    if "animation" in msg:

        await tg_api(
            session,
            "sendAnimation",
            chat_id=owner_id,
            animation=msg["animation"]["file_id"],
            caption=caption_text
        )

        return


    # AUDIO
    if "audio" in msg:

        await tg_api(
            session,
            "sendAudio",
            chat_id=owner_id,
            audio=msg["audio"]["file_id"],
            caption=caption_text
        )

        return


    # FALLBACK
    if (
        "chat" in msg
        and "message_id" in msg
    ):

        await tg_api(
            session,
            "copyMessage",
            chat_id=owner_id,
            from_chat_id=msg["chat"]["id"],
            message_id=msg["message_id"]
        )


# ============================================================
# PRIVATE MESSAGE
# ============================================================

async def handle_private_message(
    session,
    msg
):

    global waiting_for_text
    global auto_responder_text

    chat = msg.get(
        "chat",
        {}
    )

    chat_id = chat.get("id")

    if not chat_id:
        return

    text = msg.get(
        "text",
        ""
    )


    # Очікуємо новий текст автовідповідача
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
                "Новий текст:\n"
                + auto_responder_text
            ),
            reply_markup=get_settings_keyboard()
        )

        return


    # START / SETTINGS
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
            text=(
                "⚙️ Меню керування автовідповідачем:"
            ),
            reply_markup=get_settings_keyboard()
        )

        return


    # HELP
    if text == "/help":

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=get_help_text()
        )

        return


# ============================================================
# CALLBACKS
# ============================================================

async def handle_callback_query(
    session,
    callback
):

    global auto_responder_enabled
    global waiting_for_text

    callback_id = callback.get(
        "id"
    )

    message = callback.get(
        "message"
    )

    if not message:
        return

    chat_id = message["chat"]["id"]

    message_id = message["message_id"]

    data = callback.get(
        "data"
    )


    if data == "toggle_ar":

        auto_responder_enabled = (
            not auto_responder_enabled
        )

        if auto_responder_enabled:

            status = "увімкнено"

        else:

            status = "вимкнено"


        await tg_api(
            session,
            "answerCallbackQuery",
            callback_query_id=callback_id,
            text=(
                "Автовідповідач "
                + status
            )
        )


        await tg_api(
            session,
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=(
                "⚙️ Меню керування автовідповідачем:"
            ),
            reply_markup=get_settings_keyboard()
        )

        return


    if data == "edit_ar_text":

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
                "відправляти автовідповідач."
            )
        )

        return


# ============================================================
# ПОШУК КОРИСТУВАЧА ДЛЯ REPLY-КОМАНД
# ============================================================

def get_reply_user_id(msg):

    reply = msg.get(
        "reply_to_message"
    )

    if not reply:
        return None

    sender = reply.get(
        "from",
        {}
    )

    return sender.get(
        "id"
    )


# ============================================================
# BUSINESS MESSAGE
# ============================================================

async def handle_business_message(
    session,
    msg
):

    conn_id = msg.get(
        "business_connection_id"
    )

    if not conn_id:
        return


    chat = msg.get(
        "chat",
        {}
    )

    chat_id = chat.get(
        "id"
    )

    if not chat_id:
        return


    if chat.get("type") != "private":
        return


    msg_id = msg.get(
        "message_id"
    )

    if not msg_id:
        return


    sender = msg.get(
        "from",
        {}
    )

    sender_id = sender.get(
        "id"
    )

    text = msg.get(
        "text",
        ""
    )


    # Отримуємо інформацію Business connection
    conn_info = await tg_api(
        session,
        "getBusinessConnection",
        business_connection_id=conn_id
    )

    if not conn_info.get("ok"):

        print(
            "BUSINESS CONNECTION ERROR:",
            conn_info.get("description")
        )

        return


    conn_data = conn_info.get(
        "result",
        {}
    )

    if not conn_data.get(
        "is_enabled",
        False
    ):
        return


    owner_id = conn_data.get(
        "user_chat_id"
    )

    if not owner_id:
        return


    # ========================================================
    # ПОВІДОМЛЕННЯ КЛІЄНТА
    # ========================================================

    if sender_id != owner_id:

        # Надсилаємо копію власнику
        await send_media_to_owner(
            session,
            owner_id,
            msg
        )


        # Автовідповідач
        if auto_responder_enabled:

            result = await tg_api(
                session,
                "sendMessage",
                chat_id=chat_id,
                text=auto_responder_text,
                business_connection_id=conn_id,
                reply_parameters={
                    "message_id": msg_id
                }
            )

            if not result.get("ok"):

                # Сумісність зі старим способом
                result = await tg_api(
                    session,
                    "sendMessage",
                    chat_id=chat_id,
                    text=auto_responder_text,
                    business_connection_id=conn_id,
                    reply_to_message_id=msg_id
                )


            if not result.get("ok"):

                print(
                    "❌ АВТОВІДПОВІДЬ:",
                    result.get("description")
                )


        # Якщо користувач зам'ючений
        if sender_id in muted_users:

            if sender_id not in deleted_messages_cache:

                deleted_messages_cache[
                    sender_id
                ] = []


            deleted_messages_cache[
                sender_id
            ].append(
                get_msg_preview(msg)
            )


            # Обмеження кешу
            if len(
                deleted_messages_cache[sender_id]
            ) > 100:

                deleted_messages_cache[
                    sender_id
                ] = deleted_messages_cache[
                    sender_id
                ][-100:]


            result = await tg_api(
                session,
                "deleteMessage",
                chat_id=chat_id,
                message_id=msg_id,
                business_connection_id=conn_id
            )

            if not result.get("ok"):

                print(
                    "❌ DELETE:",
                    result.get("description")
                )


        return


    # ========================================================
    # КОМАНДИ ВЛАСНИКА
    # ========================================================

    if not text.startswith("."):
        return


    # --------------------------------------------------------
    # .mute
    # --------------------------------------------------------

    if text == ".mute":

        target_id = get_reply_user_id(msg)

        if not target_id:

            await tg_api(
                session,
                "editMessageText",
                chat_id=chat_id,
                message_id=msg_id,
                text=(
                    "❌ Відповідай на повідомлення юзера!"
                ),
                business_connection_id=conn_id
            )

            return


        muted_users.add(
            target_id
        )


        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=msg_id,
            business_connection_id=conn_id
        )


        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text="мют активовано",
            business_connection_id=conn_id
        )

        return


    # --------------------------------------------------------
    # .umute
    # .unmute
    # --------------------------------------------------------

    if text in [
        ".umute",
        ".unmute"
    ]:

        target_id = get_reply_user_id(msg)

        if not target_id:

            await tg_api(
                session,
                "editMessageText",
                chat_id=chat_id,
                message_id=msg_id,
                text=(
                    "❌ Відповідай на повідомлення юзера!"
                ),
                business_connection_id=conn_id
            )

            return


        muted_users.discard(
            target_id
        )


        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=msg_id,
            business_connection_id=conn_id
        )


        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=(
                "ви розмючені можете писать"
            ),
            business_connection_id=conn_id
        )

        return


    # --------------------------------------------------------
    # .nomute
    # --------------------------------------------------------

    if text == ".nomute":

        target_id = get_reply_user_id(msg)

        if not target_id:

            await tg_api(
                session,
                "editMessageText",
                chat_id=chat_id,
                message_id=msg_id,
                text=(
                    "❌ Відповідай на повідомлення!"
                ),
                business_connection_id=conn_id
            )

            return


        messages = deleted_messages_cache.get(
            target_id,
            []
        )


        if not messages:

            await tg_api(
                session,
                "editMessageText",
                chat_id=chat_id,
                message_id=msg_id,
                text=(
                    "📭 Немає збережених "
                    "видалених повідомлень."
                ),
                business_connection_id=conn_id
            )

            return


        history = "\n".join(
            "• " + item
            for item in messages
        )


        if len(history) > 3900:

            history = history[-3900:]


        await tg_api(
            session,
            "editMessageText",
            chat_id=chat_id,
            message_id=msg_id,
            text=(
                "📥 Відновлені повідомлення:\n\n"
                + history
            ),
            business_connection_id=conn_id
        )


        deleted_messages_cache[
            target_id
        ] = []

        return


    # --------------------------------------------------------
    # .spam текст кількість
    # --------------------------------------------------------

    spam_match = re.match(
        r"^\.spam\s+(.+)\s+(\d+)$",
        text,
        re.DOTALL
    )

    if spam_match:

        spam_text = spam_match.group(1)

        try:

            count = int(
                spam_match.group(2)
            )

        except Exception:

            count = 1


        # Захист від величезної кількості
        count = max(
            1,
            min(
                count,
                100
            )
        )


        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=msg_id,
            business_connection_id=conn_id
        )


        for i in range(count):

            result = await tg_api(
                session,
                "sendMessage",
                chat_id=chat_id,
                text=spam_text,
                business_connection_id=conn_id
            )

            if not result.get("ok"):

                print(
                    "❌ SPAM:",
                    result.get("description")
                )

                break


            # Не забиваємо Telegram API
            await asyncio.sleep(0.15)


        return


    # --------------------------------------------------------
    # .v / .v20 / .v60
    # --------------------------------------------------------

    animation_match = re.match(
        r"^\.v(\d*)\s+(.+)$",
        text,
        re.DOTALL
    )

    if animation_match:

        seconds_text = animation_match.group(1)

        animation_text = animation_match.group(2)


        if seconds_text:

            try:

                seconds = int(
                    seconds_text
                )

            except Exception:

                seconds = 10

        else:

            seconds = 10


        # Нормальний діапазон
        seconds = max(
            1,
            min(
                seconds,
                300
            )
        )


        # Видаляємо оригінальну команду
        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=msg_id,
            business_connection_id=conn_id
        )


        # Створюємо повідомлення,
        # яке потім редагуватимемо
        first = await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=animation_text,
            business_connection_id=conn_id
        )


        if not first.get("ok"):

            print(
                "❌ V COMMAND:",
                first.get("description")
            )

            return


        animation_message_id = (
            first
            .get("result", {})
            .get("message_id")
        )


        if not animation_message_id:
            return


        # Кадри
        frames = []

        max_spaces = 8

        for i in range(
            max_spaces + 1
        ):

            frames.append(
                ("\u00A0" * i)
                + animation_text
            )


        for i in range(
            max_spaces - 1,
            0,
            -1
        ):

            frames.append(
                ("\u00A0" * i)
                + animation_text
            )


        if not frames:
            return


        # Не більше ~2 API редагувань/сек
        delay = max(
            0.5,
            float(seconds)
            / float(len(frames))
        )


        start_time = (
            asyncio.get_event_loop().time()
        )


        index = 0


        while (
            asyncio.get_event_loop().time()
            - start_time
            < seconds
        ):

            frame = frames[
                index % len(frames)
            ]

            index += 1


            result = await tg_api(
                session,
                "editMessageText",
                chat_id=chat_id,
                message_id=animation_message_id,
                text=frame,
                business_connection_id=conn_id
            )


            if not result.get("ok"):

                description = result.get(
                    "description",
                    ""
                )


                if (
                    "message is not modified"
                    in description.lower()
                ):

                    await asyncio.sleep(
                        delay
                    )

                    continue


                if (
                    "message to edit not found"
                    in description.lower()
                ):

                    break


                if (
                    "business" in description.lower()
                    and "invalid" in description.lower()
                ):

                    break


                print(
                    "❌ V EDIT:",
                    description
                )


            await asyncio.sleep(
                delay
            )


        return


# ============================================================
# UPDATE ROUTER
# ============================================================

async def process_update(
    session,
    update
):

    global last_update_id


    update_id = update.get(
        "update_id"
    )


    if update_id is not None:

        # Захист від дублювання webhook
        if update_id <= last_update_id:

            return


        last_update_id = update_id


    try:

        if "message" in update:

            await handle_private_message(
                session,
                update["message"]
            )

            return


        if "business_message" in update:

            await handle_business_message(
                session,
                update["business_message"]
            )

            return


        if "callback_query" in update:

            await handle_callback_query(
                session,
                update["callback_query"]
            )

            return


    except Exception as e:

        print(
            "UPDATE ERROR:",
            repr(e)
        )


# ============================================================
# HTTP SERVER
# ============================================================

async def health(request):

    return web.json_response(
        {
            "status": "ok",
            "service": "seve bot",
            "telegram_ready": telegram_ready,
            "render": IS_RENDER
        }
    )


async def root(request):

    return web.Response(
        text=(
            "SEVE BOT is running!\n"
            "Telegram: "
            + (
                "READY"
                if telegram_ready
                else "NOT READY"
            )
        )
    )


async def telegram_webhook(request):

    global last_update_id

    # Перевірка секрету
    received_secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token",
        ""
    )

    if received_secret != WEBHOOK_SECRET:

        return web.Response(
            status=403,
            text="Forbidden"
        )


    try:

        update = await request.json()

    except Exception:

        return web.Response(
            status=400,
            text="Bad JSON"
        )


    # Повертаємо 200 максимально швидко.
    # Обробку запускаємо окремо.
    session = request.app["telegram_session"]

    asyncio.create_task(
        process_update(
            session,
            update
        )
    )


    return web.Response(
        status=200,
        text="OK"
    )


# ============================================================
# WEB SERVER START
# ============================================================

async def start_http_server():

    global http_ready

    app = web.Application()

    app["telegram_session"] = None

    app.router.add_get(
        "/",
        root
    )

    app.router.add_get(
        "/health",
        health
    )

    app.router.add_post(
        "/telegram/webhook/" + WEBHOOK_SECRET,
        telegram_webhook
    )


    runner = web.AppRunner(
        app
    )

    await runner.setup()


    # КЛЮЧОВЕ ДЛЯ RENDER:
    # 0.0.0.0 + PORT
    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )


    try:

        await site.start()

    except Exception as e:

        print("================================================")
        print("❌ НЕ ВДАЛОСЯ ВІДКРИТИ PORT")
        print("PORT =", PORT)
        print("ERROR =", repr(e))
        print("================================================")

        raise


    http_ready = True


    print("================================================")
    print("HTTP SERVER ЗАПУЩЕНИЙ")
    print("HOST: 0.0.0.0")
    print("PORT:", PORT)
    print("RENDER:", IS_RENDER)

    if RENDER_EXTERNAL_URL:

        print(
            "URL:",
            RENDER_EXTERNAL_URL
        )

    print("================================================")


    return runner


# ============================================================
# WEBHOOK SETUP
# ============================================================

async def setup_webhook(
    session
):

    global telegram_ready


    if not TOKEN:

        print(
            "BOT_TOKEN відсутній."
        )

        return False


    # Якщо Render
    if IS_RENDER:

        if not RENDER_EXTERNAL_URL:

            print(
                "❌ RENDER_EXTERNAL_URL відсутній."
            )

            return False


        webhook_url = (
            RENDER_EXTERNAL_URL.rstrip("/")
            + "/telegram/webhook/"
            + WEBHOOK_SECRET
        )


        print(
            "Встановлюємо Telegram webhook:"
        )

        print(
            webhook_url
        )


        result = await tg_api(
            session,
            "setWebhook",
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=[]
        )


        if not result.get("ok"):

            print(
                "❌ WEBHOOK ERROR:",
                result.get("description")
            )

            return False


        print(
            "✅ Telegram webhook встановлено."
        )


        info = await tg_api(
            session,
            "getWebhookInfo"
        )


        if info.get("ok"):

            webhook_info = info.get(
                "result",
                {}
            )

            print(
                "Webhook URL:",
                webhook_info.get("url")
            )

            print(
                "Pending updates:",
                webhook_info.get(
                    "pending_update_count",
                    0
                )
            )


        telegram_ready = True

        return True


    # ========================================================
    # ЛОКАЛЬНО:
    # polling
    # ========================================================

    await tg_api(
        session,
        "deleteWebhook",
        drop_pending_updates=True
    )


    telegram_ready = True

    print(
        "Локальний режим: Telegram polling."
    )

    return True


# ============================================================
# LOCAL POLLING
# ============================================================

async def local_polling(
    session
):

    global last_update_id


    print(
        "Очікування Telegram повідомлень..."
    )


    offset = 0


    while True:

        try:

            result = await tg_api(
                session,
                "getUpdates",
                offset=offset,
                timeout=25,
                allowed_updates=[]
            )


            if not result.get("ok"):

                print(
                    "getUpdates ERROR:",
                    result.get("description")
                )

                await asyncio.sleep(3)

                continue


            updates = result.get(
                "result",
                []
            )


            for update in updates:

                update_id = update.get(
                    "update_id"
                )


                if update_id is not None:

                    offset = update_id + 1


                await process_update(
                    session,
                    update
                )


        except asyncio.CancelledError:

            raise


        except Exception as e:

            print(
                "Polling ERROR:",
                repr(e)
            )

            await asyncio.sleep(3)


# ============================================================
# TELEGRAM INITIALIZATION
# ============================================================

async def telegram_start(
    session
):

    global telegram_ready


    if not TOKEN:

        print(
            "================================================"
        )

        print(
            "BOT_TOKEN НЕ ВСТАНОВЛЕНИЙ."
        )

        print(
            "Бот не може підключитися до Telegram."
        )

        print(
            "================================================"
        )

        return


    # Перевіряємо токен
    me = await tg_api(
        session,
        "getMe"
    )


    if not me.get("ok"):

        print(
            "================================================"
        )

        print(
            "❌ TELEGRAM TOKEN НЕ ПРАЦЮЄ"
        )

        print(
            me.get("description")
        )

        print(
            "================================================"
        )

        return


    bot_info = me.get(
        "result",
        {}
    )


    print(
        "Telegram bot:",
        bot_info.get("username")
    )

    print(
        "Telegram ID:",
        bot_info.get("id")
    )


    # Webhook / polling
    if IS_RENDER:

        success = await setup_webhook(
            session
        )

        if not success:

            print(
                "❌ Webhook не встановлено."
            )

            return


        print(
            "================================================"
        )

        print(
            "TELEGRAM WEBHOOK READY"
        )

        print(
            "Бот готовий приймати повідомлення."
        )

        print(
            "================================================"
        )

        # Тут нічого не polling.
        # HTTP сервер приймає Telegram updates.
        while True:

            await asyncio.sleep(
                3600
            )


    else:

        success = await setup_webhook(
            session
        )

        if not success:

            return


        await local_polling(
            session
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    global telegram_ready


    timeout = aiohttp.ClientTimeout(
        total=40,
        connect=15,
        sock_read=40
    )


    connector = aiohttp.TCPConnector(
        limit=50,
        ttl_dns_cache=300
    )


    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector
    ) as session:


        # ====================================================
        # СПОЧАТКУ ВІДКРИВАЄМО PORT
        # ====================================================

        runner = await start_http_server()


        # Передаємо Telegram session у HTTP app
        # через route app object
        for route in runner.app.router.routes():

            pass


        # aiohttp app
        runner.app["telegram_session"] = session


        # ====================================================
        # ПОТІМ TELEGRAM
        # ====================================================

        try:

            await telegram_start(
                session
            )

        except asyncio.CancelledError:

            raise

        except Exception as e:

            print(
                "================================================"
            )

            print(
                "❌ TELEGRAM START ERROR"
            )

            print(
                repr(e)
            )

            print(
                "HTTP сервер при цьому продовжує працювати."
            )

            print(
                "================================================"
            )


        # ====================================================
        # Якщо telegram_start завершився,
        # HTTP все одно має жити.
        # ====================================================

        while True:

            await asyncio.sleep(
                3600
            )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    print("")
    print("==============================================")
    print("SEVE BOT")
    print("Запуск...")
    print("==============================================")
    print("PORT =", PORT)
    print("RENDER =", IS_RENDER)
    print("==============================================")
    print("")


    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "Бот зупинений."
        )

    except Exception as e:

        print(
            "================================================"
        )

        print(
            "КРИТИЧНА ПОМИЛКА:"
        )

        print(
            repr(e)
        )

        print(
            "================================================"
        )

        raise