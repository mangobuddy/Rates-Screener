"""
Configuration: G10 + SGD currencies.
Overnight benchmark rates + government bond yield curves.
"""
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

TENOR_TO_YEARS = {
    "1M": 1/12, "2M": 2/12, "3M": 0.25, "4M": 4/12, "6M": 0.5, "9M": 0.75,
    "1Y": 1, "2Y": 2, "3Y": 3, "4Y": 4, "5Y": 5, "6Y": 6, "7Y": 7,
    "8Y": 8, "9Y": 9, "10Y": 10, "12Y": 12, "15Y": 15, "20Y": 20,
    "25Y": 25, "30Y": 30, "40Y": 40, "50Y": 50,
}

CURRENCIES = {
    "USD": {
        "name": "US Dollar", "country": "United States", "flag": "🇺🇸",
        "overnight": "SOFR", "bond": "US Treasury",
    },
    "EUR": {
        "name": "Euro", "country": "Euro Area", "flag": "🇪🇺",
        "overnight": "€STR", "bond": "Euro Govt (AAA)",
    },
    "GBP": {
        "name": "British Pound", "country": "United Kingdom", "flag": "🇬🇧",
        "overnight": "SONIA", "bond": "UK Gilt",
    },
    "JPY": {
        "name": "Japanese Yen", "country": "Japan", "flag": "🇯🇵",
        "overnight": "TONA", "bond": "JGB",
    },
    "CHF": {
        "name": "Swiss Franc", "country": "Switzerland", "flag": "🇨🇭",
        "overnight": "SARON", "bond": "Swiss Confed.",
    },
    "CAD": {
        "name": "Canadian Dollar", "country": "Canada", "flag": "🇨🇦",
        "overnight": "CORRA", "bond": "Canada Govt",
    },
    "AUD": {
        "name": "Australian Dollar", "country": "Australia", "flag": "🇦🇺",
        "overnight": "Cash Rate", "bond": "ACGB",
    },
    "NZD": {
        "name": "New Zealand Dollar", "country": "New Zealand", "flag": "🇳🇿",
        "overnight": "OCR", "bond": "NZGB",
    },
    "SEK": {
        "name": "Swedish Krona", "country": "Sweden", "flag": "🇸🇪",
        "overnight": "Riksbank Rate", "bond": "SGB",
    },
    "NOK": {
        "name": "Norwegian Krone", "country": "Norway", "flag": "🇳🇴",
        "overnight": "NOWA", "bond": "NGB",
    },
    "SGD": {
        "name": "Singapore Dollar", "country": "Singapore", "flag": "🇸🇬",
        "overnight": "SORA", "bond": "SGS",
    },
}
