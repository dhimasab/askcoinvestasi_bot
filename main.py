from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import openai
import os
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Load environment variables
load_dotenv()

# ====== CONFIG ======
BOT_USERNAME = "@askcoinvestasi_bot"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# ====== KEEP-ALIVE (Flask server for UptimeRobot) ======
app = Flask(__name__)

@app.route('/')
def home():
    print("🔁 Ping masuk ke / — Bot is alive!")
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ====== MESSAGE HANDLER ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text

    if not text:
        return

    if text.startswith("/tanya") or BOT_USERNAME in text:
        question = text.replace("/tanya", "").replace(BOT_USERNAME, "").strip()
        print(f"📩 Pertanyaan masuk: {question}")

        if not question:
            await message.reply_text("Pertanyaannya mana, bro? 😅")
            return

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",  # ⬅️ Ganti ke GPT-4o
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Kamu adalah asisten kripto Indonesia handal dari Coinvestasi. "
                            "Jelaskan dengan bahasa santai, informatif, dan tidak menjanjikan keuntungan. "
                            "Jangan menjawab pertanyaan yang tidak ada hubungannya dengan kripto, blockchain, web3, atau investasi digital."
                        )
                    },
                    {"role": "user", "content": question}
                ]
            )
            answer = response.choices[0].message.content.strip()
            print(f"✅ Jawaban OpenAI: {answer}")
            await message.reply_text(answer, reply_to_message_id=message.message_id)

        except Exception as e:
            print("❌ ERROR dari OpenAI:", e)
            await message.reply_text("Lagi error, coba lagi nanti ya! 😓")

# ====== MAIN BOT RUNNER ======
def main():
    keep_alive()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Regex(r"^/tanya.*"), handle_message))
    print("🚀 Bot Coinvestasi siap jalan!")
    app.run_polling()

if __name__ == "__main__":
    main()
