<div align="center">

# 🚀 Purified Futures Divergence Bot

### ⚡ RSI Divergence Scanner for Crypto Futures

Detects Bullish & Bearish RSI Divergence Every 60 Seconds

![Python](https://img.shields.io/badge/Python-3.8+-blue?style=for-the-badge\&logo=python)
![Binance](https://img.shields.io/badge/Binance-Futures-yellow?style=for-the-badge\&logo=binance)
![MEXC](https://img.shields.io/badge/MEXC-Futures-blue?style=for-the-badge)
![Telegram](https://img.shields.io/badge/Telegram-Alerts-26A5E4?style=for-the-badge\&logo=telegram)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

Professional-grade crypto futures signal bot with automatic chart generation and Telegram alerts.

</div>

---

## ✨ Features

* 🔍 Scans Top 40 Gainers + 40 Losers
* 📊 Detects RSI Divergence (LONG & SHORT)
* 📸 Auto-generates 180-candle charts with RSI
* 📱 Sends formatted signals to Telegram
* 🖥️ Dark themed GUI with live logs
* ⚡ Full scan cycle every 60 seconds

---

## 📊 Signal Logic

### 🟢 LONG (Bullish Divergence)

* Price makes Lower Low
* RSI makes Higher Low
* Red candles between peaks
* RSI must rise

### 🔴 SHORT (Bearish Divergence)

* Price makes Higher High
* RSI makes Lower High
* Green candles between peaks
* RSI must fall

---

## 🚀 Installation

### 1️⃣ Clone Repository

```bash
git clone https://github.com/yourusername/crypto-futures-divergence-bot.git
cd crypto-futures-divergence-bot
```

### 2️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 3️⃣ Run Bot

```bash
python divergence_bot.py
```

---

## 📦 Requirements

```txt
ccxt
pandas
numpy
ta
selenium
webdriver-manager
matplotlib
requests
Pillow
pygetwindow
colorama
```

Python 3.8+ required.

---

## 📱 Telegram Setup (Optional)

1. Open Telegram → Search @BotFather
2. Create bot using /newbot
3. Copy Bot Token
4. Add bot to your channel as Admin
5. Add token & channel ID in config:

```python
TELEGRAM_BOT_TOKEN = "YOUR_TOKEN"
TELEGRAM_CHANNEL_ID = "@your_channel"
```

---

## 📁 Project Structure

```
crypto-futures-divergence-bot/
│
├── divergence_bot.py
├── requirements.txt
├── README.md
├── images/
└── config/
```

---

## ⚙️ Configuration Example

```python
SCAN_INTERVAL = 60
CANDLE_COUNT = 180
MIN_PRICE_MOVE_PERCENT = 1.0
```

You can adjust scan speed, candle count, and minimum price movement.

---

## ⚠️ Risk Disclaimer

Trading cryptocurrencies involves high risk.

* You can lose all your capital.
* Leverage increases risk.
* This software is for educational purposes only.
* Use at your own risk.

The developer is not responsible for financial losses.

---

## 🤝 Contributing

Pull requests are welcome.

Possible improvements:

* Add more exchanges (Bybit, OKX)
* Backtesting module
* Auto trading integration
* Multi-timeframe analysis
* Discord alerts

---

## 📜 License

MIT License

---

<div align="center">

⭐ If you find this project useful, please star the repository!

Made with ❤️ for Crypto Traders

</div>
