import asyncio
import logging
import os
import re

import aiohttp
from aiohttp import web
from dotenv import load_dotenv


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

load_dotenv()


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not TOKEN:
    print("==================================================")
    print("ERROR: BOT_TOKEN НЕ ЗНАЙДЕНО")
    print("Додай BOT_TOKEN у Render -> Environment.")
    print("==================================================")
    raise SystemExit(1)


API_URL = "https://api.telegram.org/bot" + TOKEN


# Render сам встановлює PORT
try:
    PORT = int(os.environ.get("PORT", "10000"))
except Exception:
    PORT = 10000


RENDER_EXTERNAL_URL = os.environ.get(
    "RENDER_EXTERNAL_URL",
    ""
).strip()


IS_RENDER = bool(
    os.environ.get("RENDER")
    or RENDER_EXTERNAL_URL
)


# Секрет webhook
WEBHOOK_SECRET = os.environ.get(
    "WEBHOOK_SECRET",
    "seve_bot_webhook_secret"
).strip()


# ============================================================
# BOT STATE
# ============================================================

muted_users = set()

deleted_messages_cache = {}

auto_responder_enabled = True

auto_responder_text = (
    "привіт це мій авто відповідач\n"
    "я прийду в найближчий час\n"
    "будьласка без спаму"
)

waiting_for_text = False


# ============================================================
# BUSINESS CONNECTION CACHE
# ============================================================

business_connections = {}


# ============================================================
# TELEGRAM API
# ============================================================

async def tg_api(session, method, **kwargs):

    url = API_URL + "/" + method

    try:

        async with session.post(
            url,
            json=kwargs
        ) as response:

            raw_text = await response.text()

            try:
                data = await response.json()
            except Exception:

                return {
                    "ok": False,
                    "description": (
                        "Telegram returned invalid JSON: "
                        + raw_text[:500]
                    )
                }


            if response.status != 200:

                print(
                    "TELEGRAM HTTP ERROR:",
                    method,
                    response.status,
                    data
                )


            return data


    except asyncio.CancelledError:

        raise


    except Exception as e:

        print(
            "TELEGRAM NETWORK ERROR:",
            method,
            repr(e)
        )

        return {
            "ok": False,
            "description": str(e)
        }


# ============================================================
# SETTINGS KEYBOARD
# ============================================================

