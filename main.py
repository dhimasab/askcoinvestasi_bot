from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import openai
import os
from dotenv import load_dotenv

# Load environment variables from .env file (for local testing)
load_dotenv()

# ====== CONFIG ======
BOT_USERNAME = "@askcoinvestasi_bot"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# ====== MESSAGE HANDLER ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text

    if not text:
        return

    # Trigger jika ada /tanya atau @mention bot
    if text.startswith("/tanya") or BOT_USERNAME in text:
        # Bersihkan teks dari trigger
        question = text.replace("/tanya", "").replace(BOT_USERNAME, "").strip()

        if not question:
            await message.reply_text("Pertanyaannya mana, bro? 😅")
            return

        try:
            # Kirim pertanyaan ke OpenAI
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Kamu adalah asisten kripto Indonesia handal dari Coinvestasi. Jelaskan dengan bahasa santai, informatif, dan tidak menjanjikan keuntungan. Jangan menjawab pertanyaan-pertanyaan yang tidak ada hubungannya dengan web3, kripto, blokchain, investasi dan lainnya yang berhubungan."},
                    {"role": "user", "content": question}
                ]
            )
            answer = response.choices[0].message.content.strip()
            await message.reply_text(answer, reply_to_message_id=message.message_id)

        except Exception as e:
            await message.reply_text("Lagi error, coba lagi nanti ya! 😓")

# ====== MAIN BOT RUNNER ======
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Regex(r"^/tanya.*"), handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
