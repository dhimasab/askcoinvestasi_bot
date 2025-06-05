import os
import json
import logging
import requests
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ChatMemberUpdated
from telegram.ext import (
    Application,
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    ChatMemberHandler,
    filters,
)
import pandas as pd
import numpy as np
import openai

# ====== LOGGER ======
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== ENV & API ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
BOT_USERNAME = "@askcoinvestasi_bot"
BOT_USERNAME_STRIPPED = BOT_USERNAME.replace("@", "")
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# ====== ALLOWED GROUPS & TRACKING ======
with open("allowed_groups.json") as f:
    ALLOWED_GROUPS = json.load(f)

USAGE_FILE = "group_usage.json"
CHAT_HISTORY = {}
CHAT_LAST_USED = {}

def load_usage():
    return json.load(open(USAGE_FILE)) if os.path.exists(USAGE_FILE) else {}

def save_usage(data):
    json.dump(data, open(USAGE_FILE, "w"))

usage_counter = load_usage()

def update_memory(chat_id: str, question: str, answer: str):
    if chat_id not in CHAT_HISTORY:
        CHAT_HISTORY[chat_id] = []
    CHAT_HISTORY[chat_id].append({"role": "user", "content": question})
    CHAT_HISTORY[chat_id].append({"role": "assistant", "content": answer})
    CHAT_HISTORY[chat_id] = CHAT_HISTORY[chat_id][-10:]
    CHAT_LAST_USED[chat_id] = datetime.utcnow()

def get_memory(chat_id: str):
    return CHAT_HISTORY.get(chat_id, [])

async def clear_idle_memory():
    now = datetime.utcnow()
    for cid in list(CHAT_LAST_USED.keys()):
        if now - CHAT_LAST_USED[cid] > timedelta(minutes=5):
            CHAT_HISTORY.pop(cid, None)
            CHAT_LAST_USED.pop(cid, None)
            logger.info(f"🧹 Cleared memory for group {cid}")

# ====== SERPER BROWSING ======
def search_serper(query):
    try:
        res = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query}
        )
        res.raise_for_status()
        data = res.json()
        return "\n".join(f"- {r['title']}: {r['snippet']}" for r in data.get("organic", [])[:3])
    except Exception as e:
        logger.warning(f"Serper error: {e}")
        return None

# ====== COINGECKO ANALYTICS (DAILY) ======
def get_daily_data(symbol="bitcoin", days=30):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart?vs_currency=usd&days={days}"
    r = requests.get(url)
    if r.status_code != 200:
        raise ValueError("Failed fetch CoinGecko")
    data = r.json()
    df = pd.DataFrame(data["prices"], columns=["timestamp", "close"])
    df["close"] = df["close"].astype(float)
    df["volume"] = [v[1] for v in data["total_volumes"]]
    return df

def analyze(df):
    df["EMA9"] = df["close"].ewm(span=9).mean()
    df["EMA21"] = df["close"].ewm(span=21).mean()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))
    df["vol_avg"] = df["volume"].rolling(20).mean()
    df["vol_spike"] = df["volume"] > 1.5 * df["vol_avg"]
    last = df.iloc[-1]

    trend = "📈 EMA Uptrend" if last["EMA9"] > last["EMA21"] else "📉 EMA Downtrend"
    rsi = f"{last['RSI']:.2f}"
    rsi_state = "🟢 Oversold (RSI<30)" if last["RSI"] < 30 else "🔴 Overbought (RSI>70)" if last["RSI"] > 70 else "⚪️ Netral"
    vol = "📊 Volume Spike" if last["vol_spike"] else "🔕 Volume normal"
    confirm = "✅ Sinyal entry (bullish selaras)" if last["EMA9"] > last["EMA21"] and last["RSI"] < 30 and last["vol_spike"] else "❌ Belum ada sinyal kuat"
    return trend, f"RSI {rsi} → {rsi_state}", vol, confirm