def get_settings_keyboard():

    if auto_responder_enabled:

        status = "🟢 Увімкнено"

    else:

        status = "🔴 Вимкнено"


    return {
        "inline_keyboard": [
            [
                {
                    "text": (
                        "Автовідповідач: "
                        + status
                    ),
                    "callback_data": "toggle_ar"
                }
            ],
            [
                {
                    "text": "⚙️ Змінити текст",
                    "callback_data": "edit_ar_text"
                }
            ],
            [
                {
                    "text": "📋 Допомога",
                    "callback_data": "show_help"
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
        "/help — допомога\n\n"

        "👤 КЕРУВАННЯ КОРИСТУВАЧАМИ\n\n"

        ".mute — зам'ютити користувача\n"
        "Відповідай цією командою на його повідомлення.\n\n"

        ".umute — розм'ютити користувача\n"
        "Відповідай цією командою на його повідомлення.\n\n"

        ".unmute — те саме, що .umute\n\n"

        ".nomute — показати збережені повідомлення зам'юченого\n"
        "користувача.\n\n"

        "📨 СПАМ\n\n"

        ".spam текст кількість\n"
        "Наприклад:\n"
        ".spam привіт 5\n\n"

        "🎬 АНІМАЦІЯ\n\n"

        ".v текст\n"
        ".v20 текст\n\n"

        ".v20 редагує одне й те саме повідомлення приблизно 20 секунд."
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
# SEND MEDIA TO OWNER
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
            + str(
                sender.get(
                    "id",
                    "unknown"
                )
            )
        )


    header = (
        "📥 Нове повідомлення від "
        + sender_name
        + " ("
        + user_info
        + "):"
    )


    caption = msg.get(
        "caption",
        ""
    )


    if caption:

        caption_text = (
            header
            + "\n\n"
            + caption
        )

    else:

        caption_text = header


    # TEXT
    if (
        "text" in msg
        and "photo" not in msg
        and "video" not in msg
        and "document" not in msg
        and "voice" not in msg
        and "video_note" not in msg
        and "sticker" not in msg
        and "audio" not in msg
        and "animation" not in msg
    ):

        result = await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=(
                header
                + "\n\n"
                + msg["text"]
            )
        )

        return result


    # PHOTO
    if "photo" in msg:

        file_id = msg["photo"][-1]["file_id"]

        return await tg_api(
            session,
            "sendPhoto",
            chat_id=owner_id,
            photo=file_id,
            caption=caption_text
        )


    # VIDEO
    if "video" in msg:

        file_id = msg["video"]["file_id"]

        return await tg_api(
            session,
            "sendVideo",
            chat_id=owner_id,
            video=file_id,
            caption=caption_text
        )


    # DOCUMENT
    if "document" in msg:

        file_id = msg["document"]["file_id"]

        return await tg_api(
            session,
            "sendDocument",
            chat_id=owner_id,
            document=file_id,
            caption=caption_text
        )


    # VOICE
    if "voice" in msg:

        file_id = msg["voice"]["file_id"]

        return await tg_api(
            session,
            "sendVoice",
            chat_id=owner_id,
            voice=file_id,
            caption=caption_text
        )


    # VIDEO NOTE
    if "video_note" in msg:

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=header
        )

        return await tg_api(
            session,
            "sendVideoNote",
            chat_id=owner_id,
            video_note=msg["video_note"]["file_id"]
        )


    # STICKER
    if "sticker" in msg:

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=header
        )

        return await tg_api(
            session,
            "sendSticker",
            chat_id=owner_id,
            sticker=msg["sticker"]["file_id"]
        )


    # ANIMATION
    if "animation" in msg:

        return await tg_api(
            session,
            "sendAnimation",
            chat_id=owner_id,
            animation=msg["animation"]["file_id"],
            caption=caption_text
        )


    # AUDIO
    if "audio" in msg:

        return await tg_api(
            session,
            "sendAudio",
            chat_id=owner_id,
            audio=msg["audio"]["file_id"],
            caption=caption_text
        )


    return await tg_api(
        session,
        "copyMessage",
        chat_id=owner_id,
        from_chat_id=msg["chat"]["id"],
        message_id=msg["message_id"]
    )


# ============================================================
# PRIVATE BOT MESSAGE
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


    chat_id = chat.get(
        "id"
    )


    if not chat_id:
        return


    text = msg.get(
        "text",
        ""
    )


    # --------------------------------------------------------
    # SAVE AUTO RESPONSE TEXT
    # --------------------------------------------------------

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
            reply_markup=get_settings_keyboard()
        )

        return


    # --------------------------------------------------------
    # START / SETTINGS
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # HELP
    # --------------------------------------------------------

    if text == "/help":

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=get_help_text()
        )

        return


# ============================================================
# CALLBACK QUERY
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


    chat = message.get(
        "chat",
        {}
    )


    chat_id = chat.get(
        "id"
    )


    message_id = message.get(
        "message_id"
    )


    data = callback.get(
        "data",
        ""
    )


    # TOGGLE
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


    # CHANGE TEXT
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
                "Напиши новий текст "
                "автовідповідача."
            )
        )

        return


    # HELP
    if data == "show_help":

        await tg_api(
            session,
            "answerCallbackQuery",
            callback_query_id=callback_id
        )


        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=get_help_text()
        )

        return


# ============================================================
# GET BUSINESS CONNECTION
# ============================================================

async def get_business_connection(
    session,
    connection_id
):

    # Спочатку пробуємо кеш
    cached = business_connections.get(
        connection_id
    )


    if cached:

        return cached


    result = await tg_api(
        session,
        "getBusinessConnection",
        business_connection_id=connection_id
    )


    if not result.get("ok"):

        print(
            "❌ getBusinessConnection ERROR:"
        )

        print(
            result.get(
                "description"
            )
        )

        return None


    connection = result.get(
        "result"
    )


    if not connection:

        return None


    business_connections[
        connection_id
    ] = connection


    return connection


