import asyncio
import sys
import logging
import re
from pathlib import Path

import config
from models import MessageMeta, Chat

existing_dir = Path(__file__).parent.resolve()
sys.path.append(str(existing_dir / "lib"))

from pyrogram import Client, filters, idle
import pyrogram.errors as errors

import pyrogram.handlers as handlers
from pyrogram.types import Message, InputMediaAudio, InputMediaVideo, InputMediaPhoto, InputMediaAnimation, InputMediaDocument
from pyrogram.enums import MessageServiceType, MessageEntityType
from tortoise import Tortoise
from tortoise.functions import Max

from pyrogram.raw.types import UpdatePinnedChannelMessages
# Comment next line to stop receiving outputs
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger('pyrogram').setLevel(logging.INFO)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler(existing_dir / "log.txt", encoding="utf-8")])
ini_path = existing_dir / "config.ini"
token = config.TOKEN
admin_ids = config.ADMIN_IDS
bot = Client(str(existing_dir / "sessions" / "bot"), config.ID, config.HASH, bot_token=config.TOKEN)
receivers = []
assert len(config.HASHES) == len(config.NUMBERS) == len(config.IDS), "There is a problem with bot's user data"
(existing_dir / "sessions").mkdir(exist_ok=True)
for number, id, hash in zip(config.NUMBERS, config.IDS, config.HASHES):
    r = Client(str(existing_dir / "sessions" / str(number).strip("+")), id, hash, phone_number=number)
    receivers.append(r)
chat_lock = {}
# bot.parse_mode = None
# chat_state_map = {}
# chat_code_map = {}


# def pass_state(filter, client, update):
#     return isinstance(update, Message) and chat_state_map.get(update.chat.id) == 'pass'
#
#
# def code_state(filter, client, update):
#     return isinstance(update, Message) and chat_state_map.get(update.chat.id) == 'code'


async def raw_update_handler(client, update, users, chats):
    if isinstance(update, UpdatePinnedChannelMessages) and (chat := await Chat.get_or_none(id=int(f"-100{update.channel_id}"))):
        for message_id in update.messages:
            if meta := await MessageMeta.get_or_none(source_id=message_id, source_chat_id=chat.id):
                if not update.pinned:
                    try:
                        await bot.unpin_chat_message(chat.target, meta.target_id)
                    except errors.RPCError as e:
                        logging.error("unpin error", exc_info=e)