SYMBOL_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin",
    "DOGEUSDT": "dogecoin",
}

async def analisa_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text("Contoh: /analisa BTCUSDT")
            return
        symbol = args[0].upper()
        cg_id = SYMBOL_MAP.get(symbol)
        if not cg_id:
            await update.message.reply_text("Pair tidak dikenali. Contoh yang didukung: BTCUSDT, ETHUSDT")
            return

        df = get_daily_data(cg_id)
        trend, rsi, vol, confirm = analyze(df)
        msg = f"📊 Analisa {symbol} (daily)\n\n{trend}\n{rsi}\n{vol}\n\n{confirm}"
        await update.message.reply_text(msg, reply_to_message_id=update.message.message_id)
    except Exception as e:
        logger.exception("Analisa gagal:")
        await update.message.reply_text("⚠️ Analisa gagal. Coba lagi nanti ya.")

# ====== BOT MASUK GRUP ======
async def handle_bot_added(update: ChatMemberUpdated, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.new_chat_member.status in ["member", "administrator"]:
        chat = update.chat
        if chat.type in ["group", "supergroup"]:
            logger.info(f"✅ Bot ditambahkan ke grup: {chat.title or chat.id}")

# ====== /TANYA, MENTION, REPLY HANDLER ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text
    chat = update.effective_chat
    group_id = str(chat.id)
    group_name = chat.title or chat.username

    if not text:
        return

    logger.info(f"📥 Msg dari {group_name} ({group_id})")

    if chat.type in ["group", "supergroup"] and group_id not in ALLOWED_GROUPS:
        await msg.reply_text("Bot ini belum diaktifkan untuk grup ini 🚫")
        return

    is_command = text.startswith("/tanya")
    is_mention = BOT_USERNAME in text
    is_reply = msg.reply_to_message and msg.reply_to_message.from_user.username == BOT_USERNAME_STRIPPED

    if is_command or is_mention or is_reply:
        question = text.replace("/tanya", "").replace(BOT_USERNAME, "").strip() if not is_reply else msg.reply_to_message.text.strip()

        if not question:
            await msg.reply_text("Pertanyaannya mana, bro? 😅")
            return

        usage = usage_counter.get(group_id, 0)
        if usage >= 100:
            await msg.reply_text("Limit pertanyaan grup ini sudah habis 🚫")
            return

        browse = any(k in question.lower() for k in ["terbaru", "hari ini", "harga", "2025", "pump", "crash"])
        search = search_serper(question) if browse else None

        history = get_memory(group_id)
        messages = [
            {"role": "system", "content": "Kamu adalah asisten kripto dari Coinvestasi. Jawab singkat, santai, dan tidak menjanjikan profit."}
        ] + history

        if browse and search:
            messages.append({"role": "system", "content": f"Hasil pencarian:\n{search}"})
        elif browse:
            messages.append({"role": "system", "content": "Tidak ada hasil pencarian, jawab seadanya."})

        messages.append({"role": "user", "content": question})

        try:
            response = client.chat.completions.create(model="gpt-4o", messages=messages)
            answer = response.choices[0].message.content.strip()
            await msg.reply_text(answer, reply_to_message_id=msg.message_id)

            update_memory(group_id, question, answer)
            usage_counter[group_id] = usage + 1
            save_usage(usage_counter)
        except Exception as e:
            logger.exception("OpenAI error:")
            await msg.reply_text("⚠️ Lagi error, coba nanti ya!")

# ====== MAIN ======
def main():
    logger.info("🚀 Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.job_queue.run_repeating(lambda *_: asyncio.create_task(clear_idle_memory()), interval=60)
    app.add_handler(ChatMemberHandler(handle_bot_added, chat_member_types=["my_chat_member"]))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Regex(r"^/tanya.*"), handle_message))
    app.add_handler(CommandHandler("analisa", analisa_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
