from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

# ================== КЛИЕНТ (CLIENT) ==================
def get_client_keyboard():
    """Клавиатура клиента"""
    keyboard = [
        [KeyboardButton("◾️QR-код")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_client_keyboard_with_back():
    """Клавиатура клиента (с кнопкой Назад)""")
    keyboard = [
        [KeyboardButton("◾️QR-код")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== БАРИСТА (BARISTA) ==================
def get_barista_keyboard():
    """Клавиатура баристы"""
    keyboard = [
        [KeyboardButton("✔ Начислить")],
        [KeyboardButton("📲 Добавить номер")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_barista_keyboard_with_back():
    """Клавиатура баристы (с кнопкой Назад)""")
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

# ================== АДМИН: ГЛАВНОЕ МЕНЮ (ADMIN: MAIN MENU) ==================

def get_admin_main_keyboard():
    keyboard = [
        [KeyboardButton("📙 Баристы"), KeyboardButton("📒 Посетители")],
        [KeyboardButton("📣 Рассылка"), KeyboardButton("⚙️ Опции")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== АДМИН: УПРАВЛЕНИЕ БАРИСТАМИ (ADMIN: BARISTA MANAGEMENT) ==================

def get_admin_barista_keyboard():
    keyboard = [
        [KeyboardButton("➕ Добавить"), KeyboardButton("➖ Удалить")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== АДМИН: УПРАВЛЕНИЕ ПОСЕТИТЕЛЯМИ (ADMIN: CUSTOMER MANAGEMENT) ==================
def get_admin_customers_keyboard_after_list():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🔙 Назад")]],
        resize_keyboard=True
    )

# ================== АДМИН: НАСТРОЙКИ (ADMIN: SETTINGS) ==================

def get_admin_settings_keyboard():
    keyboard = [
        [KeyboardButton("📝 Изменить акции")],
        [KeyboardButton("🤎 Я гость"), KeyboardButton("🐾 Я бариста")],
        [KeyboardButton("🔙 Назад ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== АДМИН: УПРАВЛЕНИЕ АКЦИЯМИ (ADMIN: PROMOTION MANAGEMENT) ==================

def get_admin_promotion_keyboard():
    keyboard = [
        [KeyboardButton("📝 Название"), KeyboardButton("7️⃣ Условие")],
        [KeyboardButton("📖 Описание")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================== ПЕРЕКЛЮЧЕНИЕ РОЛЕЙ (ROLE SWITCHING) ==================

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

