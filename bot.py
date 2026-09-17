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


# ============================================================
# ENV
# ============================================================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не знайдено в Environment Variables"
    )


API_URL = "https://api.telegram.org/bot" + TOKEN

PORT = int(
    os.getenv(
        "PORT",
        "10000"
    )
)

RENDER_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    ""
).rstrip("/")

WEBHOOK_SECRET = os.getenv(
    "WEBHOOK_SECRET",
    "seve_bot_webhook_secret"
)


# ============================================================
# SETTINGS
# ============================================================

auto_responder_enabled = True

auto_responder_text = (
    "привіт це мій авто відповідач\n"
    "я прийду в найближчий час\n"
    "будьласка без спаму"
)


# ============================================================
# STATE
# ============================================================

muted_users = set()

deleted_messages_cache = {}

waiting_for_text = False


# ============================================================
# TELEGRAM API
# ============================================================

async def tg_api(
    session,
    method,
    **kwargs
):

    url = API_URL + "/" + method

    try:

        async with session.post(
            url,
            json=kwargs
        ) as response:

            try:

                result = await response.json()

            except Exception:

                raw = await response.text()

                print(
                    "",
                    flush=True
                )

                print(
                    "❌ TELEGRAM RAW RESPONSE:",
                    raw,
                    flush=True
                )

                return {
                    "ok": False,
                    "description": raw
                }


            if not result.get("ok"):

                print(
                    "",
                    flush=True
                )

                print(
                    "❌ TELEGRAM API ERROR",
                    flush=True
                )

                print(
                    "METHOD:",
                    method,
                    flush=True
                )

                print(
                    "DESCRIPTION:",
                    result.get(
                        "description"
                    ),
                    flush=True
                )

                print(
                    "PARAMETERS:",
                    kwargs,
                    flush=True
                )


            return result


    except Exception as e:

        print(
            "",
            flush=True
        )

        print(
            "❌ API EXCEPTION:",
            repr(e),
            flush=True
        )

        return {
            "ok": False,
            "description": str(e)
        }


# ============================================================
# SETTINGS KEYBOARD
# ============================================================

def settings_keyboard():

    if auto_responder_enabled:

        status = "🟢 Увімкнено"

    else:

        status = "🔴 Вимкнено"


    return {
        "inline_keyboard": [

            [
                {
                    "text":
                        "Автовідповідач: "
                        + status,

                    "callback_data":
                        "toggle_ar"
                }
            ],

            [
                {
                    "text":
                        "✏️ Змінити текст",

                    "callback_data":
                        "edit_ar_text"
                }
            ]

        ]
    }


# ============================================================
# MESSAGE PREVIEW
# ============================================================

def message_preview(msg):

    if msg.get("text"):

        return msg["text"]


    if "photo" in msg:

        return (
            "[Фото] "
            + msg.get(
                "caption",
                ""
            )
        ).strip()


    if "video" in msg:

        return (
            "[Відео] "
            + msg.get(
                "caption",
                ""
            )
        ).strip()


    if "voice" in msg:

        return "[Голосове]"


    if "video_note" in msg:

        return "[Кружок]"


    if "document" in msg:

        return (
            "[Файл] "
            + msg["document"].get(
                "file_name",
                ""
            )
        ).strip()


    if "animation" in msg:

        return "[GIF]"


    if "sticker" in msg:

        return "[Стікер]"


    if "audio" in msg:

        return "[Аудіо]"


    return "[Повідомлення]"


# ============================================================
# SEND MESSAGE TO OWNER
# ============================================================

