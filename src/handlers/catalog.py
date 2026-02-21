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
import aiosqlite
from src.config import DB_PATH
from src.db import dict_factory
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

async def prod_fav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    prod_id = int(query.data.split(':')[1])
    
    await add_favorite(user_id, prod_id)
    await query.answer("⭐ Added to favorites!", show_alert=True)

async def timeout_payment(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    user_id = data['user_id']
    invoice_id = data['invoice_id']
    paid_from_balance = data['paid_from_balance']
    item_id = data['item_id']
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = dict_factory
            await db.execute('BEGIN IMMEDIATE')
            
            async with db.execute("SELECT status FROM invoices WHERE invoice_id = ?", (invoice_id,)) as cursor:
                inv = await cursor.fetchone()
                
            if inv and inv['status'] == 'active':
                await db.execute("UPDATE stock_items SET status = 'available', reserved_at = NULL WHERE id = ?", (item_id,))
                if paid_from_balance > 0:
                    await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (paid_from_balance, user_id))
                await db.execute("UPDATE invoices SET status = 'cancelled' WHERE invoice_id = ?", (invoice_id,))
                await db.commit()
                logger.info(f"Order cancelled by timeout: {invoice_id}")
            else:
                await db.execute('ROLLBACK')
    except Exception as e:
        logger.error(f"Error in timeout_payment: {e}")

