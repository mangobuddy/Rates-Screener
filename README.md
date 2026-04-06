# 📈 Rates Screener — Telegram Bot

Free, open-source Telegram bot for government bond yields and overnight benchmark rates across **G10 + SGD**.

## What It Does

| Command | Result |
|---------|--------|
| `/rates SGD` | SORA + SGS yield curve across all tenors + chart |
| `/rates USD` | SOFR + full US Treasury curve (1M–30Y) + chart |
| `/list` | Clickable buttons for all 11 currencies |
| `/all` | Overnight rate table for all currencies |
| Type `EUR` | Auto-detects currency codes |

### Coverage

| CCY | Overnight | Govt Bond Curve | Source |
|-----|-----------|-----------------|--------|
| 🇺🇸 USD | SOFR | UST 1M–30Y (11 tenors) | NY Fed + FRED |
| 🇪🇺 EUR | €STR | Euro AAA 3M–30Y (11 tenors) | ECB Data Portal |
| 🇬🇧 GBP | SONIA | UK Gilts | Bank of England + FRED |
| 🇯🇵 JPY | TONA | JGB 1Y–40Y (11 tenors) | MoF Japan CSV |
| 🇨🇭 CHF | SARON | Swiss Confed. | SNB + FRED |
| 🇨🇦 CAD | CORRA | Canada Govt 2Y–30Y (6 tenors) | Bank of Canada API |
| 🇦🇺 AUD | Cash Rate | ACGB | RBA + FRED |
| 🇳🇿 NZD | OCR | NZGB | RBNZ + FRED |
| 🇸🇪 SEK | Riksbank Rate | SGB 2Y–10Y | Riksbank API |
| 🇳🇴 NOK | NOWA | NGB 3Y–10Y | Norges Bank + FRED |
| 🇸🇬 SGD | SORA | SGS 6M–30Y | MAS Statistics API |

---

## Setup (5 minutes)

### 1. Get API Keys (both free)

**Telegram Bot Token:**
Open Telegram → search `@BotFather` → send `/newbot` → follow prompts → copy token

**FRED API Key:**
Go to https://fred.stlouisfed.org/docs/api/api_key.html → create account → copy key

### 2. Configure

```bash
cd rates-bot
cp .env.example .env
# Edit .env and paste your two keys
```

### 3. Install & Run

```bash
pip install -r requirements.txt
python run.py
```

Open Telegram, find your bot, send `/start`.

---

## Hosting

### Option A: tmux (simplest)
```bash
tmux new -s ratesbot
python run.py
# Ctrl+B then D to detach
```

### Option B: Docker
```bash
docker build -t rates-bot .
docker run -d --name rates-bot --restart unless-stopped --env-file .env rates-bot
```

### Option C: systemd (Linux VPS)
```ini
# /etc/systemd/system/rates-bot.service
[Unit]
Description=Rates Screener Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/rates-bot
ExecStart=/usr/bin/python3 run.py
Restart=always
EnvironmentFile=/home/ubuntu/rates-bot/.env

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now rates-bot
```

### Option D: Railway.app (free tier)
Push to GitHub → railway.app → Deploy from GitHub → add env vars → done.

### Cheap VPS options
| Provider | Cost |
|----------|------|
| Oracle Cloud | Free (ARM) |
| Hetzner | €4/mo |
| DigitalOcean | $4/mo |
| Fly.io | Free tier |

---

## Project Structure

```
rates-bot/
├── run.py                  # Entry point
├── requirements.txt
├── Dockerfile
├── .env.example
└── src/
    ├── config.py           # Currency definitions
    ├── data_sources.py     # All data fetching (11 currencies)
    ├── curve_builder.py    # PCHIP interpolation
    ├── chart_generator.py  # Matplotlib charts
    └── bot.py              # Telegram handlers
```

## Adding a Currency

1. Add entry to `CURRENCIES` in `src/config.py`
2. Write a `fetch_xxx()` function in `src/data_sources.py`
3. Add to `_DISPATCH` dict

---

## License

MIT
