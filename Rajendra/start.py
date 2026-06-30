# Rajendra Save Restricted Bot
# Owner: RAJENDRA

import os
import asyncio
import re
import time
import logging
import traceback
import pyrogram
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserAlreadyParticipant, InviteHashExpired, UsernameNotOccupied
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import API_ID, API_HASH, ERROR_MESSAGE, LOGIN_SYSTEM, STRING_SESSION, CHANNEL_ID, WAITING_TIME
from database.db import db
from Rajendra.strings import HELP_TXT
from bot import RajendraUser

# Surface runtime errors in the console so they can be diagnosed without
# needing a debugger attached.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("rajendra.bot")

class batch_temp(object):
    IS_BATCH = {}
    BATCH_STEP = {}


def parse_post_range(text: str):
    match = re.search(
        r"(https://t\.me/(?:c/[^/\s]+|b/[^/\s]+|[^/\s]+)/)(\d+)(?:\s*-\s*(\d+))?(?:\?single)?(?:\s+(\d+))?",
        text
    )
    if not match:
        return None, None, None
    link = f"{match.group(1)}{match.group(2)}"
    start_id = int(match.group(2))
    if match.group(3):
        end_id = int(match.group(3))
    elif match.group(4):
        count = int(match.group(4))
        if count < 1:
            count = 1
        end_id = start_id + count - 1
    else:
        end_id = start_id
    return link, start_id, end_id


async def apply_text_rules(user_id: int, text: str) -> str:
    """Apply user's remove-words and find/replace rules to a string."""
    if not text:
        return text
    # 1. Remove words
    removes = await db.get_remove_words(user_id)
    for w in removes:
        if w:
            text = text.replace(w, "")
    # 2. Find & replace
    rules = await db.get_find_replace(user_id)
    for r in rules:
        find = r.get("find")
        replace = r.get("replace", "")
        if find:
            text = text.replace(find, replace)
    # 3. Collapse extra whitespace caused by removals
    text = " ".join(text.split())
    return text


def _html_escape(text: str) -> str:
    """Escape characters that have special meaning in Telegram HTML parse mode."""
    if not text:
        return text
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _build_caption(custom_title, processed_caption, *, replace_original=False):
    """Build the upload caption. Uses HTML bold so the title renders under
    parse_mode=HTML; the custom title is HTML-escaped first.

    When ``replace_original`` is True and a custom title is set, the original
    Telegram caption is dropped — only the title is used.
    """
    if custom_title:
        safe_title = _html_escape(custom_title)
        if replace_original:
            return f"<b>{safe_title}</b>"
        if processed_caption:
            return f"<b>{safe_title}</b>\n\n{processed_caption}"
        return f"<b>{safe_title}</b>"
    return processed_caption or None


async def get_custom_thumb_path(client, user_id: int, acc, msg, msg_type: str):
    """Download custom thumbnail set by user; fall back to original media thumb."""
    thumb_id = await db.get_thumb(user_id)
    if thumb_id:
        try:
            ph_path = await client.download_media(thumb_id)
            if ph_path:
                return ph_path
        except Exception:
            pass
    # Fallback: original media thumbnail
    try:
        if msg_type == "Video" and msg.video and msg.video.thumbs:
            return await acc.download_media(msg.video.thumbs[0].file_id)
        if msg_type == "Document" and msg.document and msg.document.thumbs:
            return await acc.download_media(msg.document.thumbs[0].file_id)
        if msg_type == "Audio" and msg.audio and msg.audio.thumbs:
            return await acc.download_media(msg.audio.thumbs[0].file_id)
    except Exception:
        return None
    return None

def _human_size(num_bytes: float) -> str:
    if num_bytes is None:
        return "?"
    units = ("B", "KB", "MB", "GB", "TB")
    val = float(num_bytes)
    for unit in units:
        if val < 1024 or unit == units[-1]:
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} {unit}"
        val /= 1024
    return f"{num_bytes} B"


def _human_speed(bps: float) -> str:
    if not bps:
        return "0 B/s"
    units = ("B/s", "KB/s", "MB/s", "GB/s")
    val = float(bps)
    for unit in units:
        if val < 1024 or unit == units[-1]:
            if unit == units[-1]:
                return f"{val:.1f} {unit}"
            return f"{val:.1f} {unit}" if unit != "B/s" else f"{int(val)} {unit}"
        val /= 1024
    return f"{bps} B/s"


