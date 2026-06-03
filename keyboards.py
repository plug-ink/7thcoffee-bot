from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ================== КЛИЕНТ ==================
def get_client_keyboard():
    """Клавиатура клиента (только QR-код)"""
    from telegram import KeyboardButton, ReplyKeyboardMarkup

    keyboard = [[KeyboardButton("◾️QR-код")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ================== АДМИН - ГЛАВНОЕ МЕНЮ (ТОЛЬКО ИНЛАЙН) ==================
def get_admin_main_keyboard():
    """Главное меню админа с инлайн-кнопками"""
    keyboard = [
        [InlineKeyboardButton("📒 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📙 Баристы", callback_data="admin_baristas")],
        [InlineKeyboardButton("📣 Рассылка", callback_data="admin_broadcast")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ================== АДМИН - УПРАВЛЕНИЕ БАРИСТАМИ (ИНЛАЙН) ==================
def get_admin_barista_inline_keyboard():
    """Инлайн-клавиатура для управления баристами"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить баристу", callback_data="barista_add")],
        [InlineKeyboardButton("➖ Удалить баристу", callback_data="barista_remove")],
        [InlineKeyboardButton("📋 Список баристов", callback_data="barista_list")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_barista_back_keyboard():
    """Клавиатура с кнопкой назад для режима добавления/удаления"""
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_barista_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


# ================== АДМИН - УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ (ИНЛАЙН) ==================
def get_admin_users_inline_keyboard():
    """Инлайн-клавиатура для управления пользователями"""
    keyboard = [
        [InlineKeyboardButton("📋 Список пользователей", callback_data="users_list")],
        [InlineKeyboardButton("🔍 Найти пользователя", callback_data="users_search")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_users_back_keyboard():
    """Клавиатура с кнопкой назад для поиска"""
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_users_menu")]]
    return InlineKeyboardMarkup(keyboard)
