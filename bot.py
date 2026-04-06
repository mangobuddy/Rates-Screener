"""
Rates Screener Telegram Bot.
  /start        — Welcome
  /rates <CCY>  — Full report + chart
  /list         — Clickable currency buttons
  /all          — Quick overnight summary for all
  /help         — Usage guide
  Or just type a currency code like USD, SGD, EUR
"""
import logging, asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)
from telegram.constants import ParseMode

from src.config import TELEGRAM_BOT_TOKEN, CURRENCIES
from src.data_sources import fetch_rates
from src.chart_generator import generate_curve_chart, generate_summary_text

logging.basicConfig(format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to the Rates Screener Bot\\!*\n\n"
        "Get government bond yields and benchmark rates\n"
        "for G10 \\+ SGD currencies — all from free sources\\.\n\n"
        "  `/rates SGD` — SGS yields \\+ SORA \\+ curve chart\n"
        "  `/rates USD` — US Treasury curve \\+ SOFR\n"
        "  `/list` — Clickable buttons for all currencies\n"
        "  `/all` — Quick overnight rate summary\n\n"
        "Or just type a currency code\\: `USD` `EUR` `SGD`",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ccys = ", ".join(sorted(CURRENCIES.keys()))
    await update.message.reply_text(
        "📖 *Usage Guide*\n\n"
        "`/rates <CCY>` — Overnight rate \\+ govt bond yields \\+ chart\n"
        "`/list` — Clickable currency buttons\n"
        "`/all` — Overnight rates for all 11 currencies\n\n"
        f"*Supported:* `{ccys}`\n\n"
        "*Data sources:*\n"
        "  USD: NY Fed \\+ FRED\n"
        "  EUR: ECB Data Portal\n"
        "  GBP: Bank of England\n"
        "  JPY: Ministry of Finance Japan\n"
        "  CAD: Bank of Canada API\n"
        "  AUD: RBA \\+ FRED\n"
        "  SEK: Riksbank API\n"
        "  SGD: MAS Statistics API\n"
        "  Others: Central banks \\+ FRED",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    buttons = []
    row = []
    for i, ccy in enumerate(sorted(CURRENCIES.keys())):
        cfg = CURRENCIES[ccy]
        row.append(InlineKeyboardButton(f"{cfg['flag']} {ccy}", callback_data=f"r:{ccy}"))
        if len(row) == 3 or i == len(CURRENCIES) - 1:
            buttons.append(row); row = []
    await update.message.reply_text(
        "🌍 *Select a currency:*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching overnight rates for all currencies…")
    loop = asyncio.get_event_loop()
    lines = ["```"]
    lines.append(f"{'CCY':<5} {'Rate':>10}  {'Name':<14}")
    lines.append(f"{'─'*32}")
    for ccy in sorted(CURRENCIES.keys()):
        try:
            data = await loop.run_in_executor(None, fetch_rates, ccy)
            ovn = data.get("overnight", {})
            r = ovn.get("rate")
            n = ovn.get("name", CURRENCIES[ccy]["overnight"])
            lines.append(f"{ccy:<5} {f'{r:.4f}%' if r is not None else 'N/A':>10}  {n:<14}")
        except Exception:
            lines.append(f"{ccy:<5} {'Error':>10}")
    lines.append("```")
    lines.append("\n_Use /rates <CCY> for full curve_")
    await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_rates(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Please specify a currency\\. Example: `/rates SGD`",
                                        parse_mode=ParseMode.MARKDOWN_V2)
        return
    await _send_rates(update, ctx.args[0].upper().strip(), callback=False)


async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("r:"):
        await _send_rates(update, q.data.split(":")[1], callback=True)


async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    if text in CURRENCIES:
        await _send_rates(update, text, callback=False)


async def _send_rates(update: Update, ccy: str, callback: bool):
    chat = update.callback_query.message.chat if callback else update.message.chat
    send_text = chat.send_message
    send_photo = chat.send_photo

    if ccy not in CURRENCIES:
        await send_text(f"❌ Unknown: {ccy}\nSupported: {', '.join(sorted(CURRENCIES.keys()))}")
        return

    loading = await send_text(f"⏳ Fetching {CURRENCIES[ccy]['flag']} {ccy} rates…")

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, fetch_rates, ccy)

        if data.get("error"):
            await loading.edit_text(f"❌ {data['error']}")
            return

        summary = generate_summary_text(data)
        await loading.edit_text(f"```\n{summary}\n```", parse_mode=ParseMode.MARKDOWN_V2)

        # Chart if we have at least 2 curve points or an overnight rate
        crv = data.get("curve", {})
        has_curve = crv and len(crv.get("years", [])) >= 2

        if has_curve or (data.get("overnight", {}).get("rate") is not None):
            buf = await loop.run_in_executor(None, generate_curve_chart, data)
            cfg = CURRENCIES[ccy]
            await send_photo(buf, caption=f"📈 {cfg['flag']} {ccy} — {cfg['bond']} Yield Curve")

    except Exception as e:
        logger.exception(f"Error: {ccy}")
        try:
            await loading.edit_text(f"❌ Error fetching {ccy}: {str(e)[:200]}")
        except Exception:
            await send_text(f"❌ Error: {str(e)[:200]}")


async def error_handler(update, ctx):
    logger.error(f"Update {update} error: {ctx.error}")


def main():
    # if not TELEGRAM_BOT_TOKEN:
    #     print("❌ Set TELEGRAM_BOT_TOKEN in .env — see .env.example"); return
    # if not FRED_API_KEY:
    #     print("⚠️  FRED_API_KEY not set — some currencies will have limited data")

    print("🚀 Starting Rates Screener Bot…")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("rates", cmd_rates))
    app.add_handler(CommandHandler("all", cmd_all))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)
    print("✅ Bot running. Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