def _human_eta(seconds: float) -> str:
    if seconds is None or seconds <= 0 or seconds == float("inf"):
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def _format_bar(percent: float, width: int = 20) -> str:
    filled = max(0, min(width, int(percent // (100 / width))))
    return "[" + ("█" * filled) + ("░" * (width - filled)) + "]"


# Per-transfer progress state.
# Layout: { user_id: { message_id: { client, chat_id, status_message_id,
#   direction, start_ts, last_edit_ts, last_text } } }
# Populated by register_progress() before download/upload, drained by
# cleanup_transfer() after the file is uploaded (or the transfer aborted).
_PROGRESS_STATE: dict = {}


def register_progress(message: Message, client, chat_id, status_message_id, direction):
    """Set up a per-transfer progress entry so progress() can find the status message."""
    _PROGRESS_STATE.setdefault(message.from_user.id, {})[message.id] = {
        "client": client,
        "chat_id": chat_id,
        "status_message_id": status_message_id,
        "direction": direction,
        "start_ts": time.time(),
        "last_edit_ts": 0.0,
        "last_text": "",
    }


# progress writer
async def progress(current, total, message, direction):
    # Pyrofork awaits async progress callbacks directly on its event loop
    # (instead of running them in the executor pool), so we can safely
    # `await` the message edit. If this raises, pyrofork's save_file catches
    # it, returns None, and the entire upload blows up with a cryptic
    # "NoneType object has no attribute 'write'" from the TL serializer.
    try:
        if message is None or message.from_user is None:
            return
        if batch_temp.IS_BATCH.get(message.from_user.id):
            raise pyrogram.StopTransmission
        # Some progress sources (e.g. upload chunks) pass None for current/total
        # before the first byte lands. Normalize so we don't divide by None.
        if current is None:
            current = 0
        if total is None:
            total = 0
        now = time.time()
        state = _PROGRESS_STATE.get(message.from_user.id, {}).get(message.id)
        if state is None:
            # No status entry registered — caller forgot to set one up.
            return
        # First chunk: kick the status message so the user sees something
        # immediately even if the throttle window hasn't elapsed.
        is_first_chunk = state["last_edit_ts"] == 0.0
        elapsed = max(1e-6, now - state["start_ts"])
        speed = current / elapsed if current else 0
        percent = (current * 100 / total) if total else 0
        eta = ((total - current) / speed) if (total and speed) else None
        text = (
            f"{_format_bar(percent)} <b>{percent:.1f}%</b>\n"
            f"<b>{_human_size(current)} / {_human_size(total)}</b>\n"
            f"<b>Speed:</b> {_human_speed(speed)}  •  <b>ETA:</b> {_human_eta(eta)}"
        )
        # Throttle network edits to ~1/sec; always edit on completion, and
        # always edit the very first chunk so the bar appears instantly.
        if is_first_chunk or now - state["last_edit_ts"] >= 1.0 or percent >= 100:
            state["last_edit_ts"] = now
            state["last_text"] = text
            client = state["client"]
            chat_id = state["chat_id"]
            status_id = state["status_message_id"]
            full_text = f"<b>{direction}</b>\n{text}"
            await _safe_edit(client, chat_id, status_id, full_text)
    except pyrogram.StopTransmission:
        raise
    except Exception as e:
        # Last-resort: log and swallow so the underlying upload keeps going.
        log.debug("progress callback swallowed exception: %s", e)


async def _safe_edit(client, chat_id, message_id, text):
    try:
        await client.edit_message_text(chat_id, message_id, text, parse_mode=enums.ParseMode.HTML)
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception as e:
        # Message may be deleted (e.g. user cancelled) or content unchanged;
        # neither is worth surfacing. Telegram's "MESSAGE_NOT_MODIFIED" lands here.
        log.debug("progress edit_message_text failed: %s", e)


async def cleanup_transfer(client, message, status_message=None, file_path=None):
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    if status_message:
        try:
            await client.delete_messages(message.chat.id, [status_message.id])
        except Exception:
            pass
    user_state = _PROGRESS_STATE.get(message.from_user.id)
    if user_state is not None:
        user_state.pop(message.id, None)
        if not user_state:
            _PROGRESS_STATE.pop(message.from_user.id, None)


# start command
@Client.on_message(filters.command(["start"]))
async def send_start(client: Client, message: Message):
    buttons = [[
        InlineKeyboardButton("👤 Owner", url = "https://t.me/paulrajend")
    ]]
    reply_markup = InlineKeyboardMarkup(buttons)
    await client.send_message(
        chat_id=message.chat.id, 
        text=f"<b>👋 Hi {message.from_user.mention}, I am Save Restricted Content Bot, I can send you restricted content by its post link.\n\nFor downloading restricted content /login first.\n\nKnow how to use bot by - /help</b>", 
        reply_markup=reply_markup, 
        reply_to_message_id=message.id
    )
    try:
        if not await db.is_user_exist(message.from_user.id):
            await db.add_user(message.from_user.id, message.from_user.first_name)
    except Exception as e:
        print(f"Failed to save user {message.from_user.id}: {e}")
    return


# help command
@Client.on_message(filters.command(["help"]))
async def send_help(client: Client, message: Message):
    await client.send_message(
        chat_id=message.chat.id, 
        text=f"{HELP_TXT}"
    )


@Client.on_message(filters.command(["batch"]) & filters.private)
async def send_batch(client: Client, message: Message):
    batch_temp.BATCH_STEP[message.from_user.id] = {"step": "link"}
    await client.send_message(
        chat_id=message.chat.id,
        text="**Please enter the starting link.**",
        reply_to_message_id=message.id
    )


# cancel command
@Client.on_message(filters.command(["cancel"]))
async def send_cancel(client: Client, message: Message):
    try:
        from Rajendra.generate import cancel_pending_login
        cancel_pending_login(message.from_user.id, message)
    except Exception:
        pass
    batch_temp.BATCH_STEP.pop(message.from_user.id, None)
    batch_temp.IS_BATCH[message.from_user.id] = True
    await client.send_message(
        chat_id=message.chat.id, 
        text="**Task cancelled.**"
    )


# Conversation state for /all
ALL_PENDING = {}

@Client.on_message(filters.command(["all"]) & filters.private & ~filters.forwarded)
async def start_all(client: Client, message: Message):
    user_id = message.from_user.id
    ALL_PENDING[user_id] = {"step": "source"}
    await client.send_message(
        chat_id=message.chat.id,
        text="Send source channel link (e.g. https://t.me/sourcechannel or @channel) or /cancel to abort.",
        reply_to_message_id=message.id
    )

# IMPORTANT: this handler must be in a group NUMBERED HIGHER than the main `save`
# handler. The dispatcher breaks out of the inner handler loop after the first
# handler in a group runs, so any handler registered BEFORE `save` in the same
# group (and with a matching filter) will steal messages away from `save`.
# Putting this in group 1 ensures `save` (group 0) always gets the message first.
@Client.on_message(filters.text & filters.private & ~filters.forwarded, group=1)
async def _all_flow(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in ALL_PENDING:
        return
    text = message.text.strip()
    if text == "/cancel":
        ALL_PENDING.pop(user_id, None)
        return await client.send_message(message.chat.id, "Operation cancelled.", reply_to_message_id=message.id)

    m = re.search(r"(?:https?://)?t\\.me/([A-Za-z0-9_]+)|@([A-Za-z0-9_]+)", text)
    if not m:
        return await client.send_message(message.chat.id, "Invalid link. Send a channel link like https://t.me/channel or @channel", reply_to_message_id=message.id)

    chatname = m.group(1) or m.group(2)
    state = ALL_PENDING[user_id]

    if state["step"] == "source":
        state["source"] = chatname
        state["step"] = "dest"
        return await client.send_message(message.chat.id, "Now send destination channel link (bot must be able to post there).", reply_to_message_id=message.id)

    # Destination received -> start forwarding
    src = state.get("source")
    dest = chatname
    ALL_PENDING.pop(user_id, None)
    await client.send_message(message.chat.id, "Starting forwarding in background. I'll notify when finished.", reply_to_message_id=message.id)
    asyncio.create_task(_forward_all_messages(client, src, dest, message))

async def _forward_all_messages(client: Client, src_chat: str, dest_chat: str, trigger_message: Message):
    try:
        async for msg in client.iter_history(src_chat):
            if not msg:
                continue
            try:
                await client.copy_message(chat_id=dest_chat, from_chat_id=src_chat, message_id=msg.message_id)
            except Exception:
                try:
                    await client.forward_messages(chat_id=dest_chat, from_chat_id=src_chat, message_ids=msg.message_id)
                except Exception:
                    continue
        await trigger_message.reply("Forwarding complete.")
    except Exception as e:
        await trigger_message.reply(f"Forwarding failed: {e}")


@Client.on_message(filters.text & filters.private & ~filters.command(["start", "help", "batch", "cancel", "login", "logout", "setthumb", "viewthumb", "delthumb", "settitle", "viewtitle", "deltitle", "replace", "removeword", "viewrules", "clearrules", "broadcast", "users", "stats"]))
async def save(client: Client, message: Message):
    log.info("save() ENTER user=%s text=%r chat=%s", message.from_user.id, message.text[:80] if message.text else None, message.chat.id)
    try:
        user_id = message.from_user.id
        batch_state = batch_temp.BATCH_STEP.get(user_id)
        if batch_state:
            if batch_state["step"] == "link":
                link, _, _ = parse_post_range(message.text)
                if link is None:
                    await message.reply_text("**Invalid link. Please send a valid Telegram post link.**", reply_to_message_id=message.id)
                    return
                batch_state["step"] = "count"
                batch_state["link"] = link
                await client.send_message(
                    message.chat.id,
                    "**How many files do you want to save?**\n\nSend a number, for example: `10`",
                    reply_to_message_id=message.id
                )
                return
            try:
                count = int(message.text.strip())
            except ValueError:
                await message.reply_text("**Please send only a number, for example: `10`.**", reply_to_message_id=message.id)
                return
            if count < 1:
                await message.reply_text("**Please send a number greater than 0.**", reply_to_message_id=message.id)
                return
            link_text = f"{batch_state['link']} {count}"
            batch_temp.BATCH_STEP.pop(user_id, None)
            await _save_link(client, message, link_text)
            return

        await _save_link(client, message, message.text)
    except Exception as e:
        batch_temp.BATCH_STEP.pop(message.from_user.id, None)
        batch_temp.IS_BATCH[message.from_user.id] = True
        log.exception("Unhandled error in save()")
        if ERROR_MESSAGE == True:
            await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id)


async def _save_link(client: Client, message: Message, text: str):
    # Joining chat
    if ("https://t.me/+" in text or "https://t.me/joinchat/" in text) and LOGIN_SYSTEM == False:
        if RajendraUser is None:
            await client.send_message(message.chat.id, "String Session is not Set", reply_to_message_id=message.id)
            return
        try:
            try:
                await RajendraUser.join_chat(text)
            except Exception as e:
                await client.send_message(message.chat.id, f"Error : {e}", reply_to_message_id=message.id)
                return
            await client.send_message(message.chat.id, "Chat Joined", reply_to_message_id=message.id)
        except UserAlreadyParticipant:
            await client.send_message(message.chat.id, "Chat already Joined", reply_to_message_id=message.id)
        except InviteHashExpired:
            await client.send_message(message.chat.id, "Invalid Link", reply_to_message_id=message.id)
        return
    
    if "https://t.me/" in text:
        if batch_temp.IS_BATCH.get(message.from_user.id) == False:
            return await message.reply_text("**One Task Is Already Processing. Wait For Complete It. If You Want To Cancel This Task Then Use - /cancel**")
        link, fromID, toID = parse_post_range(text)
        if link is None:
            return await message.reply_text("**Invalid link. Please send a valid Telegram post link.**", reply_to_message_id=message.id)
        datas = link.split("/")

        # Send a status message immediately so the user knows the link was received.
        try:
            status_msg = await client.send_message(
                message.chat.id,
                "**🔎 Looking up the message…**",
                reply_to_message_id=message.id,
            )
        except Exception:
            status_msg = None

        if LOGIN_SYSTEM == True:
            user_data = await db.get_session(message.from_user.id)
            if user_data is None:
                await message.reply("**For Downloading Restricted Content You Have To /login First.**")
                return
            api_id_raw = await db.get_api_id(message.from_user.id)
            api_hash = await db.get_api_hash(message.from_user.id)
            if not api_id_raw or not api_hash:
                await message.reply("**Your account is missing API credentials. Please /logout and /login again.**", reply_to_message_id=message.id)
                return
            try:
                api_id = int(api_id_raw)
            except (TypeError, ValueError):
                await message.reply("**Your saved API ID is invalid. Please /logout and /login again.**", reply_to_message_id=message.id)
                return
            try:
                acc = Client("saverestricted", session_string=user_data, api_hash=api_hash, api_id=api_id, in_memory=True)
                await acc.start()
                _user_started_acc = True
            except Exception as e:
                return await message.reply(f"**Your Login Session Expired. So /logout First Then Login Again By - /login**\n\n<code>{e}</code>", reply_to_message_id=message.id)
        else:
            if RajendraUser is None:
                await client.send_message(message.chat.id, f"**String Session is not Set**", reply_to_message_id=message.id)
                return
            acc = RajendraUser
            _user_started_acc = False

        batch_temp.IS_BATCH[message.from_user.id] = False
        for msgid in range(fromID, toID+1):
            if batch_temp.IS_BATCH.get(message.from_user.id): break
            
            # private
            if "https://t.me/c/" in text:
                chatid = int("-100" + datas[4])
                log.info("private link: chatid=%s msgid=%s", chatid, msgid)
                try:
                    await handle_private(client, acc, message, chatid, msgid)
                except Exception as e:
                    log.exception("handle_private failed for c/ link")
                    if ERROR_MESSAGE == True:
                        await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id)
    
            # bot
            elif "https://t.me/b/" in text:
                username = datas[4]
                try:
                    await handle_private(client, acc, message, username, msgid)
                except Exception as e:
                    if ERROR_MESSAGE == True:
                        await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id)
            
            # public
            else:
                username = datas[3]

                try:
                    msg = await client.get_messages(username, msgid)
                except UsernameNotOccupied:
                    await client.send_message(message.chat.id, "The username is not occupied by anyone", reply_to_message_id=message.id)
                    break
                try:
                    # Apply caption rules to public posts too.
                    # copy_message on a media message respects the caption
                    # parameter; on a text-only message it ignores it and sends
                    # the original text. To replace the body with the title on
                    # text-only posts, we send a fresh message instead.
                    custom_title = await db.get_custom_title(message.from_user.id)
                    replace_original = bool(custom_title)
                    if msg.caption:
                        processed = await apply_text_rules(message.from_user.id, msg.caption)
                        caption = _build_caption(custom_title, processed, replace_original=replace_original)
                        await client.copy_message(
                            message.chat.id, msg.chat.id, msg.id,
                            reply_to_message_id=message.id,
                            caption=caption,
                            parse_mode=enums.ParseMode.HTML,
                        )
                    elif msg.text and custom_title:
                        # Text post with custom title: send title alone.
                        safe_title = _html_escape(custom_title)
                        await client.send_message(
                            message.chat.id,
                            f"<b>{safe_title}</b>",
                            reply_to_message_id=message.id,
                            parse_mode=enums.ParseMode.HTML,
                        )
                    elif msg.text:
                        # No custom title — preserve text rules & entities.
                        processed = await apply_text_rules(message.from_user.id, msg.text)
                        await client.send_message(
                            message.chat.id,
                            processed or msg.text,
                            entities=msg.entities,
                            reply_to_message_id=message.id,
                            parse_mode=enums.ParseMode.HTML,
                        )
                    else:
                        await client.copy_message(
                            message.chat.id, msg.chat.id, msg.id,
                            reply_to_message_id=message.id,
                        )
                except:
                    try:
                        await handle_private(client, acc, message, username, msgid)
                    except Exception as e:
                        if ERROR_MESSAGE == True:
                            await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id)

            # wait time
            await asyncio.sleep(WAITING_TIME)
        if LOGIN_SYSTEM == True and _user_started_acc:
            try:
                await acc.stop()
            except Exception:
                pass
        batch_temp.IS_BATCH[message.from_user.id] = True
        if status_msg is not None:
            try:
                await client.delete_messages(message.chat.id, [status_msg.id])
            except Exception:
                pass


