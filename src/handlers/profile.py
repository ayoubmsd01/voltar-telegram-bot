import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)

import os
from src.db import (
    get_user, create_user, get_user_purchases, get_user_topups, create_invoice, get_invoice, update_invoice_status, update_user_balance, process_invoice_payment
)
from src.config import DB_PATH
from src.payment import create_crypto_invoice, get_crypto_invoice_status
from src.locales import get_text
import traceback
from src.xrocket import create_xrocket_invoice, get_xrocket_invoice_status
import secrets
import time


logger = logging.getLogger(__name__)

TOPUP_AMOUNT = 1

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    if not db_user:
        await create_user(user_id, 'en', update.effective_user.username)
        db_user = await get_user(user_id)
        
    lang = db_user['language'] if db_user else 'en'
    logger.info(f"DB_PATH(profile): {os.path.abspath(DB_PATH)}")

    text = get_text(
        lang, 'profile_info',
        user_id=user_id,
        balance=f"{db_user['balance']:.2f}",
        spent=f"{db_user['total_spent']:.2f}",
        reg_date=db_user['registered_at'].split()[0]
    )

    keyboard = [
        [InlineKeyboardButton(get_text(lang, 'btn_topup'), callback_data="prof_topup")],
        [InlineKeyboardButton(get_text(lang, 'btn_purchases'), callback_data="prof_purchases")],
        [InlineKeyboardButton(get_text(lang, 'btn_topups'), callback_data="prof_topups")],
        [InlineKeyboardButton(get_text(lang, 'btn_coupon'), callback_data="prof_coupon")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Clean old messages in conversation if any
    if "topup_msg" in context.user_data:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=context.user_data["topup_msg"])
        except:
            pass
        del context.user_data["topup_msg"]

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def prof_topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = (await get_user(user_id))['language']
    
    msg = await query.edit_message_text(get_text(lang, 'topup_enter_amount'))
    context.user_data["topup_msg"] = msg.message_id
    
    return TOPUP_AMOUNT

async def prof_topup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Store only the pending amount until the user selects a provider.
    try:
        amount = round(float(update.message.text.strip()), 2)
        if not (0.01 <= amount <= 10000):
            raise ValueError("out of range")
    except (ValueError, OverflowError, AttributeError):
        await update.message.reply_text("❌ Invalid amount. Enter a number from 0.01 to 10000 USD.")
        return TOPUP_AMOUNT

    context.user_data["pending_topup"] = {"amount": amount, "created": time.time()}
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 CryptoBot", callback_data="topup_provider:cryptobot")],
        [InlineKeyboardButton("🚀 xRocket", callback_data="topup_provider:xrocket")]
    ])
    await update.message.reply_text(
        f"💳 Top Up: ${amount:.2f} USDT\nSelect payment method:",
        reply_markup=keyboard
    )
    return ConversationHandler.END


async def select_topup_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selection = query.data.split(":", 1)[1]
    if selection not in ("cryptobot", "xrocket"):
        await query.edit_message_text("Invalid payment method.")
        return

    pending = context.user_data.pop("pending_topup", None)
    if not pending or time.time() - pending.get("created", 0) > 900:
        await query.edit_message_text("⏳ This top-up request expired. Open Profile → Top Up again.")
        return
    amount = float(pending["amount"])
    user_id = update.effective_user.id

    # Avoid issuing invoices with missing credentials. No wallet secrets reach Telegram.
    from src.config import CRYPTO_BOT_TOKEN
    if selection == "cryptobot" and not CRYPTO_BOT_TOKEN:
        await query.edit_message_text("⚠️ CryptoBot payments are not configured.")
        return
    if selection == "xrocket" and not os.getenv("XROCKET_API_TOKEN", "").strip():
        await query.edit_message_text("⚠️ xRocket is being configured. Choose CryptoBot for now.")
        return

    await query.edit_message_text("⏳ Creating your secure payment invoice...")
    try:
        if selection == "cryptobot":
            payment = await create_crypto_invoice(amount)
            local_id = str(payment["invoice_id"])
            provider_invoice_id = local_id
        else:
            local_id = "xr_" + secrets.token_hex(12)
            payment = await create_xrocket_invoice(amount, local_id, user_id)
            provider_invoice_id = str(payment["invoice_id"])

        await create_invoice(local_id, user_id, amount,
                             provider=selection, provider_invoice_id=provider_invoice_id)
        provider_name = "CryptoBot" if selection == "cryptobot" else "xRocket"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Pay with " + provider_name, url=payment["url"])],
            [InlineKeyboardButton("✅ Check Payment", callback_data="chk_topup:" + local_id)]
        ])
        await query.edit_message_text(
            f"💳 {provider_name} invoice: ${amount:.2f} USDT\n"
            "Pay using the button, then tap Check Payment.",
            reply_markup=keyboard
        )
    except Exception:
        logger.exception("Failed to create top-up invoice via %s", selection)
        await query.edit_message_text("⚠️ Payment provider unavailable. No balance was charged. Please retry.")


