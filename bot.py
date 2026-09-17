import asyncio
import logging
import os
import re
import aiohttp
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO)
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    print("ПОМИЛКА: BOT_TOKEN не знайдено у .env")
    raise SystemExit(1)

API_URL = "https://api.telegram.org/bot" + TOKEN


muted_users = set()
deleted_messages_cache = {}

auto_responder_enabled = True

auto_responder_text = (
    "привіт це мій авто відповідач\n"
    "я прийду в найближчий час\n"
    "бульдласка без спаму"
)

waiting_for_text = False


# =========================================================
# TELEGRAM API
# =========================================================

async def tg_api(session, method, **kwargs):

    try:
        async with session.post(
            API_URL + "/" + method,
            json=kwargs
        ) as resp:

            return await resp.json()

    except Exception as e:

        return {
            "ok": False,
            "description": str(e)
        }


# =========================================================
# SETTINGS
# =========================================================

def get_settings_keyboard():

    if auto_responder_enabled:
        status = "🟢 Увімкнено"
    else:
        status = "🔴 Вимкнено"

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


# =========================================================
# MESSAGE PREVIEW
# =========================================================

def get_msg_preview(msg):

    if "text" in msg:
        return msg["text"]

    if "photo" in msg:
        return (
            "[Фото] " +
            msg.get("caption", "")
        ).strip()

    if "video" in msg:
        return (
            "[Відео] " +
            msg.get("caption", "")
        ).strip()

    if "video_note" in msg:
        return "[Кружок / Відеоповідомлення]"

    if "voice" in msg:
        return "[Голосове повідомлення]"

    if "document" in msg:

        return (
            "[Файл: " +
            msg["document"].get(
                "file_name",
                "документ"
            ) +
            "]"
        )

    if "sticker" in msg:

        return (
            "[Наліпка " +
            msg["sticker"].get(
                "emoji",
                ""
            ) +
            "]"
        ).strip()

    if "animation" in msg:
        return "[GIF / Анімація]"

    if "audio" in msg:

        return (
            "[Аудіо] " +
            msg.get("caption", "")
        ).strip()

    return "[Медіаповідомлення]"


# =========================================================
# SEND MEDIA TO OWNER
# =========================================================

async def send_media_to_owner(
    session,
    owner_id,
    msg
):

    sender = msg.get("from", {})

    sender_name = sender.get(
        "first_name",
        "Клієнт"
    )

    username = sender.get("username")

    if username:
        user_info = "@" + username
    else:
        user_info = "ID: " + str(
            sender.get("id")
        )

    header = (
        "📥 Нове повідомлення від " +
        sender_name +
        " (" +
        user_info +
        "):"
    )

    caption = msg.get(
        "caption",
        ""
    )

    if caption:
        caption_text = (
            header +
            "\n\n" +
            caption
        )
    else:
        caption_text = header


    if (
        "text" in msg
        and
        "photo" not in msg
        and
        "video" not in msg
        and
        "document" not in msg
        and
        "voice" not in msg
        and
        "video_note" not in msg
        and
        "sticker" not in msg
        and
        "animation" not in msg
        and
        "audio" not in msg
    ):

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=(
                header +
                "\n\n" +
                msg["text"]
            )
        )

        return


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


    if "video_note" in msg:

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=header
        )

        await tg_api(
            session,
            "sendVideoNote",
            chat_id=owner_id,
            video_note=msg["video_note"]["file_id"]
        )

        return


    if "sticker" in msg:

        await tg_api(
            session,
            "sendMessage",
            chat_id=owner_id,
            text=header
        )

        await tg_api(
            session,
            "sendSticker",
            chat_id=owner_id,
            sticker=msg["sticker"]["file_id"]
        )

        return


    if "animation" in msg:

        await tg_api(
            session,
            "sendAnimation",
            chat_id=owner_id,
            animation=msg["animation"]["file_id"],
            caption=caption_text
        )

        return


    if "audio" in msg:

        await tg_api(
            session,
            "sendAudio",
            chat_id=owner_id,
            audio=msg["audio"]["file_id"],
            caption=caption_text
        )

        return