async def message_handler(client: Client, message: Message):
    if chat := await Chat.get_or_none(id=message.chat.id):
        async with chat_lock.setdefault(message.chat.id, asyncio.Lock()):
            target = chat.target
            if message.service:
                if message.service == MessageServiceType.DELETE_CHAT_PHOTO:
                    await bot.delete_chat_photo(target)
                elif message.service == MessageServiceType.NEW_CHAT_PHOTO:
                    photo = await client.download_media(message.chat.photo.big_file_id, in_memory=True)
                    await bot.set_chat_photo(target, photo=photo)
                elif message.service == MessageServiceType.PINNED_MESSAGE:
                    chat = await client.get_chat(message.chat.id)
                    if chat.pinned_message and (meta := await MessageMeta.get_or_none(source_id=chat.pinned_message.id, source_chat_id=chat.id)):
                        await bot.pin_chat_message(meta.target_chat_id, meta.target_id)
                elif message.service == MessageServiceType.NEW_CHAT_TITLE:
                    await Chat.filter(id=message.chat.id).update(name=message.chat.title)
            elif message.media_group_id:
                mlist = await bot.copy_media_group(target, message.chat.id, message.id)
                for m in mlist:
                    await MessageMeta.create(source_id=message.id, source_chat_id=message.chat.id, target_id=m.id, target_chat_id=m.chat.id)
            else:
                reply_id = None
                if message.reply_to_message and (reply_meta := await MessageMeta.get_or_none(source_id=message.reply_to_message.id, source_chat_id=message.chat.id)):
                    reply_id = reply_meta.target_id
                if message.text:
                    text, entities = replace(message.text, message.entities)
                    message.text = text
                    message.entities = entities
                elif message.caption:
                    caption, entities = replace(message.caption, message.caption_entities)
                    message.caption = caption
                    message.caption_entities = entities
                if message.text:
                    func = bot.send_message
                    kwargs = dict(
                        chat_id=chat.target,
                        text=message.text,
                        entities=message.entities,
                        disable_web_page_preview=not message.web_page,
                        reply_to_message_id=reply_id,
                        reply_markup=message.reply_markup
                    )
                elif message.media:
                    kwargs = dict(
                        chat_id=chat.target,
                        caption=message.caption,
                        caption_entities=message.caption_entities,
                        reply_to_message_id=reply_id,
                        reply_markup=message.reply_markup
                    )
                    if message.photo:
                        func = bot.send_photo
                        kwargs["photo"] = await client.download_media(message.photo.file_id, in_memory=True)
                    elif message.audio:
                        func = bot.send_audio
                        kwargs["audio"] = await client.download_media(message.audio.file_id, in_memory=True)
                    elif message.document:
                        func = bot.send_document
                        kwargs["document"] = await client.download_media(message.document.file_id, in_memory=True)
                    elif message.video:
                        func = bot.send_video
                        kwargs["video"] = await client.download_media(message.video.file_id, in_memory=True)
                    elif message.animation:
                        func = bot.send_animation
                        kwargs["animation"] = await client.download_media(message.animation.file_id, in_memory=True)
                    elif message.voice:
                        func = bot.send_voice
                        kwargs["voice"] = await client.download_media(message.voice.file_id, in_memory=True)
                    elif message.sticker:
                        func = message.copy
                        kwargs = dict(
                            chat_id=chat.target
                        )
                    elif message.video_note:
                        func = bot.send_video_note
                        kwargs["video_note"] = await client.download_media(message.video_note.file_id, in_memory=True)
                        kwargs.pop("caption")
                        kwargs.pop("caption_entities")
                    elif message.contact:
                        func = bot.send_contact
                        kwargs = dict(
                            chat_id=chat.target,
                            phone_number=message.contact.phone_number,
                            first_name=message.contact.first_name,
                            last_name=message.contact.last_name,
                            vcard=message.contact.vcard
                        )
                    elif message.location:
                        func = bot.send_location
                        kwargs = dict(
                            chat_id=chat.target,
                            latitude=message.location.latitude,
                            longitude=message.location.longitude,
                        )
                    elif message.venue:
                        func = bot.send_venue
                        kwargs = dict(
                            chat_id=chat.target,
                            latitude=message.venue.location.latitude,
                            longitude=message.venue.location.longitude,
                            title=message.venue.title,
                            address=message.venue.address,
                            foursquare_id=message.venue.foursquare_id,
                            foursquare_type=message.venue.foursquare_type
                        )
                    elif message.poll:
                        func = bot.send_poll
                        kwargs = dict(
                            chat_id=chat.target,
                            question=message.poll.question,
                            options=[opt.text for opt in message.poll.options]
                        )
                    elif message.game:
                        func = bot.send_game
                        kwargs = dict(
                            chat_id=chat.target,
                            game_short_name=message.game.short_name
                        )
                    else:
                        raise ValueError("Unknown media type")
                else:
                    raise ValueError("Can't copy this message")
                while True:
                    try:
                        m = await func(**kwargs)
                        break
                    except errors.FloodWait as e:
                        logging.info(f"Flood error for {e.value} seconds")
                        await asyncio.sleep(e.value)
                await MessageMeta.create(source_id=message.id, source_chat_id=message.chat.id, target_id=m.id, target_chat_id=m.chat.id)
    if message.service in (MessageServiceType.NEW_CHAT_PHOTO, MessageServiceType.DELETE_CHAT_PHOTO) and \
            await Chat.exists(target=message.chat.id):
        await message.delete()
    elif message.service == MessageServiceType.NEW_CHAT_TITLE and await Chat.exists(target=message.chat.id):
        await Chat.filter(target=message.chat.id).update(target_name=message.chat.title)


