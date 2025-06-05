from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import openai
import os
import logging

# ====== SETUP LOGGER ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== LOAD ENV VARS LANGSUNG ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_USERNAME = "@askcoinvestasi_bot"

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# ====== MESSAGE HANDLER ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text
    chat = update.effective_chat

    if not text:
        return

    # Log ID & Nama grup untuk identifikasi
    if chat.type in ["group", "supergroup"]:
        group_id = str(chat.id)
        group_name = chat.title
        logger.info(f"Pesan masuk dari grup: {group_name} (ID: {group_id})")
    else:
        logger.info(f"Pesan masuk dari user pribadi: {chat.username or chat.id}")

    logger.info(f"Received message: {text}")

    if text.startswith("/tanya") or BOT_USERNAME in text:
        question = text.replace("/tanya", "").replace(BOT_USERNAME, "").strip()

        if not question:
            await message.reply_text("Pertanyaannya mana, bro? 😅")
            return

        logger.info(f"Question parsed: {question}")

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
