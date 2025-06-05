# 🤖 AskCoinvestasi Bot

A Telegram chatbot assistant built for the Indonesian crypto community. Users can ask questions related to Web3, crypto, blockchain, and investments using either the `/tanya` command or by mentioning `@askcoinvestasi_bot`. The bot replies with friendly, informative answers using the OpenAI API (GPT-4o).

---

## ✨ Features

- ✅ Trigger with `/tanya` command or `@askcoinvestasi_bot` mention.
- 🇮🇩 Responds in casual, educational Indonesian style tailored for Coinvestasi branding.
- 🔐 Ignores unrelated questions (non-crypto, non-Web3 topics).
- 💬 Uses OpenAI’s GPT-4o model for high-quality, real-time responses.
- ⚙️ Deployed with simple polling mechanism, no webhook setup required.

---

## 🧠 How It Works

1. User sends a message starting with `/tanya` or mentions the bot.
2. Bot extracts the question from the message.
3. Sends the prompt to OpenAI with a specific instruction:
   - Casual and informative tone
   - No profit or financial guarantees
   - Only answer questions related to crypto/Web3/blockchain/investments
4. Bot replies in the chat, quoting the original message.

---

## 📦 Requirements

- Python 3.10+
- `python-telegram-bot` v20+
- `openai` SDK
- `dotenv` or equivalent to load env variables

---

## ⚙️ Environment Variables

Set the following environment variables:

| Key                | Description                          |
|--------------------|--------------------------------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from BotFather    |
| `OPENAI_API_KEY`     | API key from OpenAI (GPT-4o access) |

---


## 🧪 Example

**User:**

```
/tanya Apa itu restaking di EigenLayer?
```

**Bot:**

```
Restaking itu kayak lo staking ulang aset yang udah di-stake buat amankan jaringan lain juga. Di EigenLayer, lo bisa restake ETH yang udah di-stake di Ethereum buat support protokol lain — dapet reward tambahan, tapi ada risiko juga, bro. 😄
```

---

## 🔒 Safety & Compliance

- Bot only replies to relevant crypto/Web3 questions.
- No financial advice, predictions, or return guarantees.
- Questions unrelated to crypto will be ignored silently.

---

## 🙌 Credits

Developed by Coinvestasi Team, powered by GPT-4o.