# ============================================================
# PRINT BUSINESS RIGHTS
# ============================================================

def print_business_rights(
    connection
):

    rights = connection.get(
        "rights",
        {}
    )


    print("")
    print("==============================================")
    print("BUSINESS CONNECTION")
    print("==============================================")
    print(
        "ID:",
        connection.get("id")
    )
    print(
        "OWNER:",
        connection.get(
            "user_chat_id"
        )
    )
    print(
        "ENABLED:",
        connection.get(
            "is_enabled"
        )
    )
    print(
        "CAN_REPLY:",
        rights.get(
            "can_reply"
        )
    )
    print(
        "CAN_READ_MESSAGES:",
        rights.get(
            "can_read_messages"
        )
    )
    print(
        "CAN_DELETE_ALL_MESSAGES:",
        rights.get(
            "can_delete_all_messages"
        )
    )
    print(
        "CAN_DELETE_SENT_MESSAGES:",
        rights.get(
            "can_delete_sent_messages"
        )
    )
    print("==============================================")
    print("")


# ============================================================
# SEND AUTO RESPONSE
# ============================================================

async def send_auto_response(
    session,
    connection_id,
    chat_id,
    message_id
):

    connection = business_connections.get(
        connection_id
    )


    if not connection:

        connection = await get_business_connection(
            session,
            connection_id
        )


    if not connection:

        print(
            "❌ Немає Business Connection."
        )

        return False


    if not connection.get(
        "is_enabled",
        False
    ):

        print(
            "❌ Business Connection вимкнений."
        )

        return False


    rights = connection.get(
        "rights",
        {}
    )


    can_reply = rights.get(
        "can_reply",
        False
    )


    if not can_reply:

        print("")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("❌ АВТОВІДПОВІДАЧ НЕ МОЖЕ ВІДПОВІДАТИ")
        print("Причина: can_reply = False")
        print("")
        print("У Telegram Business потрібно дозволити")
        print("боту право відповідати на повідомлення.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("")

        return False


    print("")
    print("🤖 ВІДПРАВКА АВТОВІДПОВІДІ")
    print(
        "chat_id:",
        chat_id
    )
    print(
        "message_id:",
        message_id
    )
    print(
        "business_connection_id:",
        connection_id
    )
    print(
        "text:",
        auto_responder_text
    )


    # ВАЖЛИВО:
    # Використовуємо reply_parameters,
    # а не старий reply_to_message_id.
    result = await tg_api(
        session,
        "sendMessage",
        business_connection_id=connection_id,
        chat_id=chat_id,
        text=auto_responder_text,
        reply_parameters={
            "message_id": message_id,
            "allow_sending_without_reply": True
        }
    )


    print(
        "AUTO RESPONSE RESULT:",
        result
    )


    if result.get("ok"):

        print(
            "✅ АВТОВІДПОВІДЬ ВІДПРАВЛЕНА"
        )

        return True


    print("")
    print(
        "❌ АВТОВІДПОВІДЬ НЕ ВІДПРАВЛЕНА"
    )
    print(
        "Telegram:",
        result.get(
            "description"
        )
    )
    print("")

    return False


# ============================================================
# BUSINESS MESSAGE
# ============================================================

async def handle_business_message(
    session,
    msg
):

    connection_id = msg.get(
        "business_connection_id"
    )


    if not connection_id:

        print(
            "Business message без business_connection_id"
        )

        return


    chat = msg.get(
        "chat",
        {}
    )


    chat_id = chat.get(
        "id"
    )


    message_id = msg.get(
        "message_id"
    )


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


    reply_to = msg.get(
        "reply_to_message"
    )


    if chat.get(
        "type"
    ) != "private":

        return


    print("")
    print("==============================================")
    print("📩 BUSINESS MESSAGE")
    print("==============================================")
    print(
        "chat_id:",
        chat_id
    )
    print(
        "message_id:",
        message_id
    )
    print(
        "sender_id:",
        sender_id
    )
    print(
        "text:",
        text
    )
    print(
        "business_connection_id:",
        connection_id
    )
    print("==============================================")


    # --------------------------------------------------------
    # BUSINESS CONNECTION
    # --------------------------------------------------------

    connection = await get_business_connection(
        session,
        connection_id
    )


    if not connection:

        return


    if not connection.get(
        "is_enabled",
        False
    ):

        print(
            "❌ Business connection disabled."
        )

        return


    print_business_rights(
        connection
    )


    owner_id = connection.get(
        "user_chat_id"
    )


    if not owner_id:

        print(
            "❌ owner_id не знайдено."
        )

        return


    # ========================================================
    # CLIENT MESSAGE
    # ========================================================

    if sender_id != owner_id:

        print(
            "👤 Це повідомлення КЛІЄНТА."
        )


        # ----------------------------------------------------
        # FORWARD TO OWNER
        # ----------------------------------------------------

        owner_result = await send_media_to_owner(
            session,
            owner_id,
            msg
        )


        if not owner_result.get(
            "ok",
            False
        ):

            print(
                "❌ Не вдалося переслати власнику:"
            )

            print(
                owner_result.get(
                    "description"
                )
            )


        # ----------------------------------------------------
        # AUTO RESPONSE
        # ----------------------------------------------------

        if auto_responder_enabled:

            await send_auto_response(
                session,
                connection_id,
                chat_id,
                message_id
            )

        else:

            print(
                "ℹ️ Автовідповідач вимкнений."
            )


        # ----------------------------------------------------
        # MUTE
        # ----------------------------------------------------

        if sender_id in muted_users:

            print(
                "🤐 Користувач зам'ючений."
            )


            if sender_id not in deleted_messages_cache:

                deleted_messages_cache[
                    sender_id
                ] = []


            deleted_messages_cache[
                sender_id
            ].append(
                get_msg_preview(msg)
            )


            if len(
                deleted_messages_cache[
                    sender_id
                ]
            ) > 100:

                deleted_messages_cache[
                    sender_id
                ] = (
                    deleted_messages_cache[
                        sender_id
                    ][-100:]
                )


            delete_result = await tg_api(
                session,
                "deleteMessage",
                chat_id=chat_id,
                message_id=message_id,
                business_connection_id=connection_id
            )


            if not delete_result.get(
                "ok"
            ):

                print(
                    "❌ DELETE ERROR:",
                    delete_result.get(
                        "description"
                    )
                )


        return


    # ========================================================
    # OWNER MESSAGE / COMMAND
    # ========================================================

    print(
        "👑 Це повідомлення ВЛАСНИКА."
    )


    if not text.startswith("."):

        return


    # ========================================================
    # .mute
    # ========================================================

    if text == ".mute":

        if not reply_to:

            await tg_api(
                session,
                "sendMessage",
                business_connection_id=connection_id,
                chat_id=chat_id,
                text=(
                    "❌ Відповідай на повідомлення "
                    "користувача."
                )
            )

            return


        target_user = reply_to.get(
            "from",
            {}
        )


        target_id = target_user.get(
            "id"
        )


        if not target_id:

            return


        muted_users.add(
            target_id
        )


        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=message_id,
            business_connection_id=connection_id
        )


        await tg_api(
            session,
            "sendMessage",
            business_connection_id=connection_id,
            chat_id=chat_id,
            text="мют активовано"
        )


        return


    # ========================================================
    # .umute
    # .unmute
    # ========================================================

    if (
        text == ".umute"
        or text == ".unmute"
    ):

        if not reply_to:

            await tg_api(
                session,
                "sendMessage",
                business_connection_id=connection_id,
                chat_id=chat_id,
                text=(
                    "❌ Відповідай на повідомлення "
                    "користувача."
                )
            )

            return


        target_id = reply_to.get(
            "from",
            {}
        ).get(
            "id"
        )


        if not target_id:

            return


        muted_users.discard(
            target_id
        )


        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=message_id,
            business_connection_id=connection_id
        )


        await tg_api(
            session,
            "sendMessage",
            business_connection_id=connection_id,
            chat_id=chat_id,
            text=(
                "ви розмючені можете писать"
            )
        )


        return


    # ========================================================
    # .nomute
    # ========================================================

    if text == ".nomute":

        if not reply_to:

            await tg_api(
                session,
                "sendMessage",
                business_connection_id=connection_id,
                chat_id=chat_id,
                text=(
                    "❌ Відповідай на повідомлення."
                )
            )

            return


        target_id = reply_to.get(
            "from",
            {}
        ).get(
            "id"
        )


        messages = deleted_messages_cache.get(
            target_id,
            []
        )


        if not messages:

            await tg_api(
                session,
                "sendMessage",
                business_connection_id=connection_id,
                chat_id=chat_id,
                text=(
                    "📭 Немає збережених "
                    "повідомлень."
                )
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
            "sendMessage",
            business_connection_id=connection_id,
            chat_id=chat_id,
            text=(
                "📥 Збережені повідомлення:\n\n"
                + history
            )
        )


        deleted_messages_cache[
            target_id
        ] = []


        return


    # ========================================================
    # .spam
    # ========================================================

    spam_match = re.match(
        r"^\.spam\s+(.+)\s+(\d+)$",
        text,
        re.DOTALL
    )


    if spam_match:

        spam_text = spam_match.group(
            1
        )


        try:

            count = int(
                spam_match.group(
                    2
                )
            )

        except Exception:

            count = 1


        # Безпечний ліміт
        count = max(
            1,
            min(
                count,
                20
            )
        )


        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=message_id,
            business_connection_id=connection_id
        )


        for i in range(count):

            result = await tg_api(
                session,
                "sendMessage",
                business_connection_id=connection_id,
                chat_id=chat_id,
                text=spam_text
            )


            if not result.get(
                "ok"
            ):

                print(
                    "❌ SPAM ERROR:",
                    result.get(
                        "description"
                    )
                )

                break


            await asyncio.sleep(
                0.25
            )


        return


    # ========================================================
    # .v / .v20 / .v30
    # ========================================================

    animation_match = re.match(
        r"^\.v(\d*)\s+(.+)$",
        text,
        re.DOTALL
    )


    if animation_match:

        seconds_text = animation_match.group(
            1
        )


        animation_text = animation_match.group(
            2
        )


        if seconds_text:

            try:

                seconds = int(
                    seconds_text
                )

            except Exception:

                seconds = 10

        else:

            seconds = 10


        seconds = max(
            1,
            min(
                seconds,
                300
            )
        )


        # Тут НЕ видаляємо команду.
        # Редагуємо те саме повідомлення.

        max_spaces = 8

        frames = []


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


        delay = max(
            0.8,
            float(seconds)
            / float(len(frames))
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


            if not result.get(
                "ok"
            ):

                error = result.get(
                    "description",
                    ""
                )


                if (
                    "message is not modified"
                    in error.lower()
                ):

                    await asyncio.sleep(
                        delay
                    )

                    continue


                print(
                    "❌ V ERROR:",
                    error
                )

                break


            await asyncio.sleep(
                delay
            )


        return


# ============================================================
# BUSINESS CONNECTION UPDATE
# ============================================================

async def handle_business_connection(
    session,
    connection
):

    connection_id = connection.get(
        "id"
    )


    if not connection_id:

        return


    business_connections[
        connection_id
    ] = connection


    print("")
    print("==============================================")
    print("🔗 BUSINESS CONNECTION UPDATE")
    print("==============================================")
    print(
        "ID:",
        connection_id
    )
    print(
        "OWNER:",
        connection.get(
            "user_chat_id"
        )
    )
    print(
        "ENABLED:",
        connection.get(
            "is_enabled"
        )
    )


    rights = connection.get(
        "rights",
        {}
    )


    print(
        "CAN_REPLY:",
        rights.get(
            "can_reply"
        )
    )


    print(
        "CAN_READ_MESSAGES:",
        rights.get(
            "can_read_messages"
        )
    )


    print("==============================================")
    print("")


# ============================================================
# UPDATE PROCESSOR
# ============================================================

async def process_update(
    session,
    update
):

    try:

        # ----------------------------------------------------
        # BUSINESS CONNECTION
        # ----------------------------------------------------

        if "business_connection" in update:

            await handle_business_connection(
                session,
                update[
                    "business_connection"
                ]
            )

            return


        # ----------------------------------------------------
        # BUSINESS MESSAGE
        # ----------------------------------------------------

        if "business_message" in update:

            await handle_business_message(
                session,
                update[
                    "business_message"
                ]
            )

            return


        # ----------------------------------------------------
        # EDITED BUSINESS MESSAGE
        # ----------------------------------------------------

        if "edited_business_message" in update:

            await handle_business_message(
                session,
                update[
                    "edited_business_message"
                ]
            )

            return


        # ----------------------------------------------------
        # NORMAL MESSAGE
        # ----------------------------------------------------

        if "message" in update:

            await handle_private_message(
                session,
                update[
                    "message"
                ]
            )

            return


        # ----------------------------------------------------
        # CALLBACK
        # ----------------------------------------------------

        if "callback_query" in update:

            await handle_callback_query(
                session,
                update[
                    "callback_query"
                ]
            )

            return


    except Exception as e:

        print("")
        print("==============================================")
        print("❌ UPDATE ERROR")
        print(repr(e))
        print("==============================================")
        print("")


# ============================================================
# HTTP HEALTH
# ============================================================

async def root_handler(
    request
):

    return web.Response(
        text=(
            "SEVE BOT IS RUNNING\n"
            "Telegram Business webhook is active."
        )
    )


async def health_handler(
    request
):

    return web.json_response(
        {
            "status": "ok",
            "service": "seve_bot"
        }
    )


# ============================================================
# TELEGRAM WEBHOOK
# ============================================================

async def telegram_webhook(
    request
):

    # Secret перевірка
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
            text="Invalid JSON"
        )


    session = request.app[
        "telegram_session"
    ]


    # Відповідаємо Telegram одразу.
    # Обробка йде окремим task.
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
# START HTTP SERVER
# ============================================================

