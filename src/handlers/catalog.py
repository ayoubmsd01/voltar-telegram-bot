import logging
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode

from src.db import (
    get_user, get_categories, get_products_by_category, get_product, get_stock_item,
    reserve_stock_item, release_stock_item, mark_stock_sold, add_purchase, update_user_balance,
    create_invoice, get_invoice, get_setting, add_favorite, get_all_products
)
from src.payment import create_crypto_invoice, check_crypto_invoice
from src.locales import get_text

logger = logging.getLogger(__name__)

async def stock_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    lang = db_user['language'] if db_user else 'en'
    bot_username = context.bot.username

    # Fetch announcement message if any
    announcement = await get_setting('stock_update_msg')

    # Build the stock message
    categories = await get_categories()
    if not categories:
        await update.message.reply_text(get_text(lang, 'stock_empty'))
        return

    all_products = await get_all_products()
    has_stock = any(p['stock_count'] > 0 for p in all_products)
    if not has_stock:
        await update.message.reply_text(get_text(lang, 'stock_empty'))
        return

    messages = []
    current_msg = f"<b>{get_text(lang, 'stock_header')}</b>\n\n"
    if announcement:
        current_msg = announcement + "\n\n" + current_msg

    for cat in categories:
        cat_products = [p for p in all_products if p['category_id'] == cat['id'] and p['stock_count'] > 0]
        if not cat_products:
            continue

        cat_name = cat[f'name_{lang}']
        block = get_text(lang, 'stock_format', bot_username=bot_username, cat_id=cat['id'], cat_name=cat_name) + "\n"
        
        for p in cat_products:
            p_name = p[f'title_{lang}']
            block += get_text(lang, 'stock_item', bot_username=bot_username, prod_id=p['id'], prod_name=p_name, stock=p['stock_count'], price=p['price']) + "\n"
        
        block += "\n"

        if len(current_msg) + len(block) > 4000:
            messages.append(current_msg)
            current_msg = block
        else:
            current_msg += block

    if current_msg:
        messages.append(current_msg)

    for msg in messages:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def products_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    lang = db_user['language'] if db_user else 'en'

    categories = await get_categories()
    if not categories:
        await update.message.reply_text(get_text(lang, 'stock_empty'))
        return

    keyboard = []
    for cat in categories:
        # Check if there are products with stock > 0 in this category
        cat_products = await get_products_by_category(cat['id'])
        has_stock = any(p['stock_count'] > 0 for p in cat_products)
        if has_stock:
            keyboard.append([InlineKeyboardButton(f"📁 {cat[f'name_{lang}']}", callback_data=f"prod_cat:{cat['id']}")])
    
    if not keyboard:
        await update.message.reply_text(get_text(lang, 'stock_empty'))
        return

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_text(lang, 'products_select_cat'), reply_markup=reply_markup)

async def handle_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE, arg: str, lang: str):
    if arg.startswith('cat_'):
        cat_id = int(arg.split('_')[1])
        # emulate cat select
        class DummyQuery:
            data = f"prod_cat:{cat_id}"
            async def answer(self): pass
            async def edit_message_text(self, *args, **kwargs):
                await update.message.reply_text(*args, **kwargs)
        update.callback_query = DummyQuery()
        await prod_cat_callback(update, context)
    elif arg.startswith('prod_'):
        prod_id = int(arg.split('_')[1])
        class DummyQuery:
            data = f"prod_item:{prod_id}"
            async def answer(self): pass
            async def edit_message_text(self, *args, **kwargs):
                await update.message.reply_text(*args, **kwargs)
        update.callback_query = DummyQuery()
        await prod_item_callback(update, context)

