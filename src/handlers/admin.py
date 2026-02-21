import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
)

from src.config import ADMIN_IDS
from src.db import (
    get_user, get_categories, add_category, add_product,
    get_products_by_category, add_stock_item, get_all_products,
    update_user_balance, set_setting, delete_setting, set_user_ban, get_favorites, get_all_users, get_purchases_page
)
from src.locales import get_text
import re

logger = logging.getLogger(__name__)

# State definitions for ConversationHandlers
# Product Add
ADD_PROD_CAT, ADD_PROD_TITLE_RU, ADD_PROD_TITLE_EN, ADD_PROD_DESC_RU, ADD_PROD_DESC_EN, ADD_PROD_PRICE = range(6)
# Stock Add
ADD_STOCK_CAT, ADD_STOCK_PROD, ADD_STOCK_TYPE, ADD_STOCK_CONTENT = range(10, 14)
# Balances
BAL_USER_ID, BAL_AMOUNT = range(20, 22)
# History Search
SEARCH_HISTORY_USER, SEARCH_HISTORY_ORDER = range(60, 62)
# Ban
BAN_USER_ID = 40
UNBAN_USER_ID = 41

def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@admin_required
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    lang = db_user['language'] if db_user else 'en'

    keyboard = [
        [InlineKeyboardButton(get_text(lang, 'admin_add_product'), callback_data="adm_add_prod")],
        [InlineKeyboardButton(get_text(lang, 'admin_add_stock'), callback_data="adm_add_stock")],
        [InlineKeyboardButton("➕ Add Category", callback_data="adm_add_cat_ru")],  # Missing from specs, but required logically
        [InlineKeyboardButton(get_text(lang, 'admin_manage_balances'), callback_data="adm_balances")],
        [InlineKeyboardButton(get_text(lang, 'admin_publish_stock'), callback_data="adm_pub_stock"),
         InlineKeyboardButton(get_text(lang, 'admin_hide_stock'), callback_data="adm_hide_stock")],
        [InlineKeyboardButton(get_text(lang, 'admin_ban_user'), callback_data="adm_ban"),
         InlineKeyboardButton(get_text(lang, 'admin_unban_user'), callback_data="adm_unban")],
        [InlineKeyboardButton("🇷🇺 👥 Пользователи" if lang == 'ru' else "🇬🇧 👥 Users", callback_data="adm_users")],
        [InlineKeyboardButton(get_text(lang, 'btn_purchase_history'), callback_data="adm_history:page:0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(get_text(lang, 'admin_panel'), reply_markup=reply_markup)

# --- Add Product Flow ---
async def adm_add_prod_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    cats = await get_categories()
    if not cats:
        await query.edit_message_text("No categories found. Add one first.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(c['name_en'], callback_data=f"selcat:{c['id']}")] for c in cats]
    await query.edit_message_text("Select category:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_PROD_CAT

async def adm_add_prod_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split(':')[1])
    context.user_data['new_prod'] = {'cat_id': cat_id}
    
    await query.edit_message_text("Enter title (RU):")
    return ADD_PROD_TITLE_RU

async def adm_add_prod_title_ru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_prod']['title_ru'] = update.message.text
    await update.message.reply_text("Enter title (EN):")
    return ADD_PROD_TITLE_EN

async def adm_add_prod_title_en(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_prod']['title_en'] = update.message.text
    await update.message.reply_text("Enter description (RU):")
    return ADD_PROD_DESC_RU

async def adm_add_prod_desc_ru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_prod']['desc_ru'] = update.message.text
    await update.message.reply_text("Enter description (EN):")
    return ADD_PROD_DESC_EN

async def adm_add_prod_desc_en(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_prod']['desc_en'] = update.message.text
    await update.message.reply_text("Enter price (ex. 1.50):")
    return ADD_PROD_PRICE

async def adm_add_prod_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text)
        if price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Invalid price. Try again:")
        return ADD_PROD_PRICE

    p = context.user_data['new_prod']
    await add_product(p['cat_id'], p['title_ru'], p['title_en'], p['desc_ru'], p['desc_en'], price)
    
    await update.message.reply_text("✅ Product added!")
    return ConversationHandler.END


# --- Add Category Flow ---
ADD_CAT_RU, ADD_CAT_EN = range(100, 102)
async def adm_add_cat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Enter category name (RU):")
    return ADD_CAT_RU

async def adm_add_cat_ru(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_cat_ru'] = update.message.text
    await update.message.reply_text("Enter category name (EN):")
    return ADD_CAT_EN

async def adm_add_cat_en(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name_en = update.message.text
    name_ru = context.user_data['new_cat_ru']
    await add_category(name_ru, name_en)
    await update.message.reply_text("✅ Category added!")
    return ConversationHandler.END


# --- Add Stock Flow ---
async def adm_add_stock_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cats = await get_categories()
    if not cats:
        await query.edit_message_text("No categories found.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(c['name_en'], callback_data=f"stkcat:{c['id']}")] for c in cats]
    await query.edit_message_text("Select category:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_STOCK_CAT

async def adm_add_stock_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split(':')[1])
    
    prods = await get_products_by_category(cat_id)
    if not prods:
        await query.edit_message_text("No products in this category.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(p['title_en'], callback_data=f"stkprod:{p['id']}")] for p in prods]
    await query.edit_message_text("Select product:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_STOCK_PROD

async def adm_add_stock_prod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = int(query.data.split(':')[1])
    context.user_data['stk_prod_id'] = prod_id
    
    keyboard = [
        [InlineKeyboardButton("File", callback_data="stktyp:file"),
         InlineKeyboardButton("Link", callback_data="stktyp:link"),
         InlineKeyboardButton("Code", callback_data="stktyp:code")]
    ]
    await query.edit_message_text("Select stock type:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_STOCK_TYPE

async def adm_add_stock_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stk_type = query.data.split(':')[1]
    context.user_data['stk_type'] = stk_type
    
    await query.edit_message_text("Send content (For file: send document. For codes: bulk ok via newline):")
    return ADD_STOCK_CONTENT

async def adm_add_stock_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stk_type = context.user_data['stk_type']
    prod_id = context.user_data['stk_prod_id']
    
    count = 0
    if stk_type == 'file':
        if not update.message.document:
            await update.message.reply_text("Please send a document file.")
            return ADD_STOCK_CONTENT
        file_id = update.message.document.file_id
        file_name = getattr(update.message.document, "file_name", "UnknownFileName") or "UnknownFileName"
        content = f"{file_id}|{file_name}"
        await add_stock_item(prod_id, 'file', content)
        count = 1
    else:
        if not update.message.text:
            await update.message.reply_text("Please send text.")
            return ADD_STOCK_CONTENT
        if stk_type == 'code':
            lines = [line.strip() for line in update.message.text.split('\n') if line.strip()]
            for line in lines:
                await add_stock_item(prod_id, 'code', line)
            count = len(lines)
        else:
            await add_stock_item(prod_id, 'link', update.message.text)
            count = 1

    await update.message.reply_text(f"✅ Stock added! ({count} items)")

    # Notify favorites
    favs = await get_favorites(prod_id)
    if favs:
        from src.db import get_product
        prod = await get_product(prod_id)
        
        bot_username = context.bot.username
        for user_id in favs:
            try:
                # We should get user lang, but we'll default to EN here as fetching each user lang inside loop is slightly slower
                db_user = await get_user(user_id)
                lang = db_user['language'] if db_user else 'en'
                text = get_text(lang, 'restock_notification', title=prod[f'title_{lang}'], bot_username=bot_username, prod_id=prod_id)
                await context.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")

    return ConversationHandler.END

# --- Manage Balances ---
async def adm_bal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Enter User ID:")
    return BAL_USER_ID

async def adm_bal_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text)
    except:
        await update.message.reply_text("Invalid ID.")
        return BAL_USER_ID
    
    # Optional DB check
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("User not found. Try again:")
        return BAL_USER_ID
        
    context.user_data['bal_uid'] = uid
    await update.message.reply_text(f"User Balance: ${user['balance']:.2f}\nEnter amount to add/deduct:")
    return BAL_AMOUNT

async def adm_bal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text)
    except:
        await update.message.reply_text("Invalid amount.")
        return BAL_AMOUNT
        
    uid = context.user_data['bal_uid']
    await update_user_balance(uid, amt)
    
    await update.message.reply_text("✅ Balance updated!")
    return ConversationHandler.END


# --- Users List ---
async def adm_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    lang = db_user['language'] if db_user else 'en'
    
    users = await get_all_users()
    total = len(users)
    
    if lang == 'ru':
        header = f"👥 Зарегистрированные пользователи: {total}\n\n"
    else:
        header = f"👥 Registered Users: {total}\n\n"
        
    messages = []
    current_msg = header
    
    for i, u in enumerate(users, 1):
        username = f"@{u['username']}" if u.get('username') else "NoUsername"
        date_str = u['registered_at'].split()[0] if u.get('registered_at') else "Unknown"
        line = f"{i}. {username} | ID: {u['id']} | {date_str}\n"
        
        if len(current_msg) + len(line) > 4000:
            messages.append(current_msg)
            current_msg = header + line
        else:
            current_msg += line
            
    if current_msg != header:
        messages.append(current_msg)
        
    if not messages:
        await query.edit_message_text("No users found.")
        return
        
    for i, msg in enumerate(messages):
        if i == 0:
            await query.edit_message_text(msg)
        else:
            await context.bot.send_message(chat_id=user_id, text=msg)

# --- Ban Flow ---
async def adm_ban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Enter User ID to ban:")
    return BAN_USER_ID

async def adm_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        await set_user_ban(uid, True)
        await update.message.reply_text("✅ User banned.")
    except Exception as e:
        await update.message.reply_text("Error: invalid ID or DB error.")
    return ConversationHandler.END

async def adm_unban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Enter User ID to unban:")
    return UNBAN_USER_ID

async def adm_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        await set_user_ban(uid, False)
        await update.message.reply_text("✅ User unbanned.")
    except Exception as e:
        await update.message.reply_text("Error: invalid ID or DB error.")
    return ConversationHandler.END


# --- Publish/Hide Stock Details ---
async def adm_pub_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await set_setting('stock_update_msg', "📣 <b>Stock Update!</b> Fresh items are now available!")
    await query.edit_message_text("✅ Announcement published.")

async def adm_hide_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await delete_setting('stock_update_msg')
    await query.edit_message_text("✅ Announcement hidden.")


# --- Purchase History Flow ---
async def adm_history_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(':')
    page = int(data[2]) if len(data) > 2 else 0
    await _show_history(update, context, page)
    return ConversationHandler.END

async def _show_history(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, search_user_id=None, search_order_id=None):
    admin_id = update.effective_user.id
    db_user = await get_user(admin_id)
    lang = db_user['language'] if db_user else 'en'
    
    limit = 10
    offset = page * limit
    
    result = await get_purchases_page(offset, limit, search_user_id, search_order_id)
    total = result['total']
    records = result['data']
    
    from math import ceil
    total_pages = ceil(total / limit) if total > 0 else 1
    
    kb = []
    
    if total == 0:
        kb.append([InlineKeyboardButton("⬅ Back", callback_data="adm_history:back")])
        text = "No purchases found."
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
        return
        
    title = "🧾 Purchase History" if lang == 'en' else "🧾 История покупок"
    page_text = f"Page {page+1}/{total_pages}" if lang == 'en' else f"Стр. {page+1}/{total_pages}"
    
    lines = [f"<b>{title} ({page_text})</b>\n"]
    for idx, r in enumerate(records):
        d_raw = r['purchased_at']
        d_fmt = d_raw[:16] if d_raw else "N/A"
        
        ord_id = r['order_id']
        inv_id = r['invoice_id']
        inv_str = f" | Invoice: {inv_id}" if inv_id else ""
        
        username = f"@{r['username']}" if r['username'] else "NoUsername"
        uid = r['user_id']
        
        prod_name = r['title_en'] if lang == 'en' else r['title_ru']
        price = r['price_paid']
        
        used_bal = r['used_balance']
        paid_crypto = r['paid_crypto']
        
        if paid_crypto and used_bal:
            pay_str = f"PARTIAL (Balance ${used_bal:.2f} + Crypto ${paid_crypto:.2f})"
        elif paid_crypto:
            pay_str = f"CRYPTO (${paid_crypto:.2f})"
        else:
            pay_str = f"BALANCE (${price:.2f})"
            
        deltype = r['deliver_type']
        if deltype == 'file':
            del_str = "FILE"
        else:
            deltype_upper = deltype.upper() if deltype else "UNKNOWN"
            del_str = f"{deltype_upper}"
        
        real_idx = offset + idx + 1
        
        item_block = (
            f"<b>{real_idx})</b> {d_fmt} | Order #{ord_id}{inv_str}\n"
            f"   User: {username} | ID: <code>{uid}</code>\n"
            f"   Product: {prod_name}\n"
            f"   Price: ${price:.2f} | Pay: {pay_str}\n"
            f"   Delivered: {del_str}\n"
        )
        lines.append(item_block)
        
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"adm_history:page:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"adm_history:page:{page+1}"))
        
    if nav:
        kb.append(nav)
    
    btn_search_user = "🔎 Search by User ID" if lang == 'en' else "🔎 Поиск по ID юзера"
    btn_search_order = "🔎 Search by Order ID" if lang == 'en' else "🔎 Поиск по номеру заказа"
    
    kb.append([InlineKeyboardButton(btn_search_user, callback_data="adm_history:search_user")])
    kb.append([InlineKeyboardButton(btn_search_order, callback_data="adm_history:search_order")])
    kb.append([InlineKeyboardButton("⬅ Back to Admin" if lang == 'en' else "⬅ В меню", callback_data="adm_history:back")])
    
    text = "\n".join(lines)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def history_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    update.message = query.message
    await admin_cmd(update, context)
    return ConversationHandler.END

async def adm_search_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = update.effective_user.id
    db_user = await get_user(admin_id)
    lang = db_user['language'] if db_user else 'en'
    
    await query.edit_message_text(get_text(lang, 'admin_search_user'))
    return SEARCH_HISTORY_USER

async def adm_search_user_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Invalid ID. Action cancelled.")
        return ConversationHandler.END
        
    uid = int(text)
    await _show_history(update, context, page=0, search_user_id=uid)
    return ConversationHandler.END

async def adm_search_order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = update.effective_user.id
    db_user = await get_user(admin_id)
    lang = db_user['language'] if db_user else 'en'
    
    await query.edit_message_text(get_text(lang, 'admin_search_order'))
    return SEARCH_HISTORY_ORDER

async def adm_search_order_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Invalid ID. Action cancelled.")
        return ConversationHandler.END
        
    oid = int(text)
    await _show_history(update, context, page=0, search_order_id=oid)
    return ConversationHandler.END


def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update.message.reply_text("Admin action cancelled.")
    return ConversationHandler.END

def register_handlers(application: Application):
    application.add_handler(CommandHandler('admin', admin_cmd))
    
    # Product Conversation
    prod_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_add_prod_start, pattern='^adm_add_prod$')],
        states={
            ADD_PROD_CAT: [CallbackQueryHandler(adm_add_prod_cat, pattern='^selcat:')],
            ADD_PROD_TITLE_RU: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_prod_title_ru)],
            ADD_PROD_TITLE_EN: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_prod_title_en)],
            ADD_PROD_DESC_RU: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_prod_desc_ru)],
            ADD_PROD_DESC_EN: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_prod_desc_en)],
            ADD_PROD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_prod_price)],
        },
        fallbacks=[CommandHandler('cancel', cancel_admin)]
    )
    application.add_handler(prod_conv)

    # Category Conversation
    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_add_cat_start, pattern='^adm_add_cat_ru$')],
        states={
            ADD_CAT_RU: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_cat_ru)],
            ADD_CAT_EN: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_cat_en)],
        },
        fallbacks=[CommandHandler('cancel', cancel_admin)]
    )
    application.add_handler(cat_conv)

    # Stock Conversation
    stock_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_add_stock_start, pattern='^adm_add_stock$')],
        states={
            ADD_STOCK_CAT: [CallbackQueryHandler(adm_add_stock_cat, pattern='^stkcat:')],
            ADD_STOCK_PROD: [CallbackQueryHandler(adm_add_stock_prod, pattern='^stkprod:')],
            ADD_STOCK_TYPE: [CallbackQueryHandler(adm_add_stock_type, pattern='^stktyp:')],
            ADD_STOCK_CONTENT: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, adm_add_stock_content)],
        },
        fallbacks=[CommandHandler('cancel', cancel_admin)]
    )
    application.add_handler(stock_conv)

    # Balances Conversation
    bal_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_bal_start, pattern='^adm_balances$')],
        states={
            BAL_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_bal_user)],
            BAL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_bal_amount)],
        },
        fallbacks=[CommandHandler('cancel', cancel_admin)]
    )
    application.add_handler(bal_conv)
    
    # Ban Conversations
    ban_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_ban_start, pattern='^adm_ban$')],
        states={BAN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_ban_user)]},
        fallbacks=[CommandHandler('cancel', cancel_admin)]
    )
    application.add_handler(ban_conv)
    
    unban_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_unban_start, pattern='^adm_unban$')],
        states={UNBAN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_unban_user)]},
        fallbacks=[CommandHandler('cancel', cancel_admin)]
    )
    application.add_handler(unban_conv)

    application.add_handler(CallbackQueryHandler(adm_users, pattern='^adm_users$'))

    # History Search Conversations
    hist_search_user_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_search_user_start, pattern='^adm_history:search_user$')],
        states={SEARCH_HISTORY_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_search_user_process)]},
        fallbacks=[CommandHandler('cancel', cancel_admin)]
    )
    application.add_handler(hist_search_user_conv)
    
    hist_search_order_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_search_order_start, pattern='^adm_history:search_order$')],
        states={SEARCH_HISTORY_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_search_order_process)]},
        fallbacks=[CommandHandler('cancel', cancel_admin)]
    )
    application.add_handler(hist_search_order_conv)
    
    application.add_handler(CallbackQueryHandler(adm_history_page, pattern='^adm_history:page:'))
    application.add_handler(CallbackQueryHandler(history_back, pattern='^adm_history:back$'))

    # Single callback handlers
    application.add_handler(CallbackQueryHandler(adm_pub_stock, pattern='^adm_pub_stock$'))
    application.add_handler(CallbackQueryHandler(adm_hide_stock, pattern='^adm_hide_stock$'))

