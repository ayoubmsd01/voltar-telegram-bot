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
    user_id = update.effective_user.id
    lang = (await get_user(user_id))['language']
    
    amount_str = update.message.text
    try:
        amount = float(amount_str)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(get_text(lang, 'invalid_amount'))
        return TOPUP_AMOUNT

    # Create CryptoBot invoice
    crypto_data = await create_crypto_invoice(amount)
    invoice_id = str(crypto_data['invoice_id'])
    url = crypto_data['url']

    logger.info(f"DB_PATH(topup_create): {os.path.abspath(DB_PATH)}")
    await create_invoice(invoice_id, user_id, amount)

    keyboard = [
        [InlineKeyboardButton("Pay via CryptoBot", url=url)],
        [InlineKeyboardButton(get_text(lang, 'btn_check_payment'), callback_data=f"chk_topup:{invoice_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        get_text(lang, 'topup_invoice_created', amount=f"${amount:.2f}"),
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def check_topup_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Checking...", show_alert=False)

    user_id = update.effective_user.id
    lang = (await get_user(user_id))['language']
    invoice_id = str(query.data.split(':')[1])

    # DEBUG MESSAGE FOR USER
    # Disable after confirmed working.
    await context.bot.send_message(chat_id=user_id, text=f"DEBUG: check handler reached ✅\nInvoice: {invoice_id}")

    logger.info(f"DB_PATH(topup_check): {os.path.abspath(DB_PATH)}")
    logger.info(f"Check payment requested - user_id={user_id}, invoice_id={invoice_id}")
    
    invoice = await get_invoice(invoice_id)
    if not invoice:
        logger.error(f"Invoice not found in DB: {invoice_id}")
        await query.answer(get_text(lang, 'invoice_not_paid') if get_text(lang, 'invoice_not_paid') else "Invoice not found", show_alert=True)
        return

    amount = float(invoice['amount'])
    
    if invoice['status'] == 'paid':
        logger.info(f"Invoice {invoice_id} is already marked as paid in DB. Skipping.")
        await query.edit_message_text(f"✅ Already credited: ${amount:.2f}")
        return

    try:
        status = await get_crypto_invoice_status(int(invoice_id))
        logger.info(f"CryptoBot API status for invoice {invoice_id}: {status}")
        
        if status in ['paid', 'completed']:
            await context.bot.send_message(chat_id=user_id, text="✅ Paid detected. Updating balance…")
            
            # Idempotent database update
            success = await process_invoice_payment(invoice_id, user_id, amount)
            if success:
                logger.info(f"✅ Successfully processed payment. Balance updated for {user_id} by {amount}.")
                # Fetch new balance
                user_data = await get_user(user_id)
                new_balance = float(user_data['balance'])
                
                success_msg = f"✅ Balance credited: +${amount:.2f}\n" 
                success_msg += f"New balance: ${new_balance:.2f}"
                
                await query.edit_message_text(success_msg)
            else:
                logger.info(f"Payment was somehow already processed concurrently for {invoice_id}.")
                await query.edit_message_text(f"✅ Already credited: ${amount:.2f}")
                
        elif status in ['active', 'pending']:
            await context.bot.send_message(chat_id=user_id, text="⏳ Not paid yet. Try again.")
            await query.answer("⏳ Payment not received yet", show_alert=True)
        elif status in ['expired', 'cancelled']:
            await update_invoice_status(invoice_id, status)
            await context.bot.send_message(chat_id=user_id, text="❌ Invoice expired. Create a new top-up.")
            msg = "The invoice has expired or been cancelled. Please create a new top-up." if lang == 'en' else "Счет истек или был отменен. Пожалуйста, создайте новый счет."
            keyboard = [[InlineKeyboardButton(get_text(lang, 'btn_topup'), callback_data="prof_topup")]]
            await query.edit_message_text(f"❌ {msg}", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await context.bot.send_message(chat_id=user_id, text="⚠️ Payment check failed. Please try again.")
            await query.answer("Payment check failed. Please try again." if lang == 'en' else "Ошибка при проверке статуса. Повторите попытку.", show_alert=True)
    except Exception as e:
        logger.error(f"Exception during check_topup_payment: {e}\n{traceback.format_exc()}")
        await context.bot.send_message(chat_id=user_id, text=f"⚠️ Payment check failed: {str(e)}")
        await query.answer("An error occurred during verification." if lang == 'en' else "При проверке произошла ошибка.", show_alert=True)

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
        text += f"- ${t['amount']} | {date} | CryptoBot\n"

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
    application.add_handler(CallbackQueryHandler(check_topup_payment, pattern='^chk_topup:'))

