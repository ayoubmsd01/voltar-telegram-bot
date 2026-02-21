import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, TypeHandler
)
from telegram.constants import ParseMode
from telegram.ext import ApplicationHandlerStop

from src.db import get_user, create_user, update_user_language, check_user_banned
from src.locales import get_text
from src.config import ADMIN_IDS

logger = logging.getLogger(__name__)

async def ban_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Silent ban mechanism: if user is banned, drop update silently."""
    if update.effective_user:
        user_id = update.effective_user.id
        # Cache check could be added, but for now we do DB directly
        is_banned = await check_user_banned(user_id)
        if is_banned:
            raise ApplicationHandlerStop

def get_main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = [
        [get_text(lang, 'btn_products'), get_text(lang, 'btn_stock')],
        [get_text(lang, 'btn_profile'), get_text(lang, 'btn_rules')],
        [get_text(lang, 'btn_help'), get_text(lang, 'btn_projects')]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    
    if not db_user:
        await create_user(user_id, 'en') # default to en, ask to choose
        db_user = await get_user(user_id)

    # If it's the first time or no language explicitly set (default is just en initially, let's ask)
    # Actually wait! Let's check if they chose a language by using a flag, or just ask every start!
    # "ON /start: Check if the user exists in the database. If not, prompt them to select a language..."
    
    args = context.args
    # Check for deep linking e.g. /start cat_1 or /start prod_2
    
    if db_user:
        # Check if deep linking
        if args:
            lang = db_user['language']
            # Forward to catalog handling
            from .catalog import handle_deep_link
            await handle_deep_link(update, context, args[0], lang)
            return

    # Prompt language if new, or let's say we prompt if no arguments
    # Wait, the spec says: ON `/start`: Check if the user exists in the database. If not, prompt them to select a language using Inline Buttons ("🇷🇺 Русский", "🇬🇧 English"). Save this preference in the users table.
    # We will use db_user flag
    # If they are newly created, we need a way to know. 
    # Let's see if total_spent == 0 and we JUST created them? No, we can just do checking via query.
    pass

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    args = context.args
    
    if not db_user:
        # User not in DB
        username = update.effective_user.username
        await create_user(user_id, 'en', username)
        # Prompt select language
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
        ])
        await update.message.reply_text("Выберите язык / Select language:", reply_markup=keyboard)
        return
        
    lang = db_user['language']
    
    if args:
        from .catalog import handle_deep_link
        await handle_deep_link(update, context, args[0], lang)
        return
    
    await update.message.reply_text(
        get_text(lang, 'main_menu'),
        reply_markup=get_main_keyboard(lang)
    )

async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split('_')[1]
    user_id = update.effective_user.id
    
    await update_user_language(user_id, lang)
    await query.edit_message_text(get_text(lang, 'lang_set'))
    
    await context.bot.send_message(
        chat_id=user_id, 
        text=get_text(lang, 'main_menu'),
        reply_markup=get_main_keyboard(lang)
    )

async def rules_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    lang = db_user['language'] if db_user else 'en'
    await update.message.reply_text(get_text(lang, 'rules_text'), parse_mode=ParseMode.HTML)

async def help_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    lang = db_user['language'] if db_user else 'en'
    await update.message.reply_text(get_text(lang, 'help_text'))

async def projects_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = await get_user(user_id)
    lang = db_user['language'] if db_user else 'en'
    await update.message.reply_text(get_text(lang, 'projects_text'))

def register_handlers(application: Application):
    application.add_handler(TypeHandler(Update, ban_middleware), group=-1)
    
    application.add_handler(CommandHandler('start', start_cmd))
    application.add_handler(CallbackQueryHandler(lang_callback, pattern='^lang_'))
    
    # Catching menu buttons across any language
    # We can use regex on translations
    msg_ru_en = lambda k: f"^({get_text('ru', k)}|{get_text('en', k)})$"
    
    application.add_handler(MessageHandler(filters.Regex(msg_ru_en('btn_rules')), rules_text))
    application.add_handler(MessageHandler(filters.Regex(msg_ru_en('btn_help')), help_text))
    application.add_handler(MessageHandler(filters.Regex(msg_ru_en('btn_projects')), projects_text))
