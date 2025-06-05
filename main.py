from telegram import Update, ChatMemberUpdated
from telegram.ext import (
    ApplicationBuilder, MessageHandler, ContextTypes, filters, ChatMemberHandler
)
import openai
import os
import json
import logging
import requests
import time
import asyncio

# ====== SETUP LOGGER ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== ENV VARS ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_USERNAME = "@askcoinvestasi_bot"
BOT_USERNAME_STRIPPED = BOT_USERNAME.replace("@", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# ====== ALLOWED GROUPS ======
with open("allowed_groups.json") as f:
    ALLOWED_GROUPS = json.load(f)

USAGE_FILE = "group_usage.json"
CHAT_MEMORY = {}
LAST_ACTIVITY = {}

def load_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE) as f:
            return json.load(f)
    return {}

def save_usage(data):
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f)

usage_counter = load_usage()

# ====== BROWSING FUNCTION ======
def search_serper(query):
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    data = {"q": query}
    try:
        res = requests.post(url, headers=headers, json=data)
        res.raise_for_status()
        results = res.json()
        snippets = []
        for item in results.get("organic", [])[:3]:
            snippets.append(f"- {item.get('title')}: {item.get('snippet')}")
        return "\n".join(snippets)
    except Exception as e:
        logger.warning(f"Browsing error: {e}")
        return None

# ====== BOT ADDED TO GROUP ======
async def handle_bot_added(update: ChatMemberUpdated, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.new_chat_member.status in ['member', 'administrator']:
        chat = update.chat
        if chat.type in ["group", "supergroup"]:
            logger.info(f"✅ Bot ditambahkan ke grup baru: {chat.title or 'Unknown'} (ID: {chat.id})")

# ====== CLEAR MEMORY IF IDLE ======
async def clear_idle_memory():
    while True:
        now = time.time()
        to_delete = []
        for group_id, last_time in LAST_ACTIVITY.items():
            if now - last_time > 300:  # 5 menit
                to_delete.append(group_id)
        for gid in to_delete:
            CHAT_MEMORY.pop(gid, None)
            LAST_ACTIVITY.pop(gid, None)
            logger.info(f"🧹 Memori grup {gid} dibersihkan karena idle")
        await asyncio.sleep(60)

# ====== MESSAGE HANDLER ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text
    chat = update.effective_chat

    if not text:
        return

    group_id = str(chat.id)
    group_name = chat.title if chat.type in ["group", "supergroup"] else "Private Chat"
    logger.info(f"Pesan masuk dari: {group_name} (ID: {group_id})")
    LAST_ACTIVITY[group_id] = time.time()

    if chat.type in ["group", "supergroup"] and group_id not in ALLOWED_GROUPS:
        logger.warning(f"❌ Grup tidak diizinkan: {group_name} ({group_id})")
        await message.reply_text("Bot ini belum diaktifkan untuk grup ini 🚫")
        return

    is_command = text.startswith("/tanya")
    is_mention = BOT_USERNAME in text
    is_reply = message.reply_to_message and message.reply_to_message.from_user.username == BOT_USERNAME_STRIPPED

    if not (is_command or is_mention or is_reply):
        return

    if is_command or is_mention:
        question = text.replace("/tanya", "").replace(BOT_USERNAME, "").strip()
    elif is_reply:
        question = message.reply_to_message.text.strip()
    else:
        return

    if not question:
        await message.reply_text("Pertanyaannya mana, bro? 😅")
        return

    logger.info(f"Question parsed: {question}")
    usage_count = usage_counter.get(group_id, 0)

    if usage_count >= 100:
        logger.info(f"⛔ Limit tercapai untuk grup: {group_name} ({group_id})")
        await message.reply_text("Limit pertanyaan untuk grup ini sudah habis 🚫")
        return

    browsing_needed = any(k in question.lower() for k in [
        "hari ini", "terbaru", "2025", "minggu ini", "kenapa", "harga", "pump", "crash"
    ])
    browsing_context = search_serper(question) if browsing_needed else None

    chat_history = CHAT_MEMORY.get(group_id, [])[-5:]
    messages = [
        {
            "role": "system",
            "content": (
                "Kamu adalah asisten kripto Indonesia dari Coinvestasi. Gunakan gaya bahasa santai, edukatif, dan tidak menjanjikan keuntungan. "
                "Jawab pendek, relevan, dan fokus ke topik kripto & Web3. Jika user menanyakan info real-time, gunakan hasil pencarian web."
            )
        }
    ]

    messages.extend(chat_history)
    if browsing_needed and browsing_context:
        messages.append({
            "role": "system",
            "content": f"Berikut hasil pencarian web terkini:\n{browsing_context}"
        })
    elif browsing_needed and not browsing_context:
        messages.append({
            "role": "system",
            "content": "Tidak ada hasil pencarian web tersedia, jawab dengan info umum yang masuk akal."
        })

    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        answer = response.choices[0].message.content.strip()
        logger.info(f"OpenAI response: {answer}")
        await message.reply_text(answer, reply_to_message_id=message.message_id)

        usage_counter[group_id] = usage_count + 1
        save_usage(usage_counter)

        # update chat memory
        CHAT_MEMORY.setdefault(group_id, []).append({"role": "user", "content": question})
        CHAT_MEMORY[group_id].append({"role": "assistant", "content": answer})
        CHAT_MEMORY[group_id] = CHAT_MEMORY[group_id][-10:]

    except Exception as e:
        logger.exception("Terjadi error saat memanggil OpenAI API:")
        await message.reply_text("Lagi error, coba lagi nanti ya! 😓")

# ====== MAIN FUNCTION ======
def main():
    logger.info("Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(ChatMemberHandler(handle_bot_added, chat_member_types=["my_chat_member"]))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Regex(r"^/tanya.*"), handle_message))

    app.job_queue.run_repeating(lambda *_: asyncio.create_task(clear_idle_memory()), interval=60, first=60)

    app.run_polling()

if __name__ == "__main__":
    main()