async def edit_message_handler(client, message: Message):
    meta = await MessageMeta.get_or_none(source_id=message.id, source_chat_id=message.chat.id)
    if meta is None:
        return
    target_message = await bot.get_messages(meta.target_chat_id, meta.target_id)
    if not target_message:
        return
    if target_message.text != message.text:
        caption, entities = replace(message.text, message.entities)
        await bot.edit_message_text(target_message.chat.id, target_message.id, caption, None, entities, not bool(message.web_page), message.reply_markup)
    elif target_message.caption != message.caption:
        caption, entities = replace(message.caption, message.caption_entities)
        await bot.edit_message_caption(target_message.chat.id, target_message.id, caption, None, entities, message.reply_markup)
    elif message.media and message.media != target_message.media:
        if message.video:
            input_media = InputMediaVideo(message.video.file_id)
        elif message.audio:
            input_media = InputMediaAudio(message.audio.file_id)
        elif message.photo:
            input_media = InputMediaPhoto(message.photo.file_id)
        elif message.animation:
            input_media = InputMediaAnimation(message.animation.file_id)
        elif message.document:
            input_media = InputMediaDocument(message.document.file_id)
        else:
            raise ValueError("Unknown message media in edit")
        await client.edit_message_media(target_message.chat.id, target_message.id, input_media, message.reply_markup)
    elif message.video and target_message.video.file_unique_id != message.video.file_unique_id:
        input_media = InputMediaVideo(message.video.file_id)
        await client.edit_message_media(target_message.chat.id, target_message.id, input_media, message.reply_markup, message.video.file_name)
    elif message.audio and target_message.audio.file_unique_id != message.audio.file_unique_id:
        input_media = InputMediaAudio(message.audio.file_id)
        await client.edit_message_media(target_message.chat.id, target_message.id, input_media, message.reply_markup, message.audio.file_name)
    elif message.photo and target_message.photo.file_unique_id != message.photo.file_unique_id:
        input_media = InputMediaPhoto(message.photo.file_id)
        await client.edit_message_media(target_message.chat.id, target_message.id, input_media, message.reply_markup)
    elif message.animation and target_message.animation.file_unique_id != message.animation.file_unique_id:
        input_media = InputMediaAnimation(message.animation.file_id)
        await client.edit_message_media(target_message.chat.id, target_message.id, input_media, message.reply_markup, message.animation.file_name)
    elif message.document and target_message.document.file_unique_id != message.document.file_unique_id:
        input_media = InputMediaDocument(message.document.file_id)
        await client.edit_message_media(target_message.chat.id, target_message.id, input_media, message.reply_markup, message.document.file_name)
    elif target_message.reply_markup != message.reply_markup:
        await bot.edit_message_reply_markup(target_message.chat.id, target_message.id, message.reply_markup)
    else:
        raise ValueError("Can't edit this message")


async def delete_messages_handler(client, messages):
    meta_ids = []
    chat_map = {}
    for message in messages:
        if message.service:
            continue
        if meta := await MessageMeta.get_or_none(source_id=message.id, source_chat_id=message.chat.id):
            chat_map.setdefault(meta.target_chat_id, []).append(meta.target_id)
            meta_ids.append(meta.id)
    logging.debug(f"deleted messages:{len(meta_ids)}")
    if not meta_ids:
        return
    for chat_id, ids in chat_map.items():
        try:
            await bot.delete_messages(chat_id, ids)
        except errors.RPCError as e:
            logging.error("delete error", exc_info=e)
            try:
                await client.delete_messages(chat_id, ids)
            except errors.RPCError as e:
                logging.error("delete error", exc_info=e)
    await MessageMeta.filter(id__in=meta_ids).delete()


@bot.on_message(filters.chat(admin_ids) & filters.command(["del","del_channel", "remove_channel", "deletechannel", "delete_channel", "delchannel", "removechannel"]))
async def delete_channel_command(client, message: Message):
    arg = message.text[message.text.index(" "):].strip()
    if not arg:
        await bot.send_message(message.chat.id, "Please enter the desired channel name or ID in the next command")
        return
    if await Chat.exists(id=arg):
        await Chat.filter(id=arg).delete()
    elif await Chat.filter(name=arg).count() == 1:
        await Chat.filter(name=arg).delete()
    else:
        await bot.send_message(message.chat.id, "A channel with the entered specifications was not found. Note that there should not be more than one channel with the entered name")
        return
    await bot.send_message(message.chat.id, "The entered channel was successfully deleted")


# @bot.on_message(filters.command(["inline"]))
# async def inline_command(client, message: Message):
#     inline = InlineKeyboardMarkup([
#         [InlineKeyboardButton("test data", callback_data="for fun"), InlineKeyboardButton("test url", url="https://t.me/")]
#
#     ])
#     with open(r"D:\Pictures\Ore-Tsushima.-KV (2).jpg", "rb") as file:
#         await bot.send_photo(message.chat.id, file, reply_markup=inline)


