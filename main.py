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
            logger.info(f"Cleared memory for group {cid}")

def format_price(value: float) -> str:
    return f"${value:,.8f}" if value < 1 else f"${value:,.0f}"

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

# ====== SYMBOL MAP STATIC ======
SYMBOL_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin",
    "DOGEUSDT": "dogecoin",
    "SHIBUSDT": "shiba-inu",
    "ADAUSDT": "cardano",
    "XRPUSDT": "ripple",
    "AVAXUSDT": "avalanche-2",
    "LINKUSDT": "chainlink",
    "MATICUSDT": "matic-network",
    "DOTUSDT": "polkadot",
    "LTCUSDT": "litecoin",
    "TRXUSDT": "tron",
    "ATOMUSDT": "cosmos",
    "NEARUSDT": "near",
    "FILUSDT": "filecoin",
    "ETCUSDT": "ethereum-classic",
    "XLMUSDT": "stellar",
    "HBARUSDT": "hedera-hashgraph",
    "ICPUSDT": "internet-computer",
    "VETUSDT": "vechain",
    "APTUSDT": "aptos",
    "SANDUSDT": "the-sandbox",
    "EGLDUSDT": "elrond-erd-2",
    "XTZUSDT": "tezos",
    "THETAUSDT": "theta-token",
    "MANAUSDT": "decentraland",
    "AAVEUSDT": "aave",
    "FTMUSDT": "fantom",
    "EOSUSDT": "eos",
    "KLAYUSDT": "klay-token",
    "CHZUSDT": "chiliz",
    "GRTUSDT": "the-graph",
    "CRVUSDT": "curve-dao-token",
    "RNDRUSDT": "render-token",
    "FLOWUSDT": "flow",
    "CAKEUSDT": "pancakeswap-token",
    "FXSUSDT": "frax-share",
    "GMXUSDT": "gmx",
    "DYDXUSDT": "dydx",
}

# ====== DATA FETCH & ANALYZE ======
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
    df["vol_mean"] = df["volume"].rolling(20).mean()
    df["vol_std"] = df["volume"].rolling(20).std()
    df["vol_z"] = (df["volume"] - df["vol_mean"]) / df["vol_std"]
    df["H-L"] = df["high"] - df["low"]
    df["H-PC"] = abs(df["high"] - df["close"].shift(1))
    df["L-PC"] = abs(df["low"] - df["close"].shift(1))
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].rolling(14).mean()
    support = df["low"].rolling(5).min().iloc[-1]
    resistance = df["high"].rolling(5).max().iloc[-1]
    last = df.iloc[-1]
    price = last["close"]
    proximity = max(0, 1 - abs(resistance - price) / resistance)
    breakout_raw = (proximity * 1.5 + max(df["vol_z"].iloc[-1], 0) * 0.5)
    breakout_prob = 1 / (1 + np.exp(-breakout_raw))
    breakout_pct = int(breakout_prob * 100)
    tp1 = format_price(resistance + 1.0 * df["ATR"].iloc[-1])
    tp2 = format_price(resistance + 1.5 * df["ATR"].iloc[-1])
    return price, format_price(support), format_price(resistance), breakout_pct, tp1, tp2

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
        price, support, resistance, breakout_pct, tp1, tp2 = analyze_advanced(df)
        msg = f"""
Analisa {symbol} (1D)
Harga sekarang: {format_price(price)}

Support: {support}
Resistance: {resistance}
Breakout Probability: {breakout_pct}%

TP1: {tp1}
TP2: {tp2}
""".strip()
        await update.message.reply_text(msg, reply_to_message_id=update.message.message_id)
    except Exception as e:
        logger.exception("Analisa gagal:")
        await update.message.reply_text("⚠️ Analisa gagal. Coba lagi nanti ya.")

# ====== MAIN ======
def main():
    logger.info("Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.job_queue.run_repeating(lambda *_: asyncio.create_task(clear_idle_memory()), interval=60)
    app.add_handler(CommandHandler("analisa", analisa_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
