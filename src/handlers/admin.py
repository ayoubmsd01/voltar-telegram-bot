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
    update_user_balance, set_setting, delete_setting, set_user_ban, get_favorites, get_all_users
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
        [InlineKeyboardButton("🇷🇺 👥 Пользователи" if lang == 'ru' else "🇬🇧 👥 Users", callback_data="adm_users")]
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
        await add_stock_item(prod_id, 'file', file_id)
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
        
        for user_id in favs:
            try:
                # We should get user lang, but we'll default to EN here as fetching each user lang inside loop is slightly slower
                db_user = await get_user(user_id)
                lang = db_user['language'] if db_user else 'en'
                text = get_text(lang, 'restock_notification', title=prod[f'title_{lang}'])
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

    # Single callback handlers
    application.add_handler(CallbackQueryHandler(adm_pub_stock, pattern='^adm_pub_stock$'))
    application.add_handler(CallbackQueryHandler(adm_hide_stock, pattern='^adm_hide_stock$'))