# =========================================================
# PRIVATE MESSAGE
# =========================================================

async def handle_private_message(
    session,
    msg
):

    global waiting_for_text
    global auto_responder_text

    chat_id = msg["chat"]["id"]

    text = msg.get(
        "text",
        ""
    )


    if (
        waiting_for_text
        and
        text
        and
        not text.startswith("/")
    ):

        auto_responder_text = text
        waiting_for_text = False

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=(
                "✅ Текст автовідповідача "
                "збережено!\n\n" +
                auto_responder_text
            ),
            reply_markup=get_settings_keyboard()
        )

        return


    # =====================================================
    # START
    # =====================================================

    if text == "/start":

        waiting_for_text = False

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=(
                "👋 Привіт!\n\n"
                "/seting — налаштування\n"
                "/help — допомога"
            )
        )

        return


    # =====================================================
    # SETING
    # =====================================================

    if text in [
        "/seting",
        "/settings"
    ]:

        waiting_for_text = False

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text="⚙️ Налаштування:",
            reply_markup=get_settings_keyboard()
        )

        return


    # =====================================================
    # HELP
    # =====================================================

    if text == "/help":

        waiting_for_text = False

        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=(
                "📚 СПИСОК КОМАНД\n\n"

                "/start — запуск\n"
                "/seting — налаштування\n"
                "/help — допомога\n\n"

                ".mute — зам'ютити користувача\n"
                ".umute — розм'ютити користувача\n"
                ".unmute — розм'ютити користувача\n"
                ".nomute — показати видалені повідомлення\n"
                ".spam текст кількість — спам\n"
                ".v20 текст — анімація 20 секунд\n"
                ".v текст — анімація 10 секунд\n\n"

                "Для .mute та .umute потрібно "
                "відповісти на повідомлення користувача."
            )
        )

        return


# =========================================================
# CALLBACK
# =========================================================

async def handle_callback_query(
    session,
    cb
):

    global auto_responder_enabled
    global waiting_for_text

    cb_id = cb["id"]

    message = cb["message"]

    chat_id = message["chat"]["id"]

    message_id = message["message_id"]

    data = cb.get("data")


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
            callback_query_id=cb_id,
            text="Автовідповідач " + status
        )

        await tg_api(
            session,
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text="⚙️ Налаштування:",
            reply_markup=get_settings_keyboard()
        )

        return


    if data == "edit_ar_text":

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
                "Напиши новий текст "
                "для автовідповідача."
            )
        )

        return


# =========================================================
# V ANIMATION
# =========================================================

def make_v_frames(text):

    SP = "\u00A0"

    n = len(text)

    if n <= 1:
        return [text]


    frames = []

    # Початок
    frames.append(text)


    # Прибираємо символи поступово
    middle = (n + 1) // 2

    for i in range(1, n - middle + 1):

        left = text[:n - i]

        if left:
            frames.append(
                (SP * i) +
                left
            )


    # Хвиля через край
    for k in range(1, middle):

        suffix = text[n - k:]

        prefix = text[:middle - k]

        if prefix:

            gap = SP * (
                middle + k - 1
            )

            frames.append(
                suffix +
                gap +
                prefix
            )


    # Інша сторона
    if middle <= n:

        frames.append(
            text[n - middle:]
        )


    # Назад
    reverse_frames = list(
        reversed(
            frames[1:-1]
        )
    )

    frames.extend(
        reverse_frames
    )

    frames.append(text)

    return frames


# =========================================================
# RUN V ANIMATION
# =========================================================

