import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)

from src.db import (
    get_user, get_user_purchases, get_user_topups, create_invoice, get_invoice, update_invoice_status, update_user_balance
)
from src.payment import create_crypto_invoice, check_crypto_invoice
from src.locales import get_text

logger = logging.getLogger(__name__)

TOPUP_AMOUNT = 1

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    lang = db_user['language'] if db_user else 'en'

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
    user_id = update.effective_user.id
    lang = (await get_user(user_id))['language']
    invoice_id = str(query.data.split(':')[1])

    invoice = await get_invoice(invoice_id)
    if invoice:
        if invoice['status'] == 'paid':
            await query.answer("Already paid!", show_alert=True)
            return
            
        is_paid = await check_crypto_invoice(int(invoice_id))
        if is_paid:
            # Idempotent topup check via unique invoice ID
            await update_invoice_status(invoice_id, 'paid')
            await update_user_balance(user_id, invoice['amount'])
            
            await query.edit_message_text(get_text(lang, 'invoice_paid_success', amount=f"${invoice['amount']:.2f}"))
        else:
            await query.answer(get_text(lang, 'invoice_not_paid'), show_alert=True)
    else:
        await query.answer(get_text(lang, 'invoice_not_paid'), show_alert=True)

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