async def send_to_owner(
    session,
    owner_chat_id,
    msg
):

    if not owner_chat_id:

        return


    sender = msg.get(
        "from",
        {}
    )

    first_name = sender.get(
        "first_name",
        "Клієнт"
    )

    username = sender.get(
        "username"
    )

    sender_id = sender.get(
        "id",
        "?"
    )


    if username:

        sender_info = (
            "@"
            + username
        )

    else:

        sender_info = (
            "ID: "
            + str(sender_id)
        )


    header = (
        "📥 Повідомлення від "
        + first_name
        + " ("
        + sender_info
        + ")"
    )


    # TEXT

    if "text" in msg:

        await tg_api(
            session,
            "sendMessage",

            chat_id=owner_chat_id,

            text=(
                header
                + "\n\n"
                + msg["text"]
            )
        )

        return


    # PHOTO

    if "photo" in msg:

        caption = (
            header
            + "\n\n"
            + msg.get(
                "caption",
                ""
            )
        ).strip()


        await tg_api(
            session,
            "sendPhoto",

            chat_id=owner_chat_id,

            photo=msg["photo"][-1][
                "file_id"
            ],

            caption=caption
        )

        return


    # VIDEO

    if "video" in msg:

        caption = (
            header
            + "\n\n"
            + msg.get(
                "caption",
                ""
            )
        ).strip()


        await tg_api(
            session,
            "sendVideo",

            chat_id=owner_chat_id,

            video=msg["video"][
                "file_id"
            ],

            caption=caption
        )

        return


    # DOCUMENT

    if "document" in msg:

        caption = (
            header
            + "\n\n"
            + msg.get(
                "caption",
                ""
            )
        ).strip()


        await tg_api(
            session,
            "sendDocument",

            chat_id=owner_chat_id,

            document=msg["document"][
                "file_id"
            ],

            caption=caption
        )

        return


    # VOICE

    if "voice" in msg:

        await tg_api(
            session,
            "sendVoice",

            chat_id=owner_chat_id,

            voice=msg["voice"][
                "file_id"
            ]
        )

        return


    # ANIMATION

    if "animation" in msg:

        caption = (
            header
            + "\n\n"
            + msg.get(
                "caption",
                ""
            )
        ).strip()


        await tg_api(
            session,
            "sendAnimation",

            chat_id=owner_chat_id,

            animation=msg["animation"][
                "file_id"
            ],

            caption=caption
        )

        return


    # STICKER

    if "sticker" in msg:

        await tg_api(
            session,
            "sendMessage",

            chat_id=owner_chat_id,

            text=(
                header
                + "\n\n[стікер]"
            )
        )

        await tg_api(
            session,
            "sendSticker",

            chat_id=owner_chat_id,

            sticker=msg["sticker"][
                "file_id"
            ]
        )

        return


    # VIDEO NOTE

    if "video_note" in msg:

        await tg_api(
            session,
            "sendMessage",

            chat_id=owner_chat_id,

            text=(
                header
                + "\n\n[кружок]"
            )
        )

        await tg_api(
            session,
            "sendVideoNote",

            chat_id=owner_chat_id,

            video_note=msg["video_note"][
                "file_id"
            ]
        )

        return


    # AUDIO

    if "audio" in msg:

        await tg_api(
            session,
            "sendAudio",

            chat_id=owner_chat_id,

            audio=msg["audio"][
                "file_id"
            ]
        )

        return


# ============================================================
# AUTO RESPONDER
# ============================================================

