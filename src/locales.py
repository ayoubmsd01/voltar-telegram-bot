LOCALES = {
    'ru': {
        'select_lang': "Выберите язык:",
        'lang_set': "✅ Язык установлен на Русский.",
        'main_menu': "Главное меню:",
        'btn_products': "🛍 Товары",
        'btn_stock': "📦 Наличие",
        'btn_profile': "👤 Профиль",
        'btn_rules': "📖 Правила",
        'btn_help': "💬 Помощь",
        'btn_projects': "🌐 Наши проекты",
        'stock_empty': "📦 В наличии пока нет товаров.",
        'stock_header': "📦 Наличие товаров:",
        'stock_format': "— — — <a href=\"https://t.me/{bot_username}?start=cat_{cat_id}\">{cat_name}</a> — — —",
        'stock_item': "<a href=\"https://t.me/{bot_username}?start=prod_{prod_id}\">{prod_name}</a> | {stock} шт. | ${price}",
        'products_select_cat': "Выберите категорию:",
        'products_select_item': "Выберите товар:",
        'btn_back': "⬅️ Назад",
        'product_page': "<b>{title}</b>\n\n{desc}\n\nЦена: ${price}\nВ наличии: {stock} шт.",
        'btn_buy': "✅ Купить",
        'btn_add_favorite': "⭐ В избранное",
        'out_of_stock': "❌ Нет в наличии",
        'profile_info': "<b>👤 Профиль</b>\n\nID: <code>{user_id}</code>\nБаланс: ${balance}\nВсего потрачено: ${spent}\nДата регистрации: {reg_date}",
        'btn_topup': "💳 Пополнить баланс",
        'btn_purchases': "🛒 Мои покупки",
        'btn_topups': "💵 Мои пополнения",
        'btn_coupon': "🎟 Активировать купон",
        'topup_enter_amount': "Введите сумму для пополнения (в USD):",
        'invalid_amount': "❌ Неверная сумма. Введите число (например, 10.50):",
        'topup_invoice_created': "Счет создан. Оплатите ${amount}",
        'btn_check_payment': "✅ Проверить оплату",
        'btn_cancel_order': "❌ Отменить заказ",
        'invoice_paid_success': "✅ Баланс успешно пополнен на ${amount}",
        'invoice_not_paid': "❌ Оплата не найдена.",
        'purchase_success': "✅ Покупка успешна! Вот ваш товар:\n\n{content}",
        'purchase_insufficient_payment': "Ожидание оплаты...",
        'restock_notification': "📣 Внимание! Товар <b>{title}</b> снова в наличии!\n\nКупить: https://t.me/{bot_username}?start=prod_{prod_id}",
        'rules_text': "<b>🇷🇺 Правила магазина</b>\n\n"
                      "🔁 Замена производится в следующих случаях:\n"
                      "• Аккаунт не валид\n\n"
                      "❌ Замена НЕ производится в следующих случаях:\n"
                      "• БАН при заливе\n"
                      "• БАН при входе через софт\n\n"
                      "⏳ Срок проверки аккаунта составляет 30 минут после покупки.\n"
                      "По истечении этого времени претензии не принимаются.\n\n"
                      "🛡 Гарантия распространяется только на валид.\n\n"
                      "🛒 Покупая товар, вы автоматически соглашаетесь с данными правилами.",
        'help_text': "💬 По всем вопросам обращайтесь в поддержку.",
        'projects_text': "🌐 Список наших проектов...",
        # Admin
        'admin_panel': "🛠 Панель администратора",
        'admin_add_product': "➕ Добавить товар",
        'admin_add_stock': "➕ Добавить Stock",
        'admin_manage_balances': "💰 Управление балансами",
        'admin_publish_stock': "📣 Опубликовать наличие",
        'admin_hide_stock': "🛑 Скрыть наличие",

        'admin_ban_user': "🚫 Забанить пользователя",
        'admin_unban_user': "✅ Разбанить",
        'admin_enter_cat_ru': "Введите название категории (RU):",
        'admin_enter_cat_en': "Введите название категории (EN):",
        'admin_enter_title_ru': "Введите название товара (RU):",
        'admin_enter_title_en': "Введите название товара (EN):",
        'admin_enter_desc_ru': "Введите описание (RU):",
        'admin_enter_desc_en': "Введите описание (EN):",
        'admin_enter_price': "Введите цену (USD):",
        'admin_product_added': "✅ Товар успешно добавлен!",
        'admin_stock_type': "Выберите тип товара (file/link/code):",
        'admin_stock_content': "Отправьте содержимое (Для кодов можно использовать перенос строки для добавления сразу нескольких):",
        'admin_stock_added': "✅ Stock добавлен!",

        'admin_user_banned': "✅ Пользователь забанен.",
        'admin_user_unbanned': "✅ Пользователь разбанен.",
        'admin_balance_enter_id': "Введите ID пользователя:",
        'admin_balance_enter_amount': "Введите сумму (может быть отрицательной для снятия):",
        'admin_balance_success': "✅ Баланс изменен.",
        'btn_purchase_history': "🧾 История покупок",
        'admin_search_user': "Введите ID пользователя для поиска:",
        'admin_search_order': "Введите ID заказа для поиска:",
    },
    'en': {
        'select_lang': "Select language:",
        'lang_set': "✅ Language set to English.",
        'main_menu': "Main Menu:",
        'btn_products': "🛍 Products",
        'btn_stock': "📦 Stock",
        'btn_profile': "👤 Profile",
        'btn_rules': "📖 Rules",
        'btn_help': "💬 Help",
        'btn_projects': "🌐 Our projects",
        'stock_empty': "📦 No products available yet.",
        'stock_header': "📦 Stock available:",
        'stock_format': "— — — <a href=\"https://t.me/{bot_username}?start=cat_{cat_id}\">{cat_name}</a> — — —",
        'stock_item': "<a href=\"https://t.me/{bot_username}?start=prod_{prod_id}\">{prod_name}</a> | {stock} pcs. | ${price}",
        'products_select_cat': "Select category:",
        'products_select_item': "Select product:",
        'btn_back': "⬅️ Back",
        'product_page': "<b>{title}</b>\n\n{desc}\n\nPrice: ${price}\nAvailable: {stock} pcs.",
        'btn_buy': "✅ Buy",
        'btn_add_favorite': "⭐ Add to favorites",
        'out_of_stock': "❌ Out of Stock",
        'profile_info': "<b>👤 Profile</b>\n\nID: <code>{user_id}</code>\nBalance: ${balance}\nTotal spent: ${spent}\nReg Date: {reg_date}",
        'btn_topup': "💳 Top up balance",
        'btn_purchases': "🛒 My purchases",
        'btn_topups': "💵 My top-ups",
        'btn_coupon': "🎟 Activate coupon",
        'topup_enter_amount': "Enter amount to top up (in USD):",
        'invalid_amount': "❌ Invalid amount. Enter a number (e.g., 10.50):",
        'topup_invoice_created': "Invoice created. Please pay ${amount}",
        'btn_check_payment': "✅ Check Payment",
        'btn_cancel_order': "❌ Cancel Order",
        'invoice_paid_success': "✅ Balance successfully topped up by ${amount}",
        'invoice_not_paid': "❌ Payment not found.",
        'purchase_success': "✅ Purchase successful! Here is your item:\n\n{content}",
        'purchase_insufficient_payment': "Awaiting payment...",
        'restock_notification': "📣 Attention! <b>{title}</b> is back in stock!\n\nBuy now: https://t.me/{bot_username}?start=prod_{prod_id}",
        'rules_text': "<b>🇬🇧 Store Rules</b>\n\n"
                      "🔁 Replacement is provided only in the following case:\n"
                      "• Account is not valid\n\n"
                      "❌ Replacement is NOT provided in the following cases:\n"
                      "• BAN during traffic upload\n"
                      "• BAN when logging in via software\n\n"
                      "⏳ Account verification period is 30 minutes after purchase.\n"
                      "After this time, no claims will be accepted.\n\n"
                      "🛡 Warranty applies only to invalid accounts.\n\n"
                      "🛒 By purchasing the product, you automatically agree to these rules.",
        'help_text': "💬 Please contact support for assistance.",
        'projects_text': "🌐 List of our projects...",
        # Admin
        'admin_panel': "🛠 Admin Panel",
        'admin_add_product': "➕ Add Product",
        'admin_add_stock': "➕ Add Stock",
        'admin_manage_balances': "💰 Manage Balances",
        'admin_publish_stock': "📣 Publish Stock Update",
        'admin_hide_stock': "🛑 Hide Stock Update",

        'admin_ban_user': "🚫 Ban User",
        'admin_unban_user': "✅ Unban User",
        'admin_enter_cat_ru': "Enter category name (RU):",
        'admin_enter_cat_en': "Enter category name (EN):",
        'admin_enter_title_ru': "Enter product title (RU):",
        'admin_enter_title_en': "Enter product title (EN):",
        'admin_enter_desc_ru': "Enter description (RU):",
        'admin_enter_desc_en': "Enter description (EN):",
        'admin_enter_price': "Enter price (USD):",
        'admin_product_added': "✅ Product added successfully!",
        'admin_stock_type': "Select item type (file/link/code):",
        'admin_stock_content': "Send content (For codes you can use newlines to add multiple):",
        'admin_stock_added': "✅ Stock added!",

        'admin_user_banned': "✅ User banned.",
        'admin_user_unbanned': "✅ User unbanned.",
        'admin_balance_enter_id': "Enter User ID:",
        'admin_balance_enter_amount': "Enter amount (can be negative to deduct):",
        'admin_balance_success': "✅ Balance updated.",
        'btn_purchase_history': "🧾 Purchase History",
        'admin_search_user': "Enter User ID to search:",
        'admin_search_order': "Enter Order ID to search:",
    }
}

def get_text(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in ('ru', 'en') else 'en'
    text = LOCALES[lang].get(key, f"_{key}_")
    if kwargs:
        return text.format(**kwargs)
    return text