async def check_topup_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Checking...")
    user_id = update.effective_user.id
    local_id = query.data.split(":", 1)[1]

    invoice = await get_invoice(local_id)
    if not invoice:
        await query.edit_message_text("❌ Invoice not found.")
        return
    if int(invoice["user_id"]) != user_id:
        await query.answer("This payment does not belong to your account.", show_alert=True)
        return

    amount = float(invoice["amount"])
    if invoice["status"] == "paid":
        await query.edit_message_text(f"✅ Already credited: ${amount:.2f}")
        return
    if invoice["status"] != "active":
        await query.edit_message_text("❌ This invoice has expired or been cancelled.")
        return

    provider = invoice.get("provider") or "cryptobot"
    external_id = invoice.get("provider_invoice_id") or local_id
    try:
        if provider == "xrocket":
            status = await get_xrocket_invoice_status(external_id, amount)
        elif provider == "cryptobot":
            status = await get_crypto_invoice_status(int(external_id))
        else:
            raise RuntimeError("Unknown invoice provider")

        if status == "paid":
            success = await process_invoice_payment(local_id, user_id, amount)
            user_data = await get_user(user_id)
            new_balance = float(user_data["balance"])
            if success:
                await query.edit_message_text(
                    f"✅ Payment confirmed! +${amount:.2f} credited.\nNew balance: ${new_balance:.2f}"
                )
            else:
                await query.edit_message_text("✅ Invoice already processed, or no longer payable.")
        elif status in ("active", "pending", "partially_paid"):
            await query.answer("⏳ Payment not confirmed yet.", show_alert=True)
        elif status in ("expired", "cancelled"):
            await update_invoice_status(local_id, status)
            await query.edit_message_text("❌ Payment invoice expired or cancelled.")
        else:
            await query.answer("⚠️ Payment status not confirmed. Try again later.", show_alert=True)
    except Exception:
        logger.exception("Payment verification failed for provider %s", provider)
        await query.answer("⚠️ Verification temporarily unavailable.", show_alert=True)


async def prof_purchases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = (await get_user(user_id))['language']

    purchases = await get_user_purchases(user_id)
    if not purchases:
        await query.edit_message_text("No purchases yet.")
        return

    text = "🛒 <b>My Purchases:</b>\n\n"
    for p in purchases:
        title = p[f"title_{lang}"]
        date = p['purchased_at'].split()[0]
        text += f"- {title} | ${p['price_paid']} | {date}\n"

    # Need a back button possibly
    keyboard = [[InlineKeyboardButton(get_text(lang, 'btn_back'), callback_data="prof_back")]]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def prof_topups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = (await get_user(user_id))['language']

    topups = await get_user_topups(user_id)
    if not topups:
        await query.edit_message_text("No top-ups yet.")
        return

    text = "💵 <b>My Top-ups:</b>\n\n"
    for t in topups:
        date = t['created_at'].split()[0]
        provider_name = "xRocket" if t.get("provider") == "xrocket" else "CryptoBot"
        text += f"- ${t['amount']} | {date} | {provider_name}\\n"

    keyboard = [[InlineKeyboardButton(get_text(lang, 'btn_back'), callback_data="prof_back")]]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def prof_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    lang = db_user['language']

    text = get_text(
        lang, 'profile_info',
        user_id=user_id,
        balance=f"{db_user['balance']:.2f}",
        spent=f"{db_user['total_spent']:.2f}",
        reg_date=db_user['registered_at'].split()[0]
    )
    keyboard = [
        [InlineKeyboardButton(get_text(lang, 'btn_topup'), callback_data="prof_topup")],
        [InlineKeyboardButton(get_text(lang, 'btn_purchases'), callback_data="prof_purchases")],
        [InlineKeyboardButton(get_text(lang, 'btn_topups'), callback_data="prof_topups")],
        [InlineKeyboardButton(get_text(lang, 'btn_coupon'), callback_data="prof_coupon")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

def register_handlers(application: Application):
    from src.locales import get_text
    msg_ru_en = lambda k: f"^({get_text('ru', k)}|{get_text('en', k)})$"
    
    topup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(prof_topup_start, pattern='^prof_topup$')],
        states={
            TOPUP_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, prof_topup_amount)]
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)]
    )
    
    application.add_handler(topup_conv)
    application.add_handler(MessageHandler(filters.Regex(msg_ru_en('btn_profile')), profile_command))
    application.add_handler(CallbackQueryHandler(prof_purchases, pattern='^prof_purchases$'))
    application.add_handler(CallbackQueryHandler(prof_topups, pattern='^prof_topups$'))
    application.add_handler(CallbackQueryHandler(prof_back, pattern='^prof_back$'))
    application.add_handler(CallbackQueryHandler(select_topup_provider, pattern=r'^topup_provider:(cryptobot|xrocket)$'))
    application.add_handler(CallbackQueryHandler(check_topup_payment, pattern='^chk_topup:'))

