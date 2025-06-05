from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import openai
import os
import json
import logging

# ====== SETUP LOGGER ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== LOAD ENV VARS ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_USERNAME = "@askcoinvestasi_bot"

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# ====== LOAD ALLOWED GROUPS ======
with open("allowed_groups.json") as f:
    ALLOWED_GROUPS = json.load(f)

# ====== LOAD USAGE TRACKING ======
USAGE_FILE = "group_usage.json"

def load_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE) as f:
            return json.load(f)
    else:
        return {}

def save_usage(usage_data):
    with open(USAGE_FILE, "w") as f:
        json.dump(usage_data, f)

usage_counter = load_usage()

# ====== MESSAGE HANDLER ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text
    chat = update.effective_chat

    if not text:
        return

    # Group Info
    group_id = str(chat.id)
    group_name = chat.title if chat.type in ["group", "supergroup"] else "Private Chat"
    logger.info(f"Pesan masuk dari: {group_name} (ID: {group_id})")

    # Only allow whitelisted groups
    if chat.type in ["group", "supergroup"] and group_id not in ALLOWED_GROUPS:
        logger.warning(f"Grup tidak diizinkan: {group_name} ({group_id})")
        await message.reply_text("Bot ini belum diaktifkan untuk grup ini 🚫")
        return

    # Check if message is a trigger
    if text.startswith("/tanya") or BOT_USERNAME in text:
        question = text.replace("/tanya", "").replace(BOT_USERNAME, "").strip()

        if not question:
            await message.reply_text("Pertanyaannya mana, bro? 😅")
            return

        logger.info(f"Question parsed: {question}")

        # Check usage limit
        usage_count = usage_counter.get(group_id, 0)
        if usage_count >= 100:
            logger.info(f"Limit tercapai untuk grup: {group_name} ({group_id})")
            await message.reply_text("Limit 100 pertanyaan untuk grup ini sudah habis 🚫")
            return

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Kamu adalah asisten kripto Indonesia handal dari Coinvestasi. "
                            "Jelaskan dengan bahasa santai, informatif, dan tidak menjanjikan keuntungan. "
                            "Jangan menjawab pertanyaan-pertanyaan yang tidak ada hubungannya dengan web3, kripto, blockchain, "
                            "investasi dan lainnya yang berhubungan."
                        )
                    },
                    {"role": "user", "content": question}
                ]
            )
            answer = response.choices[0].message.content.strip()
            logger.info(f"OpenAI response: {answer}")
            await message.reply_text(answer, reply_to_message_id=message.message_id)

            # Update usage counter
            usage_counter[group_id] = usage_count + 1
            save_usage(usage_counter)

        except Exception as e:
            logger.exception("Terjadi error saat memanggil OpenAI API:")
            await message.reply_text("Lagi error, coba lagi nanti ya! 😓")

# ====== MAIN FUNCTION ======
def main():
    logger.info("Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Regex(r"^/tanya.*"), handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
