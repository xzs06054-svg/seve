import asyncio
import os
import aiohttp

from aiohttp import web
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не знайдений у Render Environment")

API_URL = "https://api.telegram.org/bot" + TOKEN

PORT = int(os.environ.get("PORT", "10000"))

RENDER_URL = os.environ.get(
    "RENDER_EXTERNAL_URL",
    ""
).strip()

WEBHOOK_SECRET = os.environ.get(
    "WEBHOOK_SECRET",
    "seve_bot_webhook_secret"
).strip()


# ============================================================
# AUTO RESPONDER
# ============================================================

auto_responder_enabled = True

auto_responder_text = (
    "привіт це мій авто відповідач\n"
    "я прийду в найближчий час\n"
    "будьласка без спаму"
)


# ============================================================
# BUSINESS CONNECTIONS
# ============================================================

business_connections = {}


# ============================================================
# MUTE
# ============================================================

muted_users = set()


# ============================================================
# LOG
# ============================================================

def log(text):
    print(text, flush=True)


# ============================================================
# TELEGRAM API
# ============================================================

async def telegram_api(session, method, **data):

    url = API_URL + "/" + method

    try:

        async with session.post(
            url,
            json=data,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:

            raw = await response.text()

            try:
                result = await response.json()
            except:
                result = {
                    "ok": False,
                    "description": raw
                }

            if not result.get("ok"):

                log("")
                log("❌ TELEGRAM API ERROR")
                log("METHOD: " + method)
                log("RESULT: " + str(result))

            return result

    except Exception as e:

        log("")
        log("❌ NETWORK ERROR")
        log(str(e))

        return {
            "ok": False,
            "description": str(e)
        }


# ============================================================
# GET BUSINESS CONNECTION
# ============================================================

async def get_business_connection(
    session,
    connection_id
):

    if not connection_id:
        return None

    if connection_id in business_connections:

        return business_connections[
            connection_id
        ]

    result = await telegram_api(
        session,
        "getBusinessConnection",
        business_connection_id=connection_id
    )

    log("")
    log("🔌 GET BUSINESS CONNECTION")
    log(str(result))

    if result.get("ok"):

        connection = result.get("result")

        business_connections[
            connection_id
        ] = connection

        return connection

    return None


# ============================================================
# PRINT RIGHTS
# ============================================================

async def print_business_info(
    session,
    connection_id
):

    connection = await get_business_connection(
        session,
        connection_id
    )

    if not connection:

        log("❌ BUSINESS CONNECTION НЕ ЗНАЙДЕНО")

        return None

    rights = connection.get(
        "rights"
    ) or {}

    log("")
    log("========================================")
    log("🔌 BUSINESS CONNECTION")
    log("ID: " + str(connection.get("id")))
    log("OWNER CHAT ID: " + str(
        connection.get("user_chat_id")
    ))
    log("ENABLED: " + str(
        connection.get("is_enabled")
    ))
    log("CAN_REPLY: " + str(
        rights.get("can_reply")
    ))
    log("CAN_READ_MESSAGES: " + str(
        rights.get("can_read_messages")
    ))
    log("CAN_DELETE_ALL_MESSAGES: " + str(
        rights.get("can_delete_all_messages")
    ))
    log("CAN_DELETE_SENT_MESSAGES: " + str(
        rights.get("can_delete_sent_messages")
    ))
    log("========================================")

    return connection


# ============================================================
# AUTO RESPONSE
# ============================================================

async def send_auto_response(
    session,
    connection_id,
    chat_id,
    message_id
):

    log("")
    log("🤖 АВТОВІДПОВІДАЧ")

    log(
        "connection_id = " +
        str(connection_id)
    )

    log(
        "chat_id = " +
        str(chat_id)
    )

    log(
        "message_id = " +
        str(message_id)
    )

    if not auto_responder_enabled:

        log("⚠️ Автовідповідач вимкнений")

        return False

    connection = await get_business_connection(
        session,
        connection_id
    )

    if not connection:

        log("❌ Немає Business Connection")

        return False

    if not connection.get(
        "is_enabled"
    ):

        log("❌ Business Connection вимкнений")

        return False

    rights = connection.get(
        "rights"
    ) or {}

    can_reply = rights.get(
        "can_reply",
        False
    )

    log(
        "CAN_REPLY = " +
        str(can_reply)
    )

    if not can_reply:

        log(
            "❌ У ЦЬОГО BUSINESS CONNECTION "
            "НЕМАЄ CAN_REPLY"
        )

        return False

    # --------------------------------------------------------
    # ВІДПОВІДЬ
    # --------------------------------------------------------

    result = await telegram_api(
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

    log("")
    log("📤 AUTO RESPONSE RESULT")
    log(str(result))

    if result.get("ok"):

        log("✅ АВТОВІДПОВІДЬ ВІДПРАВЛЕНА")

        return True

    log(
        "❌ ПОМИЛКА АВТОВІДПОВІДІ: " +
        str(result.get("description"))
    )

    return False


# ============================================================
# BUSINESS MESSAGE
# ============================================================

async def handle_business_message(
    session,
    message
):

    log("")
    log("")
    log("##################################################")
    log("📩 BUSINESS MESSAGE")
    log("##################################################")

    log(
        "FULL UPDATE:"
    )

    log(
        str(message)
    )

    connection_id = message.get(
        "business_connection_id"
    )

    message_id = message.get(
        "message_id"
    )

    chat = message.get(
        "chat"
    ) or {}

    chat_id = chat.get(
        "id"
    )

    sender = message.get(
        "from"
    ) or {}

    sender_id = sender.get(
        "id"
    )

    text = message.get(
        "text",
        ""
    )

    log("")
    log(
        "BUSINESS CONNECTION ID: " +
        str(connection_id)
    )

    log(
        "CHAT ID: " +
        str(chat_id)
    )

    log(
        "MESSAGE ID: " +
        str(message_id)
    )

    log(
        "SENDER ID: " +
        str(sender_id)
    )

    log(
        "TEXT: " +
        str(text)
    )

    # --------------------------------------------------------
    # BUSINESS CONNECTION
    # --------------------------------------------------------

    connection = await print_business_info(
        session,
        connection_id
    )

    if not connection:

        return

    owner_id = connection.get(
        "user_chat_id"
    )

    owner_user = connection.get(
        "user"
    ) or {}

    owner_user_id = owner_user.get(
        "id"
    )

    log("")
    log(
        "BUSINESS OWNER ID: " +
        str(owner_user_id)
    )

    # --------------------------------------------------------
    # ВАЖЛИВО
    #
    # Якщо повідомлення прийшло від клієнта,
    # а не від власника Business-акаунта,
    # відправляємо автовідповідь.
    # --------------------------------------------------------

    if sender_id != owner_user_id:

        log("")
        log(
            "👤 ЦЕ ПОВІДОМЛЕННЯ ВІД КЛІЄНТА"
        )

        await send_auto_response(
            session,
            connection_id,
            chat_id,
            message_id
        )

        # ----------------------------------------------------
        # MUTE
        # ----------------------------------------------------

        if sender_id in muted_users:

            log(
                "🔇 КОРИСТУВАЧ У MUTE"
            )

            result = await telegram_api(
                session,
                "deleteBusinessMessages",

                business_connection_id=connection_id,

                message_ids=[
                    message_id
                ]
            )

            log(
                "DELETE RESULT: " +
                str(result)
            )

        return

    # --------------------------------------------------------
    # ВЛАСНИК BUSINESS
    # --------------------------------------------------------

    log("")
    log(
        "👑 ПОВІДОМЛЕННЯ ВІД ВЛАСНИКА"
    )

    command = text.strip()

    # .mute ID

    if command.startswith(".mute"):

        parts = command.split()

        if len(parts) >= 2:

            try:

                user_id = int(
                    parts[1]
                )

                muted_users.add(
                    user_id
                )

                log(
                    "🔇 MUTED " +
                    str(user_id)
                )

            except:

                log(
                    "❌ Неправильний ID"
                )

        return

    # .umute ID

    if command.startswith(".umute"):

        parts = command.split()

        if len(parts) >= 2:

            try:

                user_id = int(
                    parts[1]
                )

                if user_id in muted_users:

                    muted_users.remove(
                        user_id
                    )

                log(
                    "🔊 UNMUTED " +
                    str(user_id)
                )

            except:

                pass

        return

    # .unmute ID

    if command.startswith(".unmute"):

        parts = command.split()

        if len(parts) >= 2:

            try:

                user_id = int(
                    parts[1]
                )

                if user_id in muted_users:

                    muted_users.remove(
                        user_id
                    )

                log(
                    "🔊 UNMUTED " +
                    str(user_id)
                )

            except:

                pass

        return


# ============================================================
# BUSINESS CONNECTION UPDATE
# ============================================================

async def handle_business_connection(
    connection
):

    connection_id = connection.get(
        "id"
    )

    if connection_id:

        business_connections[
            connection_id
        ] = connection

    log("")
    log("==========================================")
    log("🔌 BUSINESS CONNECTION UPDATE")
    log("==========================================")

    log(
        str(connection)
    )

    rights = connection.get(
        "rights"
    ) or {}

    log(
        "CONNECTION ID: " +
        str(connection_id)
    )

    log(
        "OWNER CHAT ID: " +
        str(connection.get("user_chat_id"))
    )

    log(
        "OWNER USER ID: " +
        str(
            (connection.get("user") or {}).get("id")
        )
    )

    log(
        "ENABLED: " +
        str(connection.get("is_enabled"))
    )

    log(
        "CAN_REPLY: " +
        str(rights.get("can_reply"))
    )

    log("==========================================")


# ============================================================
# NORMAL BOT MESSAGE
# ============================================================

async def handle_normal_message(
    session,
    message
):

    chat = message.get(
        "chat"
    ) or {}

    chat_id = chat.get(
        "id"
    )

    text = message.get(
        "text",
        ""
    ).strip()

    if text == "/start":

        await telegram_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=(
                "🤖 seve bot працює.\n\n"
                "Business auto responder активний."
            )
        )

        return

    if text in (
        "/settings",
        "/seting"
    ):

        status = (
            "🟢 УВІМКНЕНО"
            if auto_responder_enabled
            else
            "🔴 ВИМКНЕНО"
        )

        await telegram_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=(
                "⚙️ Налаштування\n\n"
                "Автовідповідач: " +
                status +
                "\n\n"
                "Текст:\n" +
                auto_responder_text
            )
        )

        return

    if text == "/help":

        await telegram_api(
            session,
            "sendMessage",
            chat_id=chat_id,
            text=(
                "Команди:\n\n"
                "/start\n"
                "/settings\n"
                "/help"
            )
        )

        return