# handle private
async def handle_private(client: Client, acc, message: Message, chatid: int, msgid: int):
    try:
        msg: Message = await acc.get_messages(chatid, msgid)
    except Exception as e:
        if ERROR_MESSAGE == True:
            await client.send_message(
                message.chat.id,
                f"**Could not fetch message** `{msgid}` from `{chatid}`.\n"
                f"Make sure your account is a member of that chat.\n\n<code>{e}</code>",
                reply_to_message_id=message.id,
            )
        return
    if msg is None or msg.empty:
        await message.reply(
            f"**Message `{msgid}` not found in this chat.**\n"
            "The post may have been deleted, or the link is invalid for a chat your account can access.",
            reply_to_message_id=message.id,
        )
        return
    msg_type = get_message_type(msg)
    if not msg_type:
        await message.reply(
            "**This message type is not supported.**",
            reply_to_message_id=message.id,
        )
        return
    if CHANNEL_ID:
        try:
            chat = int(CHANNEL_ID)
        except:
            chat = message.chat.id
    else:
        chat = message.chat.id
    if batch_temp.IS_BATCH.get(message.from_user.id): return

    # Load user customization
    custom_title = await db.get_custom_title(message.from_user.id)

    # Process caption / text through user's rules
    base_caption = msg.caption if msg.caption else (msg.text if msg_type == "Text" else None)
    processed_caption = await apply_text_rules(message.from_user.id, base_caption or "")
    # Once a custom title is set, drop the original Telegram caption so only
    # the title appears — user can /deltitle to go back to the original.
    final_caption = _build_caption(custom_title, processed_caption, replace_original=bool(custom_title))

    if "Text" == msg_type:
        try:
            # final_caption is just the title when one is set; otherwise it
            # contains the processed original text.
            text_to_send = final_caption or processed_caption or custom_title or ""
            await client.send_message(
                chat, text_to_send,
                entities=None if custom_title else msg.entities,
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML
            )
            return
        except Exception as e:
            if ERROR_MESSAGE == True:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
            return

    smsg = await client.send_message(
        message.chat.id,
        "<b>⬇️ Downloading…</b>",
        reply_to_message_id=message.id,
        parse_mode=enums.ParseMode.HTML,
    )
    register_progress(message, client, message.chat.id, smsg.id, "⬇️ Downloading…")
    try:
        file = await acc.download_media(msg, progress=progress, progress_args=[message, "⬇️ Downloading…"])
        log.info("download_media returned %r exists=%s", file, os.path.exists(file) if isinstance(file, str) else "n/a")
        if file is None or batch_temp.IS_BATCH.get(message.from_user.id):
            await cleanup_transfer(client, message, smsg, file)
            return
    except Exception as e:
        import traceback as _tb
        log.error("download_media failed\n%s", _tb.format_exc())
        if ERROR_MESSAGE == True:
            await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        await cleanup_transfer(client, message, smsg)
        return
    if batch_temp.IS_BATCH.get(message.from_user.id):
        await cleanup_transfer(client, message, smsg, file)
        return
    register_progress(message, client, message.chat.id, smsg.id, "⬆️ Uploading…")

    if batch_temp.IS_BATCH.get(message.from_user.id):
        await cleanup_transfer(client, message, smsg, file)
        return

    if "Document" == msg_type:
        # Verify the downloaded file still exists before we try to upload it.
        # Pyrofork writes a `.temp` and renames on success; if the cleanup ran
        # early (e.g. user cancelled) we shouldn't attempt an upload that will
        # fail with a confusing "NoneType.write" deep inside save_file.
        if isinstance(file, str) and not os.path.exists(file):
            log.error("send_document skipped: file=%r does not exist on disk", file)
            if ERROR_MESSAGE == True:
                await client.send_message(
                    message.chat.id,
                    "Downloaded file is missing on disk. Please try the link again.",
                    reply_to_message_id=message.id,
                )
            await cleanup_transfer(client, message, smsg, file)
            return
        ph_path = await get_custom_thumb_path(client, message.from_user.id, acc, msg, msg_type)
        # Preserve the original document filename so Telegram shows it instead
        # of an autogenerated placeholder on re-upload.
        original_name = getattr(msg.document, "file_name", None) if msg.document else None
        try:
            await client.send_document(
                chat, file, thumb=ph_path,
                file_name=original_name,
                caption=final_caption,
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML,
                progress=progress, progress_args=[message, "⬆️ Uploading…"]
            )
        except Exception as e:
            import traceback as _tb
            log.error("send_document failed: file=%r exists=%s ph=%r exists=%s\n%s",
                      file, os.path.exists(file) if isinstance(file, str) else "n/a",
                      ph_path, os.path.exists(ph_path) if isinstance(ph_path, str) else "n/a",
                      _tb.format_exc())
            if ERROR_MESSAGE == True:
                await client.send_message(
                    message.chat.id,
                    f"Error: {e}",
                    reply_to_message_id=message.id,
                    parse_mode=enums.ParseMode.HTML,
                )
        if ph_path != None: os.remove(ph_path)

    elif "Video" == msg_type:
        ph_path = await get_custom_thumb_path(client, message.from_user.id, acc, msg, msg_type)
        try:
            await client.send_video(
                chat, file,
                duration=msg.video.duration, width=msg.video.width, height=msg.video.height,
                thumb=ph_path,
                caption=final_caption,
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML,
                progress=progress, progress_args=[message, "⬆️ Uploading…"]
            )
        except Exception as e:
            log.exception("send_video failed for file=%r", file)
            if ERROR_MESSAGE == True:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        if ph_path != None: os.remove(ph_path)

    elif "Animation" == msg_type:
        try:
            await client.send_animation(
                chat, file,
                caption=final_caption,
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML,
                progress=progress, progress_args=[message, "⬆️ Uploading…"]
            )
        except Exception as e:
            log.exception("send_animation failed for file=%r", file)
            if ERROR_MESSAGE == True:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)

    elif "Sticker" == msg_type:
        try:
            await client.send_sticker(chat, file, reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            log.exception("send_sticker failed for file=%r", file)
            if ERROR_MESSAGE == True:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)

    elif "Voice" == msg_type:
        try:
            await client.send_voice(
                chat, file,
                caption=final_caption,
                caption_entities=msg.caption_entities,
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML,
                progress=progress, progress_args=[message, "⬆️ Uploading…"]
            )
        except Exception as e:
            log.exception("send_voice failed for file=%r", file)
            if ERROR_MESSAGE == True:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)

    elif "Audio" == msg_type:
        ph_path = await get_custom_thumb_path(client, message.from_user.id, acc, msg, msg_type)
        try:
            await client.send_audio(
                chat, file, thumb=ph_path,
                caption=final_caption,
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML,
                progress=progress, progress_args=[message, "⬆️ Uploading…"]
            )
        except Exception as e:
            log.exception("send_audio failed for file=%r", file)
            if ERROR_MESSAGE == True:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)
        if ph_path != None: os.remove(ph_path)

    elif "Photo" == msg_type:
        try:
            await client.send_photo(
                chat, file,
                caption=final_caption,
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML,
                progress=progress, progress_args=[message, "⬆️ Uploading…"]
            )
        except Exception as e:
            log.exception("send_photo failed for file=%r", file)
            if ERROR_MESSAGE == True:
                await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML)

    await cleanup_transfer(client, message, smsg, file)