async def prod_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    prod_id = int(query.data.split(':')[1])
    logger.info(f"prod_buy started for user_id={user_id}, prod_id={prod_id}")
    
    db_user = await get_user(user_id)
    lang = db_user['language'] if db_user else 'en'
    product = await get_product(prod_id)
    
    if not product or product['stock_count'] <= 0:
        if product:
            text = get_text(lang, 'product_page', title=product[f'title_{lang}'], desc=product[f'desc_{lang}'], price=product['price'], stock=0)
            keyboard = [[InlineKeyboardButton(get_text(lang, 'btn_add_favorite'), callback_data=f"prod_fav:{prod_id}")],
                        [InlineKeyboardButton(get_text(lang, 'btn_back'), callback_data=f"prod_back_items:{product['category_id']}")]]
            await query.edit_message_text(f"❌ {get_text(lang, 'out_of_stock')}\n\n{text}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(f"❌ {get_text(lang, 'out_of_stock')}")
        return

    price = product['price']

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = dict_factory
            await db.execute('BEGIN IMMEDIATE')
            
            async with db.execute("SELECT id, content, type FROM stock_items WHERE product_id = ? AND status = 'available' LIMIT 1", (prod_id,)) as cursor:
                stock_row = await cursor.fetchone()
                
            if not stock_row:
                await db.execute('ROLLBACK')
                text = get_text(lang, 'product_page', title=product[f'title_{lang}'], desc=product[f'desc_{lang}'], price=product['price'], stock=0)
                keyboard = [[InlineKeyboardButton(get_text(lang, 'btn_add_favorite'), callback_data=f"prod_fav:{prod_id}")],
                            [InlineKeyboardButton(get_text(lang, 'btn_back'), callback_data=f"prod_back_items:{product['category_id']}")]]
                await query.edit_message_text(f"❌ {get_text(lang, 'out_of_stock')}\n\n{text}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
                return
                
            stock_id = stock_row['id']
            stock_content = stock_row['content']
            stock_type = stock_row['type']
            
            async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cursor:
                user_row = await cursor.fetchone()
            current_balance = user_row['balance'] if user_row else 0
            
            logger.info(f"BUY ATTEMPT - user_id={user_id}, product_id={prod_id}, stock_id={stock_id}, balance_before={current_balance}, price={price}")
            
            if current_balance >= price:
                logger.info("Scenario A: Full Balance")
                await db.execute("UPDATE stock_items SET status = 'sold' WHERE id = ?", (stock_id,))
                await db.execute("UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE id = ?", (price, price, user_id))
                await db.execute("INSERT INTO purchases (user_id, product_id, stock_item_id, price_paid) VALUES (?, ?, ?, ?)", (user_id, prod_id, stock_id, price))
                await db.commit()
                
                if stock_type in ('code', 'link', 'text'):
                    text_msg = get_text(lang, 'purchase_success', content=stock_content)
                    await context.bot.send_message(chat_id=user_id, text=text_msg)
                elif stock_type == 'file':
                    text_msg = get_text(lang, 'purchase_success', content="[FILE]")
                    await context.bot.send_document(chat_id=user_id, document=stock_content, caption=text_msg)
                    
                await query.edit_message_text(get_text(lang, 'purchase_success', content="Delivery complete!"))
                return
            else:
                paid_from_balance = current_balance
                need_crypto = max(0, round(price - paid_from_balance, 2))
                logger.info(f"Scenario B/C: paid_from_balance={paid_from_balance}, type={stock_type}, need_crypto={need_crypto}")
                
                await db.execute("UPDATE stock_items SET status = 'reserved', reserved_at = CURRENT_TIMESTAMP WHERE id = ?", (stock_id,))
                if paid_from_balance > 0:
                    await db.execute("UPDATE users SET balance = 0 WHERE id = ?", (user_id,))
                
                await db.commit()
                # DB transaction finishes here
                
    except Exception as e:
        logger.error(f"Error in prod_buy_callback DB step 1: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await query.edit_message_text("❌ An error occurred during purchase preparation.")
        return

    # Outside DB connection, create invoice
    logger.info(f"Creating crypto invoice for {need_crypto}")
    try:
        crypto_data = await create_crypto_invoice(need_crypto)
        invoice_id = str(crypto_data['invoice_id'])
        url = crypto_data['url']
        logger.info(f"Invoice created: {invoice_id} -> {url}")
    except Exception as e:
        logger.error(f"Failed to create crypto invoice: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Rollback logic
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = dict_factory
                await db.execute('BEGIN IMMEDIATE')
                await db.execute("UPDATE stock_items SET status = 'available', reserved_at = NULL WHERE id = ?", (stock_id,))
                if paid_from_balance > 0:
                    await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (paid_from_balance, user_id))
                await db.commit()
                logger.info("Successfully rolled back DB state after CryptoBot API failure.")
        except Exception as e_rb:
            logger.error(f"Failed to rollback DB state: {e_rb}")
            logger.error(traceback.format_exc())
            
        await query.edit_message_text("❌ Payment service unavailable. Order cancelled.")
        return

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = dict_factory
            await db.execute('BEGIN IMMEDIATE')
            await db.execute('INSERT INTO invoices (invoice_id, user_id, amount) VALUES (?, ?, ?)', (invoice_id, user_id, need_crypto))
            await db.commit()
            
        context.job_queue.run_once(timeout_payment, 900, data={
            'user_id': user_id,
            'invoice_id': invoice_id,
            'paid_from_balance': paid_from_balance,
            'item_id': stock_id,
            'prod_id': prod_id,
            'price': price
        }, name=f"timeout_{invoice_id}")
        
        keyboard = [
            [InlineKeyboardButton("Pay via CryptoBot", url=url)],
            [InlineKeyboardButton(get_text(lang, 'btn_check_payment'), callback_data=f"chk_ord:{invoice_id}")],
            [InlineKeyboardButton(get_text(lang, 'btn_cancel_order'), callback_data=f"cnc_ord:{invoice_id}")]
        ]
        
        await query.edit_message_text(
            f"{get_text(lang, 'topup_invoice_created', amount=f'${need_crypto}')}\n{get_text(lang, 'purchase_insufficient_payment')}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Failed to insert invoice or queue job: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await query.edit_message_text("❌ An error occurred while generating your order. Action was reverted.")


async def check_order_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    lang = db_user['language'] if db_user else 'en'
    invoice_id = query.data.split(':')[1]
    
    try:
        is_paid = await check_crypto_invoice(int(invoice_id))
        
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = dict_factory
            await db.execute('BEGIN IMMEDIATE')
            
            async with db.execute("SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,)) as cursor:
                invoice = await cursor.fetchone()
                
            if not invoice:
                await db.execute('ROLLBACK')
                await query.edit_message_text("❌ Invoice not found.")
                return
                
            if invoice['status'] == 'paid':
                await db.execute('ROLLBACK')
                await query.edit_message_text("✅ Already paid.")
                return
                
            if invoice['status'] == 'cancelled':
                await db.execute('ROLLBACK')
                await query.edit_message_text("❌ Order is already cancelled.")
                return
                
            if is_paid:
                jobs = context.job_queue.get_jobs_by_name(f"timeout_{invoice_id}")
                if not jobs:
                    await db.execute('ROLLBACK')
                    await query.edit_message_text("❌ Delivery data lost. Contact support.")
                    return
                    
                job = jobs[0]
                data = job.data
                item_id = data['item_id']
                prod_id = data['prod_id']
                price = data['price']
                
                await db.execute("UPDATE invoices SET status = 'paid' WHERE invoice_id = ?", (invoice_id,))
                await db.execute("UPDATE stock_items SET status = 'sold' WHERE id = ?", (item_id,))
                await db.execute("UPDATE users SET total_spent = total_spent + ? WHERE id = ?", (price, user_id))
                await db.execute("INSERT INTO purchases (user_id, product_id, stock_item_id, price_paid) VALUES (?, ?, ?, ?)", (user_id, prod_id, item_id, price))
                
                async with db.execute("SELECT content, type FROM stock_items WHERE id = ?", (item_id,)) as cursor:
                    stock = await cursor.fetchone()
                
                await db.commit()
                job.schedule_removal()
                logger.info(f"Order {invoice_id} completed successfully.")
                
                stock_type = stock['type']
                stock_content = stock['content']
                if stock_type in ('code', 'link', 'text'):
                    text = get_text(lang, 'purchase_success', content=stock_content)
                    await context.bot.send_message(chat_id=user_id, text=text)
                elif stock_type == 'file':
                    text = get_text(lang, 'purchase_success', content="[FILE]")
                    await context.bot.send_document(chat_id=user_id, document=stock_content, caption=text)
                    
                await query.edit_message_text(get_text(lang, 'purchase_success', content="Delivery complete!"))
            else:
                await db.execute('ROLLBACK')
                # Edit the message to show "Payment not completed yet" briefly, then restore?
                # Actually, sending a quick message might be better since we can't show alerts.
                await context.bot.send_message(chat_id=user_id, text="❌ Payment not completed yet.")
                
    except Exception as e:
        logger.error(f"Error in check_order_payment: {e}")
        await context.bot.send_message(chat_id=user_id, text="❌ An error occurred check logs.")

async def cancel_order_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    invoice_id = query.data.split(':')[1]
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = dict_factory
            await db.execute('BEGIN IMMEDIATE')
            
            async with db.execute("SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,)) as cursor:
                invoice = await cursor.fetchone()
                
            if invoice and invoice['status'] == 'active':
                jobs = context.job_queue.get_jobs_by_name(f"timeout_{invoice_id}")
                if jobs:
                    job = jobs[0]
                    data = job.data
                    item_id = data['item_id']
                    paid_from_balance = data['paid_from_balance']
                    job.schedule_removal()
                    
                    await db.execute("UPDATE stock_items SET status = 'available', reserved_at = NULL WHERE id = ?", (item_id,))
                    if paid_from_balance > 0:
                        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (paid_from_balance, user_id))
                    await db.execute("UPDATE invoices SET status = 'cancelled' WHERE invoice_id = ?", (invoice_id,))
                    await db.commit()
                    await query.edit_message_text("❌ Order cancelled.")
                    logger.info(f"Order manually cancelled: {invoice_id}")
                    return
            await db.execute('ROLLBACK')
            await query.edit_message_text("❌ Order already processed or cancelled.")
            
    except Exception as e:
        logger.error(f"Error in cancel_order_payment: {e}")
        await query.edit_message_text("❌ An error occurred.")

def register_handlers(application: Application):
    msg_ru_en = lambda k: f"^({get_text('ru', k)}|{get_text('en', k)})$"
    
    application.add_handler(MessageHandler(filters.Regex(msg_ru_en('btn_stock')), stock_view))
    application.add_handler(MessageHandler(filters.Regex(msg_ru_en('btn_products')), products_base))
    
    # regex priority matching
    application.add_handler(CallbackQueryHandler(prod_cat_callback, pattern=r'^prod_cat:\d+$'))
    application.add_handler(CallbackQueryHandler(prod_item_callback, pattern=r'^prod_item:\d+$'))
    application.add_handler(CallbackQueryHandler(prod_back_cats_callback, pattern=r'^prod_back_cats$'))
    application.add_handler(CallbackQueryHandler(prod_back_items_callback, pattern=r'^prod_back_items:\d+$'))
    application.add_handler(CallbackQueryHandler(prod_fav_callback, pattern=r'^prod_fav:\d+$'))
    application.add_handler(CallbackQueryHandler(prod_buy_callback, pattern=r'^prod_buy:\d+$'))
    
    application.add_handler(CallbackQueryHandler(check_order_payment, pattern=r'^chk_ord:'))
    application.add_handler(CallbackQueryHandler(cancel_order_payment, pattern=r'^cnc_ord:'))