# ============================================================
# PROCESS UPDATE
# ============================================================

async def process_update(
    session,
    update
):

    try:

        log("")
        log("==========================================")
        log("🚀 PROCESS UPDATE")
        log(
            "UPDATE ID: " +
            str(update.get("update_id"))
        )
        log("==========================================")

        # Business connection

        if "business_connection" in update:

            await handle_business_connection(
                update[
                    "business_connection"
                ]
            )

            return

        # Business message

        if "business_message" in update:

            await handle_business_message(
                session,
                update[
                    "business_message"
                ]
            )

            return

        # Edited business message

        if "edited_business_message" in update:

            log(
                "✏️ EDITED BUSINESS MESSAGE"
            )

            log(
                str(
                    update[
                        "edited_business_message"
                    ]
                )
            )

            return

        # Normal message

        if "message" in update:

            await handle_normal_message(
                session,
                update[
                    "message"
                ]
            )

            return

        log(
            "ℹ️ Невідомий тип update"
        )

    except Exception as e:

        log("")
        log(
            "❌ PROCESS UPDATE ERROR"
        )

        log(
            repr(e)
        )


# ============================================================
# WEBHOOK
# ============================================================

async def telegram_webhook(
    request
):

    try:

        update = await request.json()

        log("")
        log("")
        log("==================================================")
        log("📨 TELEGRAM UPDATE RECEIVED")
        log("==================================================")

        log(
            str(update)
        )

        log("==================================================")

        # НЕ create_task.
        # ЧЕКАЄМО повну обробку.

        async with aiohttp.ClientSession() as session:

            await process_update(
                session,
                update
            )

        return web.Response(
            text="OK",
            status=200
        )

    except Exception as e:

        log("")
        log(
            "❌ WEBHOOK ERROR"
        )

        log(
            repr(e)
        )

        return web.Response(
            text="ERROR",
            status=500
        )