# get the type of message
def get_message_type(msg: pyrogram.types.messages_and_media.message.Message):
    try:
        msg.document.file_id
        return "Document"
    except:
        pass

    try:
        msg.video.file_id
        return "Video"
    except:
        pass

    try:
        msg.animation.file_id
        return "Animation"
    except:
        pass

    try:
        msg.sticker.file_id
        return "Sticker"
    except:
        pass

    try:
        msg.voice.file_id
        return "Voice"
    except:
        pass

    try:
        msg.audio.file_id
        return "Audio"
    except:
        pass

    try:
        msg.photo.file_id
        return "Photo"
    except:
        pass

    try:
        msg.text
        return "Text"
    except:
        pass


# Catch-all that runs on EVERY text message the bot receives in private chats.
# Logs a single line per message so we can see the bot is receiving input.
# This is intentionally in group=-1 so it doesn't compete with the main handlers.
@Client.on_message(filters.text & filters.private, group=-1)
async def _diagnostic_catchall(client: Client, message: Message):
    log.info(
        "DIAG: msg id=%s user=%s chat=%s text=%r",
        message.id,
        message.from_user.id if message.from_user else None,
        message.chat.id,
        (message.text or "")[:80],
    )


# Rajendra Save Restricted Bot
# Owner: RAJENDRA
