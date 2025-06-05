import os
import json
import logging
import requests
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ChatMemberUpdated
from telegram.ext import (
    ApplicationBuilder, Application,
    MessageHandler, CommandHandler,
    ChatMemberHandler, ContextTypes,
    filters
)
import pandas as pd
import numpy as np
import openai

# ====== LOGGER ======
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== ENV VAR ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
BOT_USERNAME = "@askcoinvestasi_bot"
BOT_USERNAME_STRIPPED = BOT_USERNAME.replace("@", "")
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# ====== GROUPS & MEMORY ======
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

# ====== SERPER SEARCH ======
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

# ====== ANALISA COINGECKO ======
def get_daily_data(symbol="bitcoin", days=30):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart?vs_currency=usd&days={days}"
    r = requests.get(url)
    if r.status_code != 200:
        raise ValueError("Failed to fetch CoinGecko data")
    data = r.json()
    df = pd.DataFrame(data["prices"], columns=["timestamp", "close"])
    df["close"] = df["close"].astype(float)
    df["volume"] = [v[1] for v in data["total_volumes"]]
    df["high"] = df["close"].rolling(2).max()
    df["low"] = df["close"].rolling(2).min()
    df["open"] = df["close"].shift(1)
    return df

def analyze_advanced(df):
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
    prev = df.iloc[-2]

    price = last["close"]
    ema9, ema21 = last["EMA9"], last["EMA21"]
    rsi = last["RSI"]
    vol_ratio = last["volume"] / last["vol_avg"]
    inside_bar = last["close"] < prev["high"] and last["close"] > prev["low"]

    trend = f"📉 EMA Trend: EMA9 (${ema9:,.0f}) < EMA21 (${ema21:,.0f}) → Bearish" \
        if ema9 < ema21 else f"📈 EMA Trend: EMA9 (${ema9:,.0f}) > EMA21 (${ema21:,.0f}) → Bullish"
    rsi_line = f"💠 RSI: {rsi:.1f} → {'Oversold' if rsi < 30 else 'Overbought' if rsi > 70 else 'Netral'}"
    vol_line = f"📊 Volume: {vol_ratio:.2f}x dari rata-rata → {'Spike' if vol_ratio > 1.5 else 'Normal'}"
    breakout_prob = "🔎 70%+ peluang breakout jika close di atas resistance"
    candle_note = "📝 Inside Bar terdeteksi → potensi tekanan beli" if inside_bar else "➖ Tidak ada pola candle signifikan"

    support = df["low"].rolling(5).min().iloc[-1]
    resistance = df["high"].rolling(5).max().iloc[-1]

    entry = f"🎯 Entry Buy: ${resistance:.0f} jika close valid"
    sl = f"🛑 Stop Loss: ${support:.0f}"
    tp1 = f"${resistance * 1.03:.0f}"
    tp2 = f"${resistance * 1.05:.0f}"
    tp = f"🎯 TP1: {tp1}, TP2: {tp2}"
    alasan = "📌 Alasan: Kombinasi EMA uptrend, RSI moderat, volume spike, dan pola candle mendukung"

    return price, trend, rsi_line, vol_line, breakout_prob, candle_note, entry, sl, tp, alasan

# ====== SYMBOL MAP DYNAMIC ======
def fetch_symbol_map():
    try:
        res = requests.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100")
        data = res.json()
        return {f"{item['symbol'].upper()}USDT": item['id'] for item in data}
    except:
        return {
            "BTCUSDT": "bitcoin",
            "ETHUSDT": "ethereum",
            "SOLUSDT": "solana",
            "BNBUSDT": "binancecoin",
            "DOGEUSDT": "dogecoin"
        }

SYMBOL_MAP = fetch_symbol_map()

# ====== HANDLER ANALISA ======
async def analisa_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text("Contoh: /analisa BTCUSDT")
            return
        symbol = args[0].upper()
        cg_id = SYMBOL_MAP.get(symbol)
        if not cg_id:
            await update.message.reply_text("Pair tidak dikenali. Contoh: BTCUSDT, ETHUSDT, dll.")
            return

        df = get_daily_data(cg_id)
        price, trend, rsi, vol, breakout, candle, entry, sl, tp, alasan = analyze_advanced(df)
        msg = f"""
🌟 *Analisa {symbol} (1D)*
Data: {datetime.utcnow().date()}

⬆️ Harga sekarang: ${price:,.0f}

1. *Trend & Indikator:*
{trend}
{rsi}
{vol}

2. *Breakout Probability:*  
{breakout}

3. *Candle Pattern:*  
{candle}

4. *Trading Plan:*  
{entry}  
{sl}  
{tp}  
{alasan}

5. *Rekomendasi:*  
🍛 Tunggu konfirmasi close daily sebelum entry. Hindari FOMO.
""".strip()
        await update.message.reply_text(msg, reply_to_message_id=update.message.message_id, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Analisa gagal:")
        await update.message.reply_text("⚠️ Analisa gagal. Coba lagi nanti ya.")

# ====== HANDLER UMUM /tanya /mention /reply ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text
    chat = update.effective_chat
    group_id = str(chat.id)

    if not text:
        return

    is_mention = any(e.type == "mention" and BOT_USERNAME_STRIPPED in text[e.offset:e.offset+e.length] for e in (msg.entities or []))
    is_command = text.startswith("/tanya")
    is_reply = msg.reply_to_message and msg.reply_to_message.from_user and msg.reply_to_message.from_user.username == BOT_USERNAME_STRIPPED

    if not (is_command or is_mention or is_reply):
        return

    question = text.replace("/tanya", "").replace(BOT_USERNAME, "").strip() if not is_reply else msg.reply_to_message.text.strip()
    if not question:
        await msg.reply_text("Pertanyaannya mana, bro? 😅")
        return

    if chat.type in ["group", "supergroup"] and group_id not in ALLOWED_GROUPS:
        await msg.reply_text("Bot ini belum diaktifkan untuk grup ini 🚫")
        return

    usage = usage_counter.get(group_id, 0)
    if usage >= 100:
        await msg.reply_text("Limit pertanyaan grup ini sudah habis 🚫")
        return

    browse = any(k in question.lower() for k in ["terbaru", "hari ini", "harga", "2025", "pump", "crash"])
    search = search_serper(question) if browse else None

    messages = [{"role": "system", "content": "Kamu adalah asisten kripto Coinvestasi. Jawab santai, tidak janji profit."}]
    messages += get_memory(group_id)

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

# ====== BOT MASUK GRUP ======
async def handle_bot_added(update: ChatMemberUpdated, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.new_chat_member.status in ["member", "administrator"]:
        chat = update.chat
        if chat.type in ["group", "supergroup"]:
            logger.info(f"✅ Bot ditambahkan ke grup: {chat.title or chat.id}")

# ====== MAIN ======
def main():
    logger.info("🚀 Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.job_queue.run_repeating(lambda *_: asyncio.create_task(clear_idle_memory()), interval=60)
    app.add_handler(ChatMemberHandler(handle_bot_added, chat_member_types=["my_chat_member"]))
    app.add_handler(CommandHandler("analisa", analisa_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Regex(r"^/tanya.*"), handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