@bot.on_message(filters.chat(admin_ids) & filters.command(['start']))
async def start_command(client, message: Message):
    await bot.send_message(message.chat.id, "Welcome to the bot")


@bot.on_message(filters.chat(admin_ids) & filters.command(['channels']))
async def channels_command(client, message: Message):
    text = "چنل‌های اضافه شده\n\n"
    async for chat in Chat.all():
        text += f"{chat.id}|{chat.target}\n"
    await bot.send_message(message.chat.id, text)


@bot.on_message(filters.chat(admin_ids) & filters.command(["addchannel", "add_channel", "add"]))
async def add_channel_command(client, message: Message):
    lines = message.text.split("\n")
    channels = lines[1:]
    if not channels:
        if (i := message.text.find(" ")) != -1:
            arg = message.text[i:].strip()
            channels.append(arg)
    if not channels:
        text = "In the continuation of this command, i.e. the next lines, you need to add channels"
        await bot.send_message(message.chat.id, text)
        return
    good = 0
    for line in channels:
        try:
            number, source, target = line.split(config.SEPARATOR)
            source, target = int(source), int(target)
            target_chat = await bot.get_chat(target)
            receiver = next(iter(r for r in receivers if r.phone_number.strip("+") == number.strip("+")))
            source_chat = await receiver.get_chat(source)
            await Chat.update_or_create(id=source_chat.id, name=source_chat.title, target=target_chat.id, number=number.strip("+"), target_name=target_chat.title)
            good += 1
        except errors.RPCError:
            pass
        except ValueError:
            pass
        except StopIteration:
            pass
    await bot.send_message(message.chat.id, "{}/{} Submitted entry added successfully".format(good, len(channels)))


# @bot.on_message(filters.command(['restart']))
# async def restart_command(client, message: Message):
#     await receiver.restart()
#     await bot.send_message(message.chat.id, "Bot has been restarted successfully")


@bot.on_message(filters.command(['id']))
async def id_command(client, message: Message):
    await message.reply(f"Chat id is: <code>{message.chat.id}</code>")


# @bot.on_message(filters.chat(admin_ids) & filters.command(['leave']))
# async def leave_handler(client, message: Message):
#     arg = message.text and message.text[len("leave") + 2:]
#     if not arg:
#         await bot.send_message(message.chat.id, "Use <i>/leave &lt;channel&gt;</i>\n\n"
#                                                 "<i>&lt;channel&gt;</i> must be a chat link, username or id")
#         return
#     try:
#         # chat = await app.get_chat(arg)
#         await receiver.leave_chat(arg)
#         await message.reply("Successfully left the given chat")
#     except (errors.UsernameNotOccupied, errors.InviteHashExpired, errors.UsernameInvalid):
#         await message.reply(f"Couldn't find a channel with the given argument")
#     except errors.UserNotParticipant:
#         await message.reply(f"Not a member of the given chat")


# @bot.on_message(filters.chat(admin_ids) & filters.command(['join']))
# async def join_handler(message: Message):
#     arg = message.text and message.text[len("join") + 2:]
#     if not arg:
#         await bot.send_message(message.chat.id, "Use <i>/join &lt;channel&gt;</i>\n\n"
#                                                 "<i>&lt;channel&gt;</i> must be a chat link, username or id")
#         return
#     try:
#         await receiver.join_chat(arg)
#         await message.reply("Successfully joined the given chat")
#     except (errors.UsernameNotOccupied, errors.InviteHashExpired, errors.UsernameInvalid, errors.ChannelInvalid):
#         await message.reply(f"Couldn't find a chat with the given argument")
#     except errors.UserNotParticipant:
#         await message.reply(f"Not a member of the given chat")
#
#
# @bot.on_message(filters.create(code_state))
# async def code_handler(client, message: Message):
#     if message.text and message.text.startswith('/start '):
#         chat_state_map.pop(message.chat.id)
#         await start_command(message)
#     if message.text and message.text.isdigit():
#         data = chat_code_map[message.chat.id]
#         try:
#             user = await receiver.sign_in(number, data, message.text)
#             if user:
#                 await message.reply("Signed in successfully!")
#             chat_state_map.pop(message.chat.id)
#             await receiver.restart()
#         except errors.SessionPasswordNeeded as e:
#             await message.reply("Enter 2-Step verification password")
#             chat_state_map[message.chat.id] = 'pass'
#         except Exception as e:
#             await bot.send_message(message.chat.id, f"Signing in failed:\n\n{e}")
#         finally:
#             chat_code_map.pop(message.chat.id)
#     else:
#         await message.reply("Incorrect input. Try again or use <i>/start</i> command to try again")
#
#
# @bot.on_message(filters.create(pass_state))
# async def password_handler(client, message: Message):
#     if message.text and message.text.startswith('/start '):
#         chat_state_map.pop(message.chat.id)
#         await start_command(message)
#     elif message.text:
#         user = None
#         try:
#             user = await receiver.check_password(message.text)
#         except errors.PasswordHashInvalid:
#             await message.reply("Wrong password. Try again or use <i>/start</i> command to try again")
#         except Exception as e:
#             await bot.send_message(message.chat.id, f"Signing in failed:\n\n{e}")
#         if user:
#             await message.reply("Signed in successfully!")
#         chat_state_map.pop(message.chat.id)
#         await receiver.initialize()
#     else:
#         await message.reply("Incorrect input. Try again or use <i>/start</i> command to try again.")


