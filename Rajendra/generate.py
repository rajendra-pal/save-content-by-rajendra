# Rajendra Save Restricted Bot
# Owner: RAJENDRA

import asyncio
import traceback
from pyrogram.types import Message
from pyrogram import Client, filters
from pyrogram.errors import (
    ApiIdInvalid,
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    SessionPasswordNeeded,
    PasswordHashInvalid,
)
from config import API_ID, API_HASH
from database.db import db

SESSION_STRING_SIZE = 351


@Client.on_message(filters.private & ~filters.forwarded & filters.command(["logout"]))
async def logout(client, message):
    user_data = await db.get_session(message.from_user.id)
    if user_data is None:
        return
    await db.set_session(message.from_user.id, session=None)
    await message.reply("**Logout Successfully** ♦")


# ---------- Manual conversation helper (no pyromod dependency) ----------

# Maps a login "key" (user_id) -> asyncio.Future that resolves with the user's next message.
_PENDING_LOGIN: dict = {}

def _is_pending_login_reply(_, __, message: Message):
    return bool(message.from_user and message.from_user.id in _PENDING_LOGIN)


def cancel_pending_login(user_id: int, message: Message):
    fut = _PENDING_LOGIN.pop(user_id, None)
    if fut is not None and not fut.done():
        fut.set_result(message)
        return True
    return False


@Client.on_message(
    filters.private
    & ~filters.forwarded
    & filters.text
    & filters.create(_is_pending_login_reply)
    & ~filters.command([
        "start", "help", "batch", "cancel", "login", "logout",
        "setthumb", "viewthumb", "delthumb",
        "settitle", "viewtitle", "deltitle",
        "replace", "removeword", "viewrules", "clearrules",
        "broadcast", "users", "stats",
    ])
)
async def _capture_login_reply(client: Client, message: Message):
    """Resolve a pending /login conversation step when the user replies."""
    fut = _PENDING_LOGIN.pop(message.from_user.id, None)
    if fut is not None and not fut.done():
        fut.set_result(message)


async def _ask(bot: Client, user_id: int, prompt: str, timeout: int = 600, cleanup_ids=None):
    """Replacement for bot.ask() that doesn't depend on pyromod."""
    prompt_msg = await bot.send_message(user_id, prompt)
    if cleanup_ids is not None:
        cleanup_ids.append(prompt_msg.id)
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    _PENDING_LOGIN[user_id] = fut
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        _PENDING_LOGIN.pop(user_id, None)
        raise


# ---------- /login ----------

@Client.on_message(filters.private & ~filters.forwarded & filters.command(["login"]))
async def main(bot: Client, message: Message):
    try:
        await _login_flow(bot, message)
    except asyncio.TimeoutError:
        try:
            await message.reply("**Login timed out. Please /login again.**")
        except Exception:
            pass
    except Exception as e:
        traceback.print_exc()
        try:
            await message.reply(f"<b>Login failed:</b> <code>{e}</code>\n\nPlease try /login again.")
        except Exception:
            pass


async def _login_flow(bot: Client, message: Message):
    # If a /login is already in progress for this user, cancel the old one.
    old = _PENDING_LOGIN.pop(message.from_user.id, None)
    if old is not None and not old.done():
        old.cancel()

    user_data = await db.get_session(message.from_user.id)
    if user_data is not None:
        await message.reply("**Your Are Already Logged In. First /logout Your Old Session. Then Do Login.**")
        return

    user_id = int(message.from_user.id)
    api_id = API_ID
    api_hash = API_HASH
    cleanup_ids = [message.id]

    # 1. Phone number
    phone_number_msg = await _ask(
        bot, user_id,
        "<b>Please send your phone number which includes country code</b>\n"
        "<b>Example:</b> <code>+13124562345, +9171828181889</code>\n\n"
        "<i>Send /cancel to abort.</i>",
        timeout=600,
        cleanup_ids=cleanup_ids,
    )
    cleanup_ids.append(phone_number_msg.id)
    if phone_number_msg.text and phone_number_msg.text.strip() == "/cancel":
        return await phone_number_msg.reply("<b>process cancelled !</b>")
    phone_number = phone_number_msg.text.strip()

    client = Client(name="login_tmp", api_id=api_id, api_hash=api_hash, in_memory=True)
    await client.connect()
    try:
        try:
            code = await client.send_code(phone_number)
        except PhoneNumberInvalid:
            return await phone_number_msg.reply("`PHONE_NUMBER` **is invalid.**")

        # 2. OTP
        sending_otp_msg = await phone_number_msg.reply("Sending OTP...")
        cleanup_ids.append(sending_otp_msg.id)
        phone_code_msg = await _ask(
            bot, user_id,
            "Please check for an OTP in official telegram account. If you got it, send OTP here after reading the below format.\n\n"
            "If OTP is `12345`, **please send it as** `1 2 3 4 5`.\n\n"
            "**Enter /cancel to cancel The Procces**",
            timeout=600,
            cleanup_ids=cleanup_ids,
        )
        cleanup_ids.append(phone_code_msg.id)
        if phone_code_msg.text and phone_code_msg.text.strip() == "/cancel":
            return await phone_code_msg.reply("<b>process cancelled !</b>")

        try:
            phone_code = phone_code_msg.text.replace(" ", "").strip()
            await client.sign_in(phone_number, code.phone_code_hash, phone_code)
        except PhoneCodeInvalid:
            return await phone_code_msg.reply("**OTP is invalid.**")
        except PhoneCodeExpired:
            return await phone_code_msg.reply("**OTP is expired.**")
        except SessionPasswordNeeded:
            # 3. 2FA password
            two_step_msg = await _ask(
                bot, user_id,
                "**Your account has enabled two-step verification. Please provide the password.**\n\n"
                "**Enter /cancel to cancel The Procces**",
                timeout=300,
                cleanup_ids=cleanup_ids,
            )
            cleanup_ids.append(two_step_msg.id)
            if two_step_msg.text and two_step_msg.text.strip() == "/cancel":
                return await two_step_msg.reply("<b>process cancelled !</b>")
            try:
                await client.check_password(password=two_step_msg.text.strip())
            except PasswordHashInvalid:
                return await two_step_msg.reply("**Invalid Password Provided**")

        string_session = await client.export_session_string()
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    if not string_session or len(string_session) < SESSION_STRING_SIZE:
        return await message.reply("<b>invalid session sring</b>")

    try:
        await db.set_session(message.from_user.id, session=string_session)
        await db.set_api_id(message.from_user.id, api_id=api_id)
        await db.set_api_hash(message.from_user.id, api_hash=api_hash)
    except Exception as e:
        return await message.reply_text(f"<b>ERROR IN LOGIN:</b> `{e}`")

    try:
        await bot.delete_messages(message.chat.id, cleanup_ids)
    except Exception:
        pass

    await bot.send_message(
        message.from_user.id,
        "<b>Account Login Successfully.\n\n"
        "If You Get Any Error Related To AUTH KEY Then /logout first and /login again</b>",
    )


# Rajendra Save Restricted Bot
# Owner: RAJENDRA