# ============================================================
# ROOT
# ============================================================

async def root(
    request
):

    return web.Response(
        text="seve bot is running"
    )


# ============================================================
# HEALTH
# ============================================================

async def health(
    request
):

    return web.Response(
        text="OK"
    )


# ============================================================
# SET WEBHOOK
# ============================================================

async def set_webhook(
    session
):

    if not RENDER_URL:

        log(
            "❌ RENDER_EXTERNAL_URL не знайдений"
        )

        return

    webhook_url = (
        RENDER_URL.rstrip("/")
        +
        "/telegram/webhook/"
        +
        WEBHOOK_SECRET
    )

    log("")
    log(
        "🌐 WEBHOOK:"
    )

    log(
        webhook_url
    )

    result = await telegram_api(
        session,
        "setWebhook",

        url=webhook_url,

        allowed_updates=[
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
            "message",
            "callback_query"
        ]
    )

    log("")
    log(
        "📡 SET WEBHOOK RESULT:"
    )

    log(
        str(result)
    )

    info = await telegram_api(
        session,
        "getWebhookInfo"
    )

    log("")
    log(
        "📡 WEBHOOK INFO:"
    )

    log(
        str(info)
    )


# ============================================================
# BOT INFO
# ============================================================

async def check_bot(
    session
):

    result = await telegram_api(
        session,
        "getMe"
    )

    log("")
    log(
        "🤖 BOT INFO:"
    )

    log(
        str(result)
    )