def replace(text: str, entities):
    if entities is None:
        entities = []
    entities = [e for e in entities if e.type != MessageEntityType.MENTION]
    replacements = {re.escape(x): y for x, y in config.REPLACEMENTS.items()}
    replacements[r"@[a-zA-Z0-9_]{5,}"] = config.MENTION
    for x, y in replacements.items():
        for match in reversed(list(re.finditer(x, text))):
            i_start, i_end = match.span()
            text, entities = update_text_and_entities(text, entities, y, i_start, i_end)
    return text, entities or None


def update_text_and_entities(text, entities, subtext, i_start, i_end):
    assert i_start <= i_end
    dif = len(subtext) - (i_end - i_start)
    text = text[:i_start] + subtext + text[i_end:]
    # text = text.encode('utf-16-le')
    new_entities = []
    for entity in entities:
        if entity.offset > i_end:
            entity.offset += dif
        elif entity.offset <= i_start and entity.offset + entity.length >= i_end:
            entity.length += dif
        elif entity.offset + entity.length <= i_start:
            pass
        else:
            continue
        new_entities.append(entity)
    return text, new_entities


async def message_check():
    async for data in MessageMeta.annotate(source_id=Max("source_id")).group_by("source_chat_id").values_list("source_id", "source_chat_id"):
        if not data:
            return
        messages = []
        source_id, source_chat_id = data
        chat = await Chat.get_or_none(id=source_id)
        if chat is None:
            await MessageMeta.filter(source_id=source_id).delete()
            continue
        try:
            receiver = next(iter(r for r in receivers if r.phone_number.strip("+") == chat.number))
        except StopIteration as e:
            logging.exception("error", exc_info=e)
            continue
        limit = 1
        async for last_message in receiver.get_chat_history(source_chat_id, limit):
            if last_message.id > source_id:
                messages.append(last_message)
                limit = last_message.id - source_id - 1
                if limit > 1:
                    async for message in receiver.get_chat_history(source_chat_id, limit, 1):
                        messages.append(message)
        ids = await MessageMeta.filter(source_id__in=[m.id for m in messages], source_chat_id=source_chat_id).values_list("source_id", flat=True)
        for message in reversed([m for m in messages if m.id not in ids]):
            await message_handler(receiver, message)


async def startup():
    global lock
    lock = asyncio.Lock()
    logging.info("Running")
    try:
        for r in receivers:
            print(f"=========={r.phone_number}==========")
            await r.start()
        await bot.start()
        await Tortoise.init(db_url=config.DB, modules={"models": ["models"]}, timezone="Asia/Tehran")
        await Tortoise.generate_schemas(safe=True)
        await message_check()
        for r in receivers:
            r.add_handler(handlers.RawUpdateHandler(raw_update_handler), group=1)
            r.add_handler(handlers.MessageHandler(message_handler, filters.channel))
            r.add_handler(handlers.DeletedMessagesHandler(delete_messages_handler, filters.channel))
            r.add_handler(handlers.EditedMessageHandler(edit_message_handler, filters.channel))
        await idle()
    except KeyboardInterrupt:
        pass
    finally:
        await Tortoise.close_connections()


if __name__ == '__main__':
    bot.run(startup())