async def start_http_server(
    session
):

    app = web.Application()


    app["telegram_session"] = session


    app.router.add_get(
        "/",
        root_handler
    )


    app.router.add_get(
        "/health",
        health_handler
    )


    webhook_path = (
        "/telegram/webhook/"
        + WEBHOOK_SECRET
    )


    app.router.add_post(
        webhook_path,
        telegram_webhook
    )


    runner = web.AppRunner(
        app
    )


    await runner.setup()


    # КЛЮЧОВЕ ДЛЯ RENDER
    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )


    await site.start()


    print("")
    print("==================================================")
    print("✅ HTTP SERVER ЗАПУЩЕНИЙ")
    print("==================================================")
    print(
        "HOST: 0.0.0.0"
    )
    print(
        "PORT:",
        PORT
    )


    if RENDER_EXTERNAL_URL:

        print(
            "URL:",
            RENDER_EXTERNAL_URL
        )


    print(
        "WEBHOOK PATH:",
        webhook_path
    )


    print("==================================================")
    print("")


    return runner


# ============================================================
# SET WEBHOOK
# ============================================================

async def setup_render_webhook(
    session
):

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
        "Встановлення Telegram webhook..."
    )


    print(
        webhook_url
    )


    result = await tg_api(
        session,
        "setWebhook",
        url=webhook_url,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=[
            "message",
            "callback_query",
            "business_connection",
            "business_message",
            "edited_business_message"
        ],
        drop_pending_updates=False
    )


    print(
        "setWebhook RESULT:",
        result
    )


    if not result.get(
        "ok"
    ):

        return False


    # Перевіряємо webhook
    info = await tg_api(
        session,
        "getWebhookInfo"
    )


    print("")
    print("==============================================")
    print("WEBHOOK INFO")
    print("==============================================")


    if info.get(
        "ok"
    ):

        webhook_info = info.get(
            "result",
            {}
        )


        print(
            "URL:",
            webhook_info.get(
                "url"
            )
        )


        print(
            "PENDING:",
            webhook_info.get(
                "pending_update_count",
                0
            )
        )


        print(
            "LAST ERROR:",
            webhook_info.get(
                "last_error_message",
                "немає"
            )
        )


        print(
            "LAST ERROR DATE:",
            webhook_info.get(
                "last_error_date",
                "немає"
            )
        )


    else:

        print(
            info
        )


    print("==============================================")
    print("")


    return True