async def prod_cat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = (await get_user(update.effective_user.id))['language']

    cat_id = int(query.data.split(':')[1])
    products = await get_products_by_category(cat_id)
    
    keyboard = []
    for p in products:
        if p['stock_count'] > 0:
            p_name = p[f'title_{lang}']
            pcs = "шт." if lang == "ru" else "pcs."
            btn_text = f"{p_name} | {p['price']}$ | {p['stock_count']} {pcs}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"prod_item:{p['id']}")])
    
    keyboard.append([InlineKeyboardButton(get_text(lang, 'btn_back'), callback_data="prod_back_cats")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(get_text(lang, 'products_select_item'), reply_markup=reply_markup)

async def prod_back_cats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = (await get_user(update.effective_user.id))['language']

    categories = await get_categories()
    keyboard = []
    for cat in categories:
        cat_products = await get_products_by_category(cat['id'])
        if any(p['stock_count'] > 0 for p in cat_products):
            keyboard.append([InlineKeyboardButton(f"📁 {cat[f'name_{lang}']}", callback_data=f"prod_cat:{cat['id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(get_text(lang, 'products_select_cat'), reply_markup=reply_markup)

async def prod_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = (await get_user(update.effective_user.id))['language']

    prod_id = int(query.data.split(':')[1])
    product = await get_product(prod_id)
    
    if not product:
        await query.edit_message_text(get_text(lang, 'stock_empty'))
        return

    title = product[f'title_{lang}']
    desc = product[f'desc_{lang}']
    stock = product['stock_count']
    price = product['price']

    text = get_text(lang, 'product_page', title=title, desc=desc, price=price, stock=stock)
    
    keyboard = []
    if stock > 0:
        keyboard.append([InlineKeyboardButton(get_text(lang, 'btn_buy'), callback_data=f"prod_buy:{prod_id}")])
    else:
        keyboard.append([InlineKeyboardButton(get_text(lang, 'btn_add_favorite'), callback_data=f"prod_fav:{prod_id}")])

    keyboard.append([InlineKeyboardButton(get_text(lang, 'btn_back'), callback_data=f"prod_back_items:{product['category_id']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def prod_back_items_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Just redirect logic to category callback
    query.data = f"prod_cat:{query.data.split(':')[1]}"
    await prod_cat_callback(update, context)

async def prod_fav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    prod_id = int(query.data.split(':')[1])
    
    await add_favorite(user_id, prod_id)
    await query.answer("⭐ Added to favorites!", show_alert=True)

async def deliver_item(context: ContextTypes.DEFAULT_TYPE, user_id: int, product_id: int, item_id: int, price_paid: float):
    # Process delivery
    item = await get_stock_item(item_id)
    product = await get_product(product_id)
    db_user = await get_user(user_id)
    lang = db_user['language']

    content = item['content']
    item_type = item['type']

    await mark_stock_sold(item_id)
    await add_purchase(user_id, product_id, item_id, price_paid)
    
    if item_type in ('code', 'link', 'text'):
        text = get_text(lang, 'purchase_success', content=content)
        await context.bot.send_message(chat_id=user_id, text=text)
    elif item_type == 'file':
        # the content should be a file_id from telegram
        text = get_text(lang, 'purchase_success', content="[FILE]")
        await context.bot.send_document(chat_id=user_id, document=content, caption=text)

async def timeout_payment(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    user_id = data['user_id']
    invoice_id = data['invoice_id']
    paid_from_balance = data['paid_from_balance']
    item_id = data['item_id']
    
    invoice = await get_invoice(invoice_id)
    if invoice and invoice['status'] == 'active':
        # Cancel order
        await update_invoice_status(invoice_id, 'cancelled')
        await release_stock_item(item_id)
        if paid_from_balance > 0:
            await update_user_balance(user_id, paid_from_balance)
            
        db_user = await get_user(user_id)
        lang = db_user['language']
        # Optionally send a message
        # await context.bot.send_message(chat_id=user_id, text=get_text(lang, 'btn_cancel_order'))

async def prod_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    lang = (await get_user(user_id))['language']
    
    prod_id = int(query.data.split(':')[1])
    product = await get_product(prod_id)
    
    item_id = await reserve_stock_item(prod_id)
    if not item_id:
        await query.answer(get_text(lang, 'out_of_stock'), show_alert=True)
        # Edit message to out of stock + fav button
        product = await get_product(prod_id)
        text = get_text(lang, 'product_page', title=product[f'title_{lang}'], desc=product[f'desc_{lang}'], price=product['price'], stock=0)
        keyboard = [[InlineKeyboardButton(get_text(lang, 'btn_add_favorite'), callback_data=f"prod_fav:{prod_id}")],
                    [InlineKeyboardButton(get_text(lang, 'btn_back'), callback_data=f"prod_back_items:{product['category_id']}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return

    price = product['price']
    db_user = await get_user(user_id)
    balance = db_user['balance']

    if balance >= price:
        # Scenario A
        await update_user_balance(user_id, -price)
        await deliver_item(context, user_id, prod_id, item_id, price)
        await query.edit_message_text(get_text(lang, 'purchase_success', content="Delivery in progress..."))
    else:
        # Scenario B
        need_crypto = round(price - balance, 2)
        await update_user_balance(user_id, -balance)
        
        crypto_data = await create_crypto_invoice(need_crypto)
        invoice_id = str(crypto_data['invoice_id'])
        url = crypto_data['url']
        
        await create_invoice(invoice_id, user_id, need_crypto)
        
        # Schedule timeout in 15 mins (900 seconds)
        context.job_queue.run_once(timeout_payment, 900, data={
            'user_id': user_id,
            'invoice_id': invoice_id,
            'paid_from_balance': balance,
            'item_id': item_id,
            'prod_id': prod_id,
            'price': price
        }, name=f"timeout_{invoice_id}")
        
        keyboard = [
            [InlineKeyboardButton("Pay via CryptoBot", url=url)],
            [InlineKeyboardButton(get_text(lang, 'btn_check_payment'), callback_data=f"chk_ord:{invoice_id}")],
            [InlineKeyboardButton(get_text(lang, 'btn_cancel_order'), callback_data=f"cnc_ord:{invoice_id}")]
        ]
        
        await query.edit_message_text(
            f"{get_text(lang, 'topup_invoice_created', amount=need_crypto)}\n{get_text(lang, 'purchase_insufficient_payment')}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def check_order_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    lang = (await get_user(user_id))['language']
    invoice_id = query.data.split(':')[1]
    
    # check db first
    invoice = await get_invoice(invoice_id)
    if invoice and invoice['status'] == 'paid':
        await query.answer(get_text(lang, 'purchase_success', content=""), show_alert=True)
        return
        
    is_paid = await check_crypto_invoice(int(invoice_id))
    if is_paid:
        await update_invoice_status(invoice_id, 'paid')
        
        # Find job data to deliver item
        jobs = context.job_queue.get_jobs_by_name(f"timeout_{invoice_id}")
        if jobs:
            job = jobs[0]
            data = job.data
            job.schedule_removal()
            await deliver_item(context, user_id, data['prod_id'], data['item_id'], data['price'])
            await query.edit_message_text(get_text(lang, 'purchase_success', content="Delivery complete!"))
    else:
        await query.answer("Payment not completed yet.", show_alert=True)

async def cancel_order_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    lang = (await get_user(user_id))['language']
    invoice_id = query.data.split(':')[1]
    
    invoice = await get_invoice(invoice_id)
    if invoice and invoice['status'] == 'active':
        jobs = context.job_queue.get_jobs_by_name(f"timeout_{invoice_id}")
        if jobs:
            job = jobs[0]
            data = job.data
            job.schedule_removal()
            
            await update_invoice_status(invoice_id, 'cancelled')
            await release_stock_item(data['item_id'])
            if data['paid_from_balance'] > 0:
                await update_user_balance(user_id, data['paid_from_balance'])
                
            await query.edit_message_text("❌ Order cancelled.")
            return

    await query.answer("Order already processed.", show_alert=True)

def register_handlers(application: Application):
    msg_ru_en = lambda k: f"^({get_text('ru', k)}|{get_text('en', k)})$"
    
    application.add_handler(MessageHandler(filters.Regex(msg_ru_en('btn_stock')), stock_view))
    application.add_handler(MessageHandler(filters.Regex(msg_ru_en('btn_products')), products_base))
    
    # regex priority matching
    application.add_handler(CallbackQueryHandler(prod_cat_callback, pattern='^prod_cat:'))
    application.add_handler(CallbackQueryHandler(prod_item_callback, pattern='^prod_item:'))
    application.add_handler(CallbackQueryHandler(prod_back_cats_callback, pattern='^prod_back_cats$'))
    application.add_handler(CallbackQueryHandler(prod_back_items_callback, pattern='^prod_back_items:'))
    application.add_handler(CallbackQueryHandler(prod_fav_callback, pattern='^prod_fav:'))
    application.add_handler(CallbackQueryHandler(prod_buy_callback, pattern='^prod_buy:'))
    
    application.add_handler(CallbackQueryHandler(check_order_payment, pattern='^chk_ord:'))
    application.add_handler(CallbackQueryHandler(cancel_order_payment, pattern='^cnc_ord:'))
