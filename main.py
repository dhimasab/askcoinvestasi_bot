from telegram import Update, ChatMemberUpdated
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
    ChatMemberHandler
)
import openai
import os
import json
import logging
import requests

# ====== SETUP LOGGER ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== ENV VARS ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
BOT_USERNAME = "@askcoinvestasi_bot"
BOT_USERNAME_STRIPPED = BOT_USERNAME.replace("@", "")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# ====== FILES ======
USAGE_FILE = "group_usage.json"
MEMORY_FILE = "memory.json"

def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def save_json(data, path):
    with open(path, "w") as f:
        json.dump(data, f)

usage_counter = load_json(USAGE_FILE)
conversation_memory = load_json(MEMORY_FILE)

with open("allowed_groups.json") as f:
    ALLOWED_GROUPS = json.load(f)

TRIGGER_KEYWORDS = [
    "jawab pertanyaan ini", "respon dong", "jawab dong", "responin dong",
    "tolong dijawab", "jawab ini dong", "tolong dijawab ya", "responin deh",
    "coba dijawab", "tolong dong", "minta jawabannya", "bisa bantu jawab?",
    "bantuin jawab ini dong", "ayo jawab", "please", "respon chat di atas",
    "jawab pertanyaan sebelumnya", "jawab chat sebelumnya", "tanggapi dong",
    "jawab"
]

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

# ====== HANDLE BOT ADDED ======
async def handle_bot_added(update: ChatMemberUpdated, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.new_chat_member.status in ['member', 'administrator']:
        chat = update.chat
        if chat.type in ["group", "supergroup"]:
            logger.info(f"✅ Bot ditambahkan ke grup baru: {chat.title or 'Unknown'} (ID: {chat.id})")

# ====== MAIN HANDLER ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text
    chat = update.effective_chat
    if not text: return

    group_id = str(chat.id)
    group_name = chat.title if chat.type in ["group", "supergroup"] else "Private Chat"
    logger.info(f"Pesan masuk dari: {group_name} (ID: {group_id})")

    if chat.type in ["group", "supergroup"] and group_id not in ALLOWED_GROUPS:
        logger.warning(f"❌ Grup tidak diizinkan: {group_name} ({group_id})")
        await message.reply_text("Bot ini belum diaktifkan untuk grup ini 🚫")
        return

    is_command = text.startswith("/tanya")
    is_mention = BOT_USERNAME in text
    is_trigger_phrase = any(kw in text.lower() for kw in TRIGGER_KEYWORDS)
    is_reply = message.reply_to_message and message.reply_to_message.from_user.username == BOT_USERNAME_STRIPPED
    should_respond = is_command or is_mention or (is_reply and is_trigger_phrase) or (is_reply and BOT_USERNAME in text)

    if not should_respond:
        return

    # Extract question or fallback to memory
    question = text.replace("/tanya", "").replace(BOT_USERNAME, "").strip()
    if not question and group_id in conversation_memory:
        question = conversation_memory[group_id]
    elif not question:
        await message.reply_text("Pertanyaannya mana, bro? 😅")
        return

    conversation_memory[group_id] = question
    save_json(conversation_memory, MEMORY_FILE)

    if usage_counter.get(group_id, 0) >= 100:
        logger.info(f"⛔ Limit tercapai untuk grup: {group_name} ({group_id})")
        await message.reply_text("Limit pertanyaan untuk grup ini sudah habis 🚫")
        return

    browsing_needed = any(kw in question.lower() for kw in ["hari ini", "terbaru", "2025", "minggu ini", "kenapa", "harga", "pump", "crash"])
    browsing_context = search_serper(question) if browsing_needed else None

    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "Kamu adalah asisten kripto Indonesia dari Coinvestasi. Gunakan gaya bahasa yang santai, tidak menjanjikan keuntungan, dan edukatif. "
                    "Jawab pendek, relevan, dan fokus ke topik kripto & Web3. Jika user menanyakan info umum atau data waktu nyata, prioritaskan hasil pencarian web."
                )
            }
        ]
        if browsing_context:
            messages.append({"role": "system", "content": f"Berikut hasil pencarian web:\n{browsing_context}"})
        elif browsing_needed and not browsing_context:
            messages.append({"role": "system", "content": "Hasil pencarian web tidak tersedia. Jawab sebisanya dengan pengetahuan umum."})

        messages.append({"role": "user", "content": question})

        response = client.chat.completions.create(model="gpt-4o", messages=messages)
        answer = response.choices[0].message.content.strip()

        logger.info(f"OpenAI response: {answer}")
        await message.reply_text(answer, reply_to_message_id=message.message_id)

        usage_counter[group_id] = usage_counter.get(group_id, 0) + 1
        save_json(usage_counter, USAGE_FILE)

    except Exception as e:
        logger.exception("Terjadi error saat memanggil OpenAI API:")
        await message.reply_text("Lagi error, coba lagi nanti ya! 😓")

# ====== MAIN ======
def main():
    logger.info("Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(ChatMemberHandler(handle_bot_added, chat_member_types=["my_chat_member"]))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Regex(r"^/tanya.*"), handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
