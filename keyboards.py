from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

# ================== КЛИЕНТ ==================
def get_client_keyboard():
    """Клавиатура клиента (только 2 кнопки)"""
    keyboard = [
        [KeyboardButton("◾️QR-код")]  # ← УБРАЛИ "🎁 Акции"
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_client_keyboard_with_back():
    """Клавиатура клиента для админа в режиме клиента"""
    keyboard = [
        [KeyboardButton("◾️QR-код")],
        [KeyboardButton("🔙 Назад")]  # ← УБРАЛИ "🎁 Акции"
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== БАРИСТА ==================
def get_barista_keyboard():
    """Клавиатура баристы с кнопкой +1 и добавлением клиента"""
    keyboard = [
        [KeyboardButton("✔ Начислить")],
        [KeyboardButton("📲 Добавить номер")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_barista_keyboard_with_back():
    """Клавиатура баристы с кнопкой +1 (для админа)"""
    keyboard = [
        [KeyboardButton("✔ Начислить")],
        [KeyboardButton("📲 Добавить номер")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_barista_action_keyboard():
    """Клавиатура после сканирования QR"""
    keyboard = [
        [KeyboardButton("✔ Засчитать покупку")],
        [KeyboardButton("❌ Отменить")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== АДМИН - ГЛАВНОЕ МЕНЮ ==================
def get_admin_main_keyboard():
    keyboard = [
        [KeyboardButton("📙 Баристы"), KeyboardButton("📒 Посетители")],
        [KeyboardButton("📣 Рассылка"), KeyboardButton("⚙️ Опции")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== АДМИН - УПРАВЛЕНИЕ БАРИСТАМИ ==================
def get_admin_barista_keyboard():
    keyboard = [
        [KeyboardButton("➕ Добавить"), KeyboardButton("➖ Удалить")],
        [KeyboardButton("🔙 Назад")]  # ← УБРАЛИ "📋 Список"
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== АДМИН - УПРАВЛЕНИЕ ПОСЕТИТЕЛЯМИ ==================
def get_admin_customers_keyboard_after_list():
    """То же самое - только Назад после списка"""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🔙 Назад")]],
        resize_keyboard=True
    )

# ================== АДМИН - НАСТРОЙКИ ==================
def get_admin_settings_keyboard():
    keyboard = [
        [KeyboardButton("📝 Изменить акции")],
        [KeyboardButton("🤎 Я гость"), KeyboardButton("🐾 Я бариста")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== АДМИН - УПРАВЛЕНИЕ АКЦИЯМИ ==================
def get_admin_promotion_keyboard():
    keyboard = [
        [KeyboardButton("📝 Название"), KeyboardButton("7️⃣ Условие")],
        [KeyboardButton("📖 Описание")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== ПЕРЕКЛЮЧЕНИЕ РОЛЕЙ ==================
def get_role_switcher_keyboard():
    keyboard = [
        [KeyboardButton("👑 Режим админа")],
        [KeyboardButton("👨‍💼 Я бариста"), KeyboardButton("👤 Я ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_customers_keyboard():
    """Клавиатура для раздела пользователей (только Назад)"""
    keyboard = [
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

