# Rajendra Save Restricted Bot
# Owner: RAJENDRA

from pyrogram import Client, filters
from pyrogram.types import Message
from database.db import db


# /setthumb — reply to a photo to set it as custom thumbnail
@Client.on_message(filters.command("setthumb") & filters.private)
async def set_thumb(client: Client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply(
            "**Reply to a photo to set it as your custom thumbnail.**"
        )
    file_id = message.reply_to_message.photo.file_id
    await db.set_thumb(message.from_user.id, file_id)
    await message.reply("**✅ Custom thumbnail saved.**")


# /viewthumb — see current custom thumbnail
@Client.on_message(filters.command("viewthumb") & filters.private)
async def view_thumb(client: Client, message: Message):
    thumb_id = await db.get_thumb(message.from_user.id)
    if not thumb_id:
        return await message.reply(
            "**No custom thumbnail set. Use /setthumb by replying to a photo.**"
        )
    await client.send_photo(
        message.chat.id, thumb_id,
        caption="**Your current custom thumbnail.**"
    )


# /delthumb — remove custom thumbnail
@Client.on_message(filters.command("delthumb") & filters.private)
async def del_thumb(client: Client, message: Message):
    await db.set_thumb(message.from_user.id, None)
    await message.reply("**✅ Custom thumbnail removed.**")


# /settitle <text> — set custom title prefix
@Client.on_message(filters.command("settitle") & filters.private)
async def set_title(client: Client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return await message.reply(
            "**Usage:** `/settitle Your Custom Title`"
        )
    title = parts[1].strip()
    await db.set_custom_title(message.from_user.id, title)
    await message.reply(f"**✅ Custom title set:** `{title}`")


# /viewtitle — view current custom title
@Client.on_message(filters.command("viewtitle") & filters.private)
async def view_title(client: Client, message: Message):
    title = await db.get_custom_title(message.from_user.id)
    if not title:
        return await message.reply(
            "**No custom title set. Use /settitle Your Title**"
        )
    await message.reply(f"**Your current custom title:** `{title}`")


# /deltitle — remove custom title
@Client.on_message(filters.command("deltitle") & filters.private)
async def del_title(client: Client, message: Message):
    await db.set_custom_title(message.from_user.id, None)
    await message.reply("**✅ Custom title removed.**")


# /replace find|replace — add a find/replace rule (| separator so spaces are allowed)
@Client.on_message(filters.command("replace") & filters.private)
async def add_replace(client: Client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or "|" not in parts[1]:
        return await message.reply(
            "**Usage:** `/replace oldword|newword`\n"
            "Use `|` as separator so spaces are preserved."
        )
    find, replace = parts[1].split("|", 1)
    find = find.strip()
    replace = replace.strip()
    if not find:
        return await message.reply("**The `find` part cannot be empty.**")
    await db.add_find_replace(message.from_user.id, find, replace)
    await message.reply(f"**✅ Rule added:** `{find}` → `{replace}`")


# /removeword <word> — strip this word from all captions/text
@Client.on_message(filters.command("removeword") & filters.private)
async def remove_word(client: Client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return await message.reply(
            "**Usage:** `/removeword badword`"
        )
    word = parts[1].strip()
    await db.add_remove_word(message.from_user.id, word)
    await message.reply(f"**✅ Word will be removed:** `{word}`")


# /viewrules — view all find/replace rules and removed words
@Client.on_message(filters.command("viewrules") & filters.private)
async def view_rules(client: Client, message: Message):
    rules = await db.get_find_replace(message.from_user.id)
    removes = await db.get_remove_words(message.from_user.id)

    txt = "**📋 Your Customization Rules**\n\n"
    txt += "**🔁 Find & Replace:**\n"
    if rules:
        for r in rules:
            txt += f"• `{r['find']}` → `{r['replace']}`\n"
    else:
        txt += "_None_\n"

    txt += "\n**🚫 Removed Words:**\n"
    if removes:
        for w in removes:
            txt += f"• `{w}`\n"
    else:
        txt += "_None_"

    await message.reply(txt)


# /clearrules — clear all find/replace rules and removed words
@Client.on_message(filters.command("clearrules") & filters.private)
async def clear_rules(client: Client, message: Message):
    await db.clear_find_replace(message.from_user.id)
    await db.clear_remove_words(message.from_user.id)
    await message.reply("**✅ All customization rules cleared.**")


# Rajendra Save Restricted Bot
# Owner: RAJENDRA