async def run_v_animation(
    session,
    chat_id,
    message_id,
    conn_id,
    anim_text,
    seconds
):

    frames = make_v_frames(
        anim_text
    )

    if not frames:
        return


    if seconds < 1:
        seconds = 1

    if seconds > 300:
        seconds = 300


    delay = float(seconds) / float(
        len(frames)
    )


    # Telegram не варто редагувати
    # надто часто.
    if delay < 0.8:
        delay = 0.8


    end_time = (
        asyncio.get_event_loop().time()
        +
        seconds
    )


    index = 0


    while (
        asyncio.get_event_loop().time()
        <
        end_time
    ):

        frame = frames[
            index %
            len(frames)
        ]

        index += 1


        result = await tg_api(
            session,
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=frame,
            business_connection_id=conn_id
        )


        if not result.get("ok"):

            description = result.get(
                "description",
                ""
            ).lower()

            if (
                "message is not modified"
                in description
            ):
                pass

            elif (
                "message to edit not found"
                in description
            ):
                break


        await asyncio.sleep(
            delay
        )


    # Завершуємо оригінальним текстом
    await tg_api(
        session,
        "editMessageText",
        chat_id=chat_id,
        message_id=message_id,
        text=anim_text,
        business_connection_id=conn_id
    )


# =========================================================
# BUSINESS MESSAGE
# =========================================================

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

    if chat.get("type") != "private":
        return


    message_id = msg.get(
        "message_id"
    )

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


    # =====================================================
    # BUSINESS CONNECTION
    # =====================================================

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


    # =====================================================
    # MESSAGE FROM CLIENT
    # =====================================================

    if sender_id != owner_id:

        await send_media_to_owner(
            session,
            owner_id,
            msg
        )


        # Автовідповідач
        if auto_responder_enabled:

            await tg_api(
                session,
                "sendMessage",
                chat_id=chat_id,
                text=auto_responder_text,
                business_connection_id=conn_id,
                reply_to_message_id=message_id
            )


        # Якщо користувач у mute
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


            await tg_api(
                session,
                "deleteMessage",
                chat_id=chat_id,
                message_id=message_id,
                business_connection_id=conn_id
            )

        return


    # =====================================================
    # ТІЛЬКИ КОМАНДИ ВЛАСНИКА
    # =====================================================

    if not text.startswith("."):
        return


    # =====================================================
    # .MUTE
    # =====================================================
    # ВАЖЛИВО:
    # ЦЕЙ БЛОК ПЕРЕВІРЯЄ ТІЛЬКИ .mute
    # =====================================================

    if text.strip() == ".mute":

        if not reply_to:

            await tg_api(
                session,
                "deleteMessage",
                chat_id=chat_id,
                message_id=message_id,
                business_connection_id=conn_id
            )

            await tg_api(
                session,
                "sendMessage",
                chat_id=chat_id,
                text=(
                    "...................................😂ти замючен🤣.........................................."
                    "........🤣🤣вопшем ти итак и так лох хахаха🤣🤣"
                ),
                business_connection_id=conn_id
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


        # ДОДАЄМО КОРИСТУВАЧА В MUTE
        muted_users.add(
            target_id
        )


        # ВИДАЛЯЄМО КОМАНДУ .mute
        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=message_id,
            business_connection_id=conn_id
        )


        # ПОВІДОМЛЕННЯ ПРО MUTE
        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text="мют активовано",
            business_connection_id=conn_id
        )

        return


    # =====================================================
    # .UMUTE
    # =====================================================
    # ОКРЕМИЙ БЛОК!
    #
    # НЕ ПЕРЕВІРЯЄМО .mute.
    # =====================================================

    if text.strip() == ".umute":

        if not reply_to:

            await tg_api(
                session,
                "deleteMessage",
                chat_id=chat_id,
                message_id=message_id,
                business_connection_id=conn_id
            )

            await tg_api(
                session,
                "sendMessage",
                chat_id=chat_id,
                text=(
                    "........тебя розмютили........"
                    ""
                ),
                business_connection_id=conn_id
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


        # ВИДАЛЯЄМО КОРИСТУВАЧА З MUTE
        muted_users.discard(
            target_id
        )


        # ВИДАЛЯЄМО КОМАНДУ .umute
        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=message_id,
            business_connection_id=conn_id
        )


        # ПРАВИЛЬНЕ ПОВІДОМЛЕННЯ ПІСЛЯ РОЗМ'ЮТУ
        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text="ви розмючені можете писать",
            business_connection_id=conn_id
        )

        return


    # =====================================================
    # .UNMUTE
    # =====================================================

    if text.strip() == ".unmute":

        if not reply_to:

            await tg_api(
                session,
                "deleteMessage",
                chat_id=chat_id,
                message_id=message_id,
                business_connection_id=conn_id
            )

            await tg_api(
                session,
                "sendMessage",
                chat_id=chat_id,
                text=(
                     "........тебя розмютили........"
                    ""
                ),
                business_connection_id=conn_id
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
            business_connection_id=conn_id
        )


        await tg_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text="ви розмючені можете писать",
            business_connection_id=conn_id
        )

        return


    # =====================================================
    # .NOMUTE
    # =====================================================

    if text.strip() == ".nomute":

        if not reply_to:

            await tg_api(
                session,
                "deleteMessage",
                chat_id=chat_id,
                message_id=message_id,
                business_connection_id=conn_id
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


        if messages:

            history = "\n".join(
                "• " + x
                for x in messages
            )

            await tg_api(
                session,
                "sendMessage",
                chat_id=chat_id,
                text=(
                    "📥 Видалені повідомлення:\n\n" +
                    history
                ),
                business_connection_id=conn_id
            )

            deleted_messages_cache[
                target_id
            ] = []

        else:

            await tg_api(
                session,
                "sendMessage",
                chat_id=chat_id,
                text=(
                    "📭 Немає збережених "
                    "повідомлень."
                ),
                business_connection_id=conn_id
            )


        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=message_id,
            business_connection_id=conn_id
        )

        return


    # =====================================================
    # .SPAM
    # =====================================================

    spam_match = re.match(
        r"^\.spam\s+(.+)\s+(\d+)$",
        text,
        re.DOTALL
    )

    if spam_match:

        spam_text = spam_match.group(1)

        count = int(
            spam_match.group(2)
        )

        if count > 100:
            count = 100


        await tg_api(
            session,
            "deleteMessage",
            chat_id=chat_id,
            message_id=message_id,
            business_connection_id=conn_id
        )


        for i in range(count):

            await tg_api(
                session,
                "sendMessage",
                chat_id=chat_id,
                text=spam_text,
                business_connection_id=conn_id
            )

            await asyncio.sleep(
                0.1
            )

        return


    # =====================================================
    # .V
    # =====================================================

    anim_match = re.match(
        r"^\.v(\d*)\s+(.+)$",
        text,
        re.DOTALL
    )

    if anim_match:

        sec_text = anim_match.group(1)

        anim_text = anim_match.group(2)


        if sec_text:
            seconds = int(sec_text)
        else:
            seconds = 10


        if seconds < 1:
            seconds = 1

        if seconds > 300:
            seconds = 300


        # Спочатку .v20 стає самим текстом
        await tg_api(
            session,
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=anim_text,
            business_connection_id=conn_id
        )


        # Далі редагується ТЕ САМЕ повідомлення
        await run_v_animation(
            session,
            chat_id,
            message_id,
            conn_id,
            anim_text,
            seconds
        )

        return


# =========================================================
# MAIN
# =========================================================

async def main():

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
            "Бот запущений і готовий до роботи!"
        )


        while True:

            try:

                result = await tg_api(
                    session,
                    "getUpdates",
                    offset=offset,
                    timeout=30
                )


                if not result.get("ok"):

                    await asyncio.sleep(3)

                    continue


                for update in result.get(
                    "result",
                    []
                ):

                    offset = (
                        update["update_id"] +
                        1
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
                    "Помилка: " +
                    str(e)
                )

                await asyncio.sleep(3)


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "Бот зупинений."
        )