async def send_auto_response(
    session,
    connection_id,
    chat_id,
    message_id
):

    global auto_responder_enabled


    print(
        "",
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )

    print(
        "🤖 AUTO RESPONDER",
        flush=True
    )

    print(
        "connection_id:",
        connection_id,
        flush=True
    )

    print(
        "chat_id:",
        chat_id,
        flush=True
    )

    print(
        "message_id:",
        message_id,
        flush=True
    )

    print(
        "enabled:",
        auto_responder_enabled,
        flush=True
    )

    print(
        "text:",
        repr(auto_responder_text),
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )


    if not auto_responder_enabled:

        print(
            "❌ AUTO RESPONDER ВИМКНЕНО",
            flush=True
        )

        return


    # --------------------------------------------------------
    # ВАЖЛИВО:
    # Надсилаємо БЕЗ reply_parameters.
    # --------------------------------------------------------

    result = await tg_api(

        session,

        "sendMessage",

        business_connection_id=
            connection_id,

        chat_id=
            chat_id,

        text=
            auto_responder_text
    )


    print(
        "",
        flush=True
    )

    print(
        "AUTO RESPONSE RESULT:",
        result,
        flush=True
    )


    if result.get("ok"):

        print(
            "✅ АВТОВІДПОВІДЬ ВІДПРАВЛЕНА",
            flush=True
        )

    else:

        print(
            "❌ АВТОВІДПОВІДЬ НЕ ВІДПРАВЛЕНА",
            flush=True
        )

        print(
            "Причина:",
            result.get(
                "description"
            ),
            flush=True
        )


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

    chat = msg.get(
        "chat",
        {}
    )

    chat_id = chat.get(
        "id"
    )

    chat_type = chat.get(
        "type"
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


    print(
        "",
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )

    print(
        "📩 BUSINESS MESSAGE",
        flush=True
    )

    print(
        "connection_id:",
        connection_id,
        flush=True
    )

    print(
        "chat_id:",
        chat_id,
        flush=True
    )

    print(
        "chat_type:",
        chat_type,
        flush=True
    )

    print(
        "message_id:",
        message_id,
        flush=True
    )

    print(
        "sender_id:",
        sender_id,
        flush=True
    )

    print(
        "text:",
        repr(text),
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )


    if not connection_id:

        print(
            "❌ Немає business_connection_id",
            flush=True
        )

        return


    if chat_type != "private":

        print(
            "ℹ️ Це не private chat",
            flush=True
        )

        return


    # ========================================================
    # GET BUSINESS CONNECTION
    # ========================================================

    result = await tg_api(

        session,

        "getBusinessConnection",

        business_connection_id=
            connection_id
    )


    if not result.get("ok"):

        print(
            "❌ НЕ ВДАЛОСЯ ОТРИМАТИ BUSINESS CONNECTION",
            flush=True
        )

        return


    connection = result.get(
        "result",
        {}
    )


    # ========================================================
    # CONNECTION DATA
    # ========================================================

    print(
        "",
        flush=True
    )

    print(
        "========== BUSINESS CONNECTION ==========",
        flush=True
    )

    print(
        "id:",
        connection.get(
            "id"
        ),
        flush=True
    )

    print(
        "enabled:",
        connection.get(
            "is_enabled"
        ),
        flush=True
    )

    print(
        "user:",
        connection.get(
            "user"
        ),
        flush=True
    )

    print(
        "user_chat_id:",
        connection.get(
            "user_chat_id"
        ),
        flush=True
    )

    print(
        "rights:",
        connection.get(
            "rights"
        ),
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )


    if not connection.get(
        "is_enabled"
    ):

        print(
            "❌ BUSINESS CONNECTION ВИМКНЕНО",
            flush=True
        )

        return


    rights = connection.get(
        "rights"
    ) or {}


    can_reply = rights.get(
        "can_reply",
        False
    )


    print(
        "CAN_REPLY:",
        can_reply,
        flush=True
    )


    owner_user = connection.get(
        "user"
    ) or {}


    owner_user_id = owner_user.get(
        "id"
    )


    owner_chat_id = connection.get(
        "user_chat_id"
    )


    print(
        "OWNER USER ID:",
        owner_user_id,
        flush=True
    )

    print(
        "OWNER CHAT ID:",
        owner_chat_id,
        flush=True
    )

    print(
        "SENDER ID:",
        sender_id,
        flush=True
    )


    # ========================================================
    # MESSAGE FROM CLIENT
    # ========================================================

    if sender_id != owner_user_id:

        print(
            "",
            flush=True
        )

        print(
            "👤 ПОВІДОМЛЕННЯ ВІД КЛІЄНТА",
            flush=True
        )


        # ----------------------------------------------------
        # SEND TO OWNER
        # ----------------------------------------------------

        await send_to_owner(

            session,

            owner_chat_id,

            msg
        )


        # ----------------------------------------------------
        # AUTO RESPONSE
        # ----------------------------------------------------

        if can_reply:

            await send_auto_response(

                session,

                connection_id,

                chat_id,

                message_id
            )

        else:

            print(
                "",
                flush=True
            )

            print(
                "==========================================",
                flush=True
            )

            print(
                "❌ НЕМАЄ ПРАВА can_reply",
                flush=True
            )

            print(
                "Telegram не дозволяє боту",
                flush=True
            )

            print(
                "відправляти повідомлення",
                flush=True
            )

            print(
                "від імені Business-акаунта.",
                flush=True
            )

            print(
                "Потрібно увімкнути право",
                flush=True
            )

            print(
                "«Відповідати на повідомлення»",
                flush=True
            )

            print(
                "у налаштуваннях підключеного Business-бота.",
                flush=True
            )

            print(
                "==========================================",
                flush=True
            )


        # ----------------------------------------------------
        # MUTED USER
        # ----------------------------------------------------

        if sender_id in muted_users:

            print(
                "🤐 КОРИСТУВАЧ У MUTE:",
                sender_id,
                flush=True
            )


            if sender_id not in deleted_messages_cache:

                deleted_messages_cache[
                    sender_id
                ] = []


            deleted_messages_cache[
                sender_id
            ].append(
                message_preview(msg)
            )


            # deleteMessage
            # залишається окремо,
            # бо це вже існуюча функція.

            delete_result = await tg_api(

                session,

                "deleteMessage",

                business_connection_id=
                    connection_id,

                chat_id=
                    chat_id,

                message_id=
                    message_id
            )


            if delete_result.get("ok"):

                print(
                    "🗑 Повідомлення видалено",
                    flush=True
                )

            else:

                print(
                    "❌ DELETE ERROR:",
                    delete_result.get(
                        "description"
                    ),
                    flush=True
                )


        return


    # ========================================================
    # OWNER MESSAGE
    # ========================================================

    print(
        "👑 ПОВІДОМЛЕННЯ ВЛАСНИКА",
        flush=True
    )


    if not text.startswith("."):

        return


    # ========================================================
    # .mute
    # ========================================================

    if text.startswith(
        ".mute"
    ):

        reply = msg.get(
            "reply_to_message"
        )


        if not reply:

            await tg_api(

                session,

                "sendMessage",

                business_connection_id=
                    connection_id,

                chat_id=
                    chat_id,

                text=
                    "❌ Відповідай на повідомлення юзера!"
            )

            return


        target = reply.get(
            "from",
            {}
        )

        target_id = target.get(
            "id"
        )


        if target_id:

            muted_users.add(
                target_id
            )


        await tg_api(

            session,

            "sendMessage",

            business_connection_id=
                connection_id,

            chat_id=
                chat_id,

            text=
                "🤐 Користувача зам'ючено."
        )


        return


    # ========================================================
    # .unmute / .umute
    # ========================================================

    if (
        text.startswith(".unmute")
        or
        text.startswith(".umute")
    ):

        reply = msg.get(
            "reply_to_message"
        )


        if not reply:

            await tg_api(

                session,

                "sendMessage",

                business_connection_id=
                    connection_id,

                chat_id=
                    chat_id,

                text=
                    "❌ Відповідай на повідомлення юзера!"
            )

            return


        target = reply.get(
            "from",
            {}
        )

        target_id = target.get(
            "id"
        )


        if target_id:

            muted_users.discard(
                target_id
            )


        await tg_api(

            session,

            "sendMessage",

            business_connection_id=
                connection_id,

            chat_id=
                chat_id,

            text=
                "🔊 Користувача роз'ючено."
        )


        return


    # ========================================================
    # .nomute
    # ========================================================

    if text.startswith(
        ".nomute"
    ):

        reply = msg.get(
            "reply_to_message"
        )


        if not reply:

            await tg_api(

                session,

                "sendMessage",

                business_connection_id=
                    connection_id,

                chat_id=
                    chat_id,

                text=
                    "❌ Відповідай на повідомлення!"
            )

            return


        target_id = (
            reply
            .get(
                "from",
                {}
            )
            .get(
                "id"
            )
        )


        messages = deleted_messages_cache.get(
            target_id,
            []
        )


        if messages:

            history = "\n".join(
                "• " + item
                for item in messages
            )


            answer = (
                "📥 Збережені повідомлення:"
                "\n\n"
                + history
            )


            deleted_messages_cache[
                target_id
            ] = []

        else:

            answer = (
                "📭 Немає збережених повідомлень."
            )


        await tg_api(

            session,

            "sendMessage",

            business_connection_id=
                connection_id,

            chat_id=
                chat_id,

            text=
                answer
        )


        return


    # ========================================================
    # .spam
    # ========================================================

    spam_match = re.match(

        r"^\.spam\s+(.+)\s+(\d+)$",

        text
    )


    if spam_match:

        spam_text = spam_match.group(
            1
        )

        count = min(
            int(
                spam_match.group(
                    2
                )
            ),
            100
        )


        for _ in range(count):

            await tg_api(

                session,

                "sendMessage",

                business_connection_id=
                    connection_id,

                chat_id=
                    chat_id,

                text=
                    spam_text
            )


            await asyncio.sleep(
                0.1
            )


        return


    # ========================================================
    # .v / .v20
    # ========================================================

    animation_match = re.match(

        r"^\.v(\d*)\s+(.+)$",

        text,

        re.DOTALL
    )


    if animation_match:

        seconds_text = (
            animation_match.group(
                1
            )
        )


        animation_text = (
            animation_match.group(
                2
            )
        )


        if seconds_text:

            seconds = int(
                seconds_text
            )

        else:

            seconds = 10


        spaces = 8

        frames = []


        for i in range(
            spaces + 1
        ):

            frames.append(
                (
                    "\u00A0" * i
                )
                + animation_text
            )


        for i in range(
            spaces - 1,
            0,
            -1
        ):

            frames.append(
                (
                    "\u00A0" * i
                )
                + animation_text
            )


        delay = max(
            0.5,
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

                business_connection_id=
                    connection_id,

                chat_id=
                    chat_id,

                message_id=
                    message_id,

                text=
                    frame
            )


            if not result.get(
                "ok"
            ):

                description = (
                    result.get(
                        "description",
                        ""
                    )
                )


                if (
                    "message is not modified"
                    in description
                ):

                    continue


                print(
                    "❌ ANIMATION ERROR:",
                    description,
                    flush=True
                )


                break


            await asyncio.sleep(
                delay
            )


        return


# ============================================================
# NORMAL MESSAGE
# ============================================================

async def handle_normal_message(
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

    text = msg.get(
        "text",
        ""
    )


    # ========================================================
    # NEW AUTO RESPONSE TEXT
    # ========================================================

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

            chat_id=
                chat_id,

            text=
                "✅ Текст автовідповідача збережено!\n\n"
                + auto_responder_text,

            reply_markup=
                settings_keyboard()
        )


        return


    # ========================================================
    # COMMANDS
    # ========================================================

    if text in (
        "/start",
        "/settings",
        "/seting"
    ):

        waiting_for_text = False


        await tg_api(

            session,

            "sendMessage",

            chat_id=
                chat_id,

            text=
                "⚙️ Керування ботом:",

            reply_markup=
                settings_keyboard()
        )


# ============================================================
# CALLBACK
# ============================================================

async def handle_callback(
    session,
    callback
):

    global auto_responder_enabled
    global waiting_for_text


    callback_id = callback.get(
        "id"
    )

    data = callback.get(
        "data"
    )

    message = callback.get(
        "message",
        {}
    )

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


    # ========================================================
    # TOGGLE
    # ========================================================

    if data == "toggle_ar":

        auto_responder_enabled = (
            not auto_responder_enabled
        )


        if auto_responder_enabled:

            text = (
                "🟢 Автовідповідач увімкнено"
            )

        else:

            text = (
                "🔴 Автовідповідач вимкнено"
            )


        await tg_api(

            session,

            "answerCallbackQuery",

            callback_query_id=
                callback_id,

            text=
                text
        )


        await tg_api(

            session,

            "editMessageText",

            chat_id=
                chat_id,

            message_id=
                message_id,

            text=
                "⚙️ Керування ботом:",

            reply_markup=
                settings_keyboard()
        )


        return


    # ========================================================
    # EDIT TEXT
    # ========================================================

    if data == "edit_ar_text":

        waiting_for_text = True


        await tg_api(

            session,

            "answerCallbackQuery",

            callback_query_id=
                callback_id
        )


        await tg_api(

            session,

            "sendMessage",

            chat_id=
                chat_id,

            text=
                "Напиши новий текст автовідповідача:"
        )


# ============================================================
# PROCESS UPDATE
# ============================================================

async def process_update(
    session,
    update
):

    print(
        "",
        flush=True
    )

    print(
        "PROCESS UPDATE:",
        list(
            update.keys()
        ),
        flush=True
    )


    # BUSINESS MESSAGE

    if "business_message" in update:

        await handle_business_message(

            session,

            update[
                "business_message"
            ]
        )

        return


    # NORMAL MESSAGE

    if "message" in update:

        await handle_normal_message(

            session,

            update[
                "message"
            ]
        )

        return


    # CALLBACK

    if "callback_query" in update:

        await handle_callback(

            session,

            update[
                "callback_query"
            ]
        )

        return


    # BUSINESS CONNECTION

    if "business_connection" in update:

        print(
            "",
            flush=True
        )

        print(
            "🔗 BUSINESS CONNECTION UPDATE",
            flush=True
        )

        print(
            update[
                "business_connection"
            ],
            flush=True
        )

        return


    print(
        "ℹ️ UPDATE НЕ ОБРОБЛЕНО",
        flush=True
    )


# ============================================================
# HTTP
# ============================================================

async def root(request):

    return web.Response(
        text="SEVE BOT RUNNING"
    )


async def health(request):

    return web.Response(
        text="SEVE BOT OK"
    )


# ============================================================
# WEBHOOK
# ============================================================

async def telegram_webhook(
    request
):

    try:

        secret = request.match_info.get(
            "secret"
        )


        if secret != WEBHOOK_SECRET:

            print(
                "❌ INVALID WEBHOOK SECRET",
                flush=True
            )

            return web.Response(
                status=403,
                text="Forbidden"
            )


        update = await request.json()


        print(
            "",
            flush=True
        )

        print(
            "========== TELEGRAM UPDATE ==========",
            flush=True
        )

        print(
            update,
            flush=True
        )

        print(
            "=====================================",
            flush=True
        )


        session = request.app[
            "session"
        ]


        await process_update(

            session,

            update
        )


        print(
            "========== UPDATE PROCESSED ==========",
            flush=True
        )


        return web.json_response(
            {
                "ok": True
            }
        )


    except Exception as e:

        print(
            "",
            flush=True
        )

        print(
            "========== WEBHOOK ERROR ==========",
            flush=True
        )

        print(
            repr(e),
            flush=True
        )

        print(
            "===================================",
            flush=True
        )


        return web.json_response(

            {
                "ok": False,
                "error": str(e)
            },

            status=200
        )


# ============================================================
# WEBHOOK SETUP
# ============================================================

async def setup_webhook(
    session
):

    if not RENDER_URL:

        print(
            "❌ RENDER_EXTERNAL_URL НЕ ВКАЗАНИЙ",
            flush=True
        )

        return


    webhook_url = (

        RENDER_URL

        + "/telegram/webhook/"

        + WEBHOOK_SECRET
    )


    print(
        "",
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )

    print(
        "🌐 SETTING TELEGRAM WEBHOOK",
        flush=True
    )

    print(
        webhook_url,
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )


    result = await tg_api(

        session,

        "setWebhook",

        url=
            webhook_url,

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
        "SET WEBHOOK RESULT:",
        result,
        flush=True
    )


# ============================================================
# APP
# ============================================================

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


    await setup_webhook(
        session
    )


    async def cleanup(app):

        await app[
            "session"
        ].close()


    app.on_cleanup.append(
        cleanup
    )


    return app


# ============================================================
# MAIN
# ============================================================

async def main():

    print(
        "",
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )

    print(
        "          SEVE BOT STARTED",
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )

    print(
        "PORT:",
        PORT,
        flush=True
    )

    print(
        "RENDER URL:",
        RENDER_URL,
        flush=True
    )

    print(
        "WEBHOOK SECRET:",
        WEBHOOK_SECRET,
        flush=True
    )

    print(
        "AUTO RESPONDER:",
        auto_responder_enabled,
        flush=True
    )

    print(
        "AUTO TEXT:",
        repr(
            auto_responder_text
        ),
        flush=True
    )

    print(
        "==========================================",
        flush=True
    )


    app = await create_app()


    runner = web.AppRunner(
        app
    )


    await runner.setup()


    site = web.TCPSite(

        runner,

        "0.0.0.0",

        PORT
    )


    await site.start()


    print(
        "",
        flush=True
    )

    print(
        "🌐 SERVER LISTENING",
        flush=True
    )

    print(
        "0.0.0.0:"
        + str(PORT),
        flush=True
    )


    while True:

        await asyncio.sleep(
            3600
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "Бот зупинений.",
            flush=True
        )