# ============================================================
# HTTP SERVER
# ============================================================

async def start_server():

    app = web.Application()

    app.router.add_get(
        "/",
        root
    )

    app.router.add_get(
        "/health",
        health
    )

    app.router.add_post(
        "/telegram/webhook/"
        + WEBHOOK_SECRET,
        telegram_webhook
    )

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

    log("")
    log("==================================================")
    log("🌐 SERVER STARTED")
    log("HOST: 0.0.0.0")
    log(
        "PORT: " +
        str(PORT)
    )
    log("==================================================")

    return runner


# ============================================================
# MAIN
# ============================================================

async def main():

    log("")
    log("")
    log("##################################################")
    log("🚀 SEVE BOT START")
    log("##################################################")

    log(
        "PORT = " +
        str(PORT)
    )

    # HTTP server

    await start_server()

    async with aiohttp.ClientSession() as session:

        await check_bot(
            session
        )

        if RENDER_URL:

            log("")
            log(
                "☁️ RENDER MODE"
            )

            await set_webhook(
                session
            )

        else:

            log("")
            log(
                "⚠️ RENDER_EXTERNAL_URL не заданий"
            )

            log(
                "Бот очікує webhook."
            )

    # Не завершуємо процес

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

        log(
            "🛑 BOT STOPPED"
        )

    except Exception as e:

        log(
            "💥 FATAL ERROR: " +
            repr(e)
        )