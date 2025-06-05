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
BOT_USERNAME = "@askcoinvestasi_bot"
SERPER_API_KEY = os.getenv("SERPER_API_KEY") or "8e28cf714810f94847d29700c9e3be11c2d1186d"

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# ====== ALLOWED GROUPS ======
with open("allowed_groups.json") as f:
    ALLOWED_GROUPS = json.load(f)

USAGE_FILE = "group_usage.json"

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

# ====== BOT DITAMBAHKAN KE GRUP ======
async def handle_bot_added(update: ChatMemberUpdated, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.new_chat_member.status in ['member', 'administrator']:
        chat = update.chat
        if chat.type in ["group", "supergroup"]:
            logger.info(f"✅ Bot ditambahkan ke grup baru: {chat.title or 'Unknown'} (ID: {chat.id})")

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

    if chat.type in ["group", "supergroup"] and group_id not in ALLOWED_GROUPS:
        logger.warning(f"❌ Grup tidak diizinkan: {group_name} ({group_id})")
        await message.reply_text("Bot ini belum diaktifkan untuk grup ini 🚫")
        return

    if text.startswith("/tanya") or BOT_USERNAME in text:
        question = text.replace("/tanya", "").replace(BOT_USERNAME, "").strip()

        if not question:
            await message.reply_text("Pertanyaannya mana, bro? 😅")
            return

        logger.info(f"Question parsed: {question}")
        usage_count = usage_counter.get(group_id, 0)

        if usage_count >= 100:
            logger.info(f"⛔ Limit tercapai untuk grup: {group_name} ({group_id})")
            await message.reply_text("Limit pertanyaan untuk grup ini sudah habis 🚫")
            return

        browsing_needed = any(kw in question.lower() for kw in [
            "hari ini", "minggu ini", "kenapa", "harga bitcoin", "berita", "terkini", "2025"
        ])
        browsing_context = search_serper(question) if browsing_needed else None

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Kamu adalah asisten kripto Indonesia dari Coinvestasi. "
                        "Gunakan gaya bahasa yang santai, tidak menjanjikan keuntungan, dan edukatif. "
                        "Jawab secara singkat, relevan, dan tetap di topik kripto dan Web3."
                    )
                }
            ]

            if browsing_needed and browsing_context:
                messages.append({"role": "system", "content": f"Hasil pencarian terkini:\n{browsing_context}"})

            elif browsing_needed and not browsing_context:
                fallback_note = (
                    "❗ Saat ini aku nggak bisa akses data real-time. Tapi untuk topik seperti ini, kamu bisa cek situs seperti CoinGecko, CoinMarketCap, atau CryptoPanic.\n\n"
                    "Kalau kamu mau, aku bantu jawab berdasarkan pemahaman umum ya."
                )
                await message.reply_text(fallback_note)
                messages.append({
                    "role": "system",
                    "content": (
                        "Data pencarian tidak tersedia, jawab dengan pengetahuan umum yang relevan dan edukatif."
                    )
                })

            messages.append({"role": "user", "content": question})

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )

            answer = response.choices[0].message.content.strip()
            logger.info(f"OpenAI response: {answer}")
            await message.reply_text(answer, reply_to_message_id=message.message_id)

            usage_counter[group_id] = usage_count + 1
            save_usage(usage_counter)

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

    app.run_polling()

if __name__ == "__main__":
    main()