# ============================================================
# LOCAL POLLING
# ============================================================

async def local_polling(
    session
):

    print(
        "Локальний режим: polling."
    )


    await tg_api(
        session,
        "deleteWebhook",
        drop_pending_updates=False
    )


    offset = 0


    while True:

        try:

            result = await tg_api(
                session,
                "getUpdates",
                offset=offset,
                timeout=25,
                allowed_updates=[
                    "message",
                    "callback_query",
                    "business_connection",
                    "business_message",
                    "edited_business_message"
                ]
            )


            if not result.get(
                "ok"
            ):

                print(
                    "getUpdates ERROR:",
                    result.get(
                        "description"
                    )
                )

                await asyncio.sleep(
                    3
                )

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
                "POLLING ERROR:",
                repr(e)
            )

            await asyncio.sleep(
                3
            )


# ============================================================
# CHECK BOT
# ============================================================

async def check_bot(
    session
):

    result = await tg_api(
        session,
        "getMe"
    )


    if not result.get(
        "ok"
    ):

        print("")
        print("==============================================")
        print("❌ BOT TOKEN НЕ ПРАЦЮЄ")
        print("==============================================")
        print(
            result.get(
                "description"
            )
        )
        print("==============================================")
        print("")

        return False


    bot = result.get(
        "result",
        {}
    )


    print("")
    print("==============================================")
    print("🤖 TELEGRAM BOT")
    print("==============================================")
    print(
        "NAME:",
        bot.get(
            "first_name"
        )
    )
    print(
        "USERNAME:",
        bot.get(
            "username"
        )
    )
    print(
        "ID:",
        bot.get(
            "id"
        )
    )
    print("==============================================")
    print("")


    return True


# ============================================================
# MAIN
# ============================================================

async def main():

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
        # СПОЧАТКУ PORT
        # ====================================================

        runner = await start_http_server(
            session
        )


        # ====================================================
        # ПЕРЕВІРКА BOT TOKEN
        # ====================================================

        bot_ok = await check_bot(
            session
        )


        if not bot_ok:

            print(
                "HTTP сервер залишається запущеним,"
                " але Telegram не працює."
            )

            while True:

                await asyncio.sleep(
                    3600
                )


        # ====================================================
        # RENDER
        # ====================================================

        if IS_RENDER:

            webhook_ok = await setup_render_webhook(
                session
            )


            if not webhook_ok:

                print("")
                print("==============================================")
                print("❌ WEBHOOK НЕ ВСТАНОВЛЕНО")
                print("==============================================")
                print("")
                print(
                    "Перевір RENDER_EXTERNAL_URL."
                )
                print("")
                print("==============================================")


            else:

                print("")
                print("==============================================")
                print("✅ TELEGRAM WEBHOOK READY")
                print("==============================================")
                print(
                    "Бот чекає Business повідомлення."
                )
                print("==============================================")
                print("")


            # Не завершуємо процес.
            while True:

                await asyncio.sleep(
                    3600
                )


        # ====================================================
        # LOCAL
        # ====================================================

        else:

            await local_polling(
                session
            )


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":

    print("")
    print("==================================================")
    print("SEVE BOT")
    print("==================================================")
    print(
        "Render:",
        IS_RENDER
    )
    print(
        "PORT:",
        PORT
    )
    print("==================================================")
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

        print("")
        print("==================================================")
        print("❌ КРИТИЧНА ПОМИЛКА")
        print("==================================================")
        print(
            repr(e)
        )
        print("==================================================")
        print("")

        raise