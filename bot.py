from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import datetime
from config import BOT_TOKEN, ADMIN_IDS
from database import Database
from qr_manager import generate_qr_code, parse_qr_data, read_qr_from_image
from keyboards import *
async def notify_customer(bot, customer_id, new_count, required):
    remaining = max(0, required - new_count)
    if new_count == 0:
        await bot.send_message(
            customer_id,
            "🎉 Поздравляем, напиток в подарок ваш! Покажите это сообщение бариста."
        )
    else:
        await bot.send_message(
            customer_id,
            f"☕ +1 к вашей карте. До бесплатного напитка осталось: {remaining}"
        )


db = Database()

# ================== СИСТЕМА СОСТОЯНИЙ ==================
def set_user_state(context, state):
    context.user_data['state'] = state

def get_user_state(context):
    return context.user_data.get('state', 'main')

def is_admin(user_id):
    return user_id in ADMIN_IDS     # ← список из config.py

def get_user_role(user_id, username):
    """Определяет роль пользователя"""
    if is_admin(user_id):
        return 'admin'
    elif username and db.is_user_barista(username):
        return 'barista'
    else:
        return 'client'

# ================== ОСНОВНЫЕ КОМАНДЫ ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    db.get_or_create_user(user_id, user.username, user.first_name, user.last_name)
    set_user_state(context, 'main')
    
    role = get_user_role(user_id, user.username)
    
    if role == 'admin':
        await show_admin_main(update)
    elif role == 'barista':
        await show_barista_main(update)
    else:
        await show_client_main(update)
    print(f"🔍 user_id={user_id}, username=@{user.username}")   # ← добавь
    ...
    print(f"📨 роль={get_user_role(user_id, user.username)}")
# ================== РЕЖИМ КЛИЕНТА ==================
async def show_client_main(update: Update):
    user = update.effective_user
    role = get_user_role(user.id, user.username)

    text = """
👤 Добро пожаловать в CoffeeRina!

Участвуйте в акции и получайте бесплатные напитки!
    """

    keyboard = get_client_keyboard_with_back() if role == 'admin' else get_client_keyboard()

    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)

async def handle_client_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "📱 Мой QR":
        await send_qr_code(update, user_id)
    elif text == "🎁 Акции":
        await show_promotion_info(update)
    elif text == "🔙 Назад" and is_admin(user_id):
        set_user_state(context, 'main')
        await show_admin_main(update)

# ================== РЕЖИМ БАРИСТЫ ==================
async def show_barista_main(update: Update):
    """Показывает меню баристы с разными кнопками для админа и баристы"""
    user = update.effective_user
    role = get_user_role(user.id, user.username)
    
    text = """
👨‍💼 Режим баристы CoffeeRina

Готов к работе!
    """
    
    if role == 'admin':
        # Админ видит кнопку "Назад" для возврата в настройки
        if update.message:
            await update.message.reply_text(text, reply_markup=get_barista_keyboard_with_back())
        else:
            await update.callback_query.edit_message_text(text, reply_markup=get_barista_keyboard_with_back())
    else:
        # Бариста видит только основные кнопки
        if update.message:
            await update.message.reply_text(text, reply_markup=get_barista_keyboard())
        else:
            await update.callback_query.edit_message_text(text, reply_markup=get_barista_keyboard())

async def handle_barista_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "📷 Скан QR":
        set_user_state(context, 'scanning_qr')
        await update.message.reply_text("📸 Отправьте фото QR-кода")
    elif text == "ℹ️ Акции":
        await show_barista_promotion_info(update)
    elif text == "🔙 Назад" and is_admin(user_id):
        set_user_state(context, 'main')
        await show_admin_main(update)

async def handle_qr_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового ввода QR-кода"""
    user_input = update.message.text
    user_id = update.effective_user.id
    
    # Парсим данные QR
    customer_id = parse_qr_data(user_input)
    if not customer_id:
        await update.message.reply_text("❌ Неверный формат QR-кода. Формат: coffeerina:123456")
        return
    
    await process_customer_scan(update, context, customer_id)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фотографии с QR-кодом"""
    state = get_user_state(context)
    user_id = update.effective_user.id
    
    if state != 'scanning_qr':
        await update.message.reply_text("❌ Сначала нажмите '📷 Скан QR' для активации режима сканирования")
        return
    
    try:
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        await update.message.reply_text("🔍 Обрабатываю QR-код...")
        
        # Распознаем QR-код
        qr_data = read_qr_from_image(bytes(photo_bytes))
        if not qr_data:
            await update.message.reply_text("❌ Не удалось распознать QR-код. Попробуйте ввести вручную: coffeerina:123456")
            return
        
        customer_id = parse_qr_data(qr_data)
        if not customer_id:
            await update.message.reply_text("❌ Неверный формат распознанного QR-кода")
            return
        
        await process_customer_scan(update, context, customer_id)
        # Удаляем фото, которое прислал бариста
        await update.message.delete()

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обработки фото: {e}")

async def process_customer_scan(update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: int):
    """Обработка сканирования клиента"""
    # Получаем данные клиента
    purchases = db.get_user_stats(customer_id)
    if purchases is None:
        await update.message.reply_text("❌ Клиент не найден в базе данных.")
        set_user_state(context, 'main')
        return
    
    # ← ДОБАВИТЬ: Получаем информацию о пользователе
    cursor = db.conn.cursor()
    cursor.execute('SELECT username, first_name, last_name FROM users WHERE user_id = ?', (customer_id,))
    user_info = cursor.fetchone()
    
    username = user_info[0] if user_info and user_info[0] else "Не указан"
    first_name = user_info[1] if user_info and user_info[1] else ""
    last_name = user_info[2] if user_info and user_info[2] else ""
    
    # Формируем имя пользователя
    user_display_name = f"@{username}" if username != "Не указан" else f"{first_name} {last_name}".strip()
    if not user_display_name:
        user_display_name = "Гость"
    
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7
    remaining = max(0, required - purchases)
    
    # ← ИЗМЕНИТЬ текст: убрать ID, добавить username
    text = f"""
📋 Данные клиента:

👤 Пользователь: {user_display_name}
📊 Покупок: {purchases}/{required}
🎯 До бесплатного напитка: {remaining}

{'🎉 Бесплатный напиток доступен!' if purchases >= required else 'Продолжайте в том же духе!'}
    """
    
    # Сохраняем ID клиента для дальнейших действий
    context.user_data['current_customer'] = customer_id
    set_user_state(context, 'barista_action')
    
    # ОДИНАКОВЫЕ КНОПКИ ДЛЯ ВСЕХ ПОСЛЕ СКАНИРОВАНИЯ
    keyboard = [
        [KeyboardButton("✅ Засчитать покупку")],
        [KeyboardButton("🔙 Назад")]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)
# ================== РЕЖИМ АДМИНА ==================
async def show_admin_main(update: Update):
    text = """
👑 Панель администратора CoffeeRina

Выберите раздел для управления:
    """
    if update.message:
        await update.message.reply_text(text, reply_markup=get_admin_main_keyboard())
    else:
        await update.callback_query.edit_message_text(text, reply_markup=get_admin_main_keyboard())

async def handle_admin_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "👥 Баристы":
        set_user_state(context, 'admin_barista')
        await show_barista_management(update)
    elif text == "👤 Посетители":
        set_user_state(context, 'admin_customers')
        await show_all_customers(update)
    elif text == "⚙️ Настройки":
        set_user_state(context, 'admin_settings')
        await show_admin_settings(update)

async def show_barista_management(update: Update):
    baristas = db.get_all_baristas()
    text = "👥 Управление баристами:\n\n"

    if baristas:
        for barista in baristas:
            username = barista[1]          # ← только username
            text += f"@{username}\n"
    else:
        text += "Баристы не добавлены"

    text += "\nВыберите действие:"
    await update.message.reply_text(text, reply_markup=get_admin_barista_keyboard())
async def show_customer_management(update: Update):
    text = "👤 Управление посетителями\n\nИспользуйте кнопки ниже для поиска и управления клиентами"
    await update.message.reply_text(text, reply_markup=get_admin_customers_keyboard())
async def show_all_customers(update: Update):
    print('[DEBUG] show_all_customers вызвана')
    users = db.get_all_users()  # ← нужно добавить в database.py
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    if not users:
        text = "📂 Клиентов пока нет."
    else:
        text = "📋 Список пользователей:\n\n"
        for u in users:
            user_id, username, first_name, last_name, purchases = u
            print(f"[DEBUG] user_id={user_id}, username='{username}', first_name='{first_name}', last_name='{last_name}'")
            name = f"@{username}" if username else f"{first_name or ''} {last_name or ''}".strip() or f"Гость (id:{user_id})"
            text += f"{name}, {purchases}/{required}\n"
            
    await update.message.reply_text(
    text,
    reply_markup=get_admin_customers_keyboard_after_list()  # кнопка «Найти» + «Назад»
    )
async def show_admin_settings(update: Update):
    promotion = db.get_promotion()
    text = f"""
⚙️ Настройки системы

Текущая акция: {promotion[1] if promotion else 'Не настроена'}
Условие: {promotion[2] if promotion else 7} покупок → бесплатный напиток

Выберите раздел для настройки:
    """
    await update.message.reply_text(text, reply_markup=get_admin_settings_keyboard())

async def handle_admin_barista_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "➕ Добавить":
        set_user_state(context, 'adding_barista')
        await update.message.reply_text("Введите @username баристы для добавления (без @):")
    elif text == "➖ Удалить":
        set_user_state(context, 'removing_barista')
        await update.message.reply_text("Введите @username баристы для удаления (без @):")
    elif text == "📋 Список":
        await show_barista_management(update)
    elif text == "🔙 Назад":
        set_user_state(context, 'main')
        await show_admin_main(update)

async def handle_admin_customer_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    print("DEBUG admin_customers text:", text)   # ← добавь сюда

    if text == "🔍 Найти пользователя":
        print("DEBUG: нажата кнопка Найти пользователя")   # ← и сюда
        set_user_state(context, 'finding_customer_by_username')
        await update.message.reply_text("Введите @username гостя (без @):")
        return

    # остальные elif...

async def handle_admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📝 Изменить акции":
        set_user_state(context, 'promotion_management')
        await show_promotion_management(update)
    elif text == "👤 Режим клиента":
        set_user_state(context, 'client_mode')
        await show_client_main(update)
    elif text == "👨‍💼 Режим бариста":
        set_user_state(context, 'barista_mode')
        await show_barista_main(update)
    elif text == "🔙 Назад":
        set_user_state(context, 'main')
        await show_admin_main(update)

async def show_promotion_management(update: Update):
    promotion = db.get_promotion()
    text = f"""
📝 Управление акциями

Текущая акция: {promotion[1]}
Условие: каждые {promotion[2]} покупок
Описание: {promotion[3] if promotion[3] else 'Нет описания'}

Выберите что изменить:
    """
    await update.message.reply_text(text, reply_markup=get_admin_promotion_keyboard())

async def handle_promotion_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    print(f"[DEBUG] promotion_management текст кнопки: '{text}'")

    # --- новое простое условие ---
    if "Условие" in text:
        print("[DEBUG] нажата кнопка Условие")
        set_user_state(context, 'changing_promotion_condition')
        await update.message.reply_text("Введите новое количество покупок для акции (например: 7):")
        return
    elif "Название" in text:
        set_user_state(context, 'changing_promotion_name')
        await update.message.reply_text("Введите новое название акции:")
        return

    elif "Описание" in text:
        set_user_state(context, 'changing_promotion_description')
        await update.message.reply_text("Введите новое описание акции:")
        return
    elif text == "🔙 Назад":
        set_user_state(context, 'admin_settings')
        await show_admin_settings(update)

# ================== ОБРАБОТКА ПОИСКА КЛИЕНТА ==================
async def handle_customer_search(update: Update, context: ContextTypes.DEFAULT_TYPE, search_query: str):
    """Обработка поиска клиента по @username"""
    
    # Убираем поиск по ID, оставляем только username
    username_input = search_query.replace('@', '').strip()
    
    if not username_input:
        await update.message.reply_text("❌ Введите корректный @username")
        set_user_state(context, 'admin_customers')
        return
    
    # Ищем пользователя по username
    user_data = db.get_user_by_username_exact(username_input)
    
    if user_data:
        customer_id, username, first_name, last_name = user_data
        purchases = db.get_user_stats(customer_id)
        promotion = db.get_promotion()
        required = promotion[2] if promotion else 7
        
        # Формируем красивое имя
        user_display_name = f"@{username}" if username else f"{first_name} {last_name}".strip()
        if not user_display_name:
            user_display_name = "Гость"
        
        text = f"""
📋 Найден пользователь:

👤 {user_display_name}
📊 Покупок: {purchases}/{required}
🎯 До бесплатного напитка: {max(0, required - purchases)}

{'🎉 Бесплатный напиток доступен!' if purchases >= required else 'Продолжайте в том же духе!'}
        """
        
        # ← ВСТАВИТЬ СЮДА ↓↓↓
        keyboard = [
            [
                InlineKeyboardButton("➕ Начислить", callback_data=f"add_{customer_id}"),
                InlineKeyboardButton("➖ Отменить", callback_data=f"remove_{customer_id}")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_customers")]
        ]
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("❌ Пользователь не найден")
    
    set_user_state(context, 'admin_customers')
# ================== ОБРАБОТКА CALLBACK QUERIES ==================
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Простая обработка - если остались старые callback'и, просто закрываем их
    if data.startswith('add_') or data.startswith('remove_') or data.startswith('cancel_') or data == 'cancel':
        await query.edit_message_text("🔄 Это меню устарело. Используйте новые кнопки ниже.")
        set_user_state(context, 'main')
        
        # Показываем главное меню
        user = query.from_user
        role = get_user_role(user.id, user.username)
        
        if role == 'barista':
            await show_barista_main(update)
        elif role == 'admin':
            await show_admin_main(update)
        else:
            await show_client_main(update)
# ================== БАЗОВЫЕ ФУНКЦИИ ==================
async def send_qr_code(update: Update, user_id: int):
    qr_image = generate_qr_code(user_id)
    caption = "📱 Ваш персональный QR-код\n\nПокажите его баристе при заказе напитка"
    await update.message.reply_photo(photo=qr_image, caption=caption)

async def show_user_status(update: Update, user_id: int):
    purchases = db.get_user_stats(user_id)
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7
    remaining = max(0, required - purchases)
    
    text = f"""
📊 Ваш статус:

Покупок: {purchases}/{required}
До бесплатного напитка: {remaining}

{'🎉 Следующий напиток бесплатный!' if purchases >= required else 'Продолжайте в том же духе!'}
    """
    await update.message.reply_text(text)

async def show_promotion_info(update: Update):
    promotion = db.get_promotion()
    user_id = update.effective_user.id
    purchases = db.get_user_stats(user_id)
    required = promotion[2] if promotion else 7
    remaining = max(0, required - purchases)

    if promotion:
        text = (
            f"🎁 {promotion[1]}\n\n"
            f"{promotion[3] if promotion[3] else 'Покажите QR-код при каждой покупке'}\n\n"
            f"📊 Ваш прогресс: {purchases}/{required}\n"
            f"🎯 До напитка в подарок: {remaining}"
        )
        if purchases >= required:
            text += "\n\n🎉 Следующий напиток в подарок!"
    else:
        text = "Акция ещё не настроена"

    await update.message.reply_text(text)

async def show_barista_promotion_info(update: Update):
    promotion = db.get_promotion()
    if promotion:
        text = f"""
🎁 Информация об акции:

{promotion[1]}
{promotion[3] if promotion[3] else 'Клиент показывает QR-код при каждой покупке'}

Условие: {promotion[2]} покупок → бесплатный напиток

📋 Инструкция:
1. Клиент показывает QR-код
2. Вы сканируете его через "Скан QR"
3. Нажимаете "✅ Засчитать покупку"
4. Система автоматически обновляет счетчик
        """
    else:
        text = "Акция не настроена"
    
    await update.message.reply_text(text)

# ================== ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = get_user_state(context)
    text = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Определяем роль пользователя
    role = get_user_role(user_id, username)
    
    print(f"📨 Сообщение: '{text}', состояние: {state}, роль: {role}")
        # Обработка кнопки "Назад" в режиме баристы (для админа)
    if text == "🔙 Назад" and state == 'barista_mode':
        set_user_state(context, 'admin_settings')
        await show_admin_settings(update)
        return

    # Обработка меню бариста для админа
    if state == 'admin_barista':
        if text == "➕ Добавить":
            set_user_state(context, 'adding_barista')
            await update.message.reply_text("Введите @username баристы для добавления (без @):")
        elif text == "➖ Удалить":
            set_user_state(context, 'removing_barista')
            await update.message.reply_text("Введите @username баристы для удаления (без @):")
        elif text == "📋 Список":
            await show_barista_management(update)
        elif text == "🔙 Назад":
            set_user_state(context, 'main')
            await show_admin_main(update)
        return
    if state == 'main' and role in ['barista', 'admin']:
        if text == "📷 Скан QR":
            set_user_state(context, 'scanning_qr')
            await update.message.reply_text("📸 Отправьте фото QR-кода")
            return
        elif text == "ℹ️ Акции":
            await show_barista_promotion_info(update)
            return
    # Обработка специальных состояний ввода
    if state == 'adding_barista':
        username_input = text.replace('@', '').strip()
        if username_input and username_input not in ['➕ Добавить', '➖ Удалить', '📋 Список', '🔙 Назад']:
            if db.add_barista(username_input, "Бариста", ""):
                await update.message.reply_text(f"✅ Бариста @{username_input} успешно добавлен!")
            else:
                await update.message.reply_text("❌ Ошибка при добавлении баристы")
            set_user_state(context, 'admin_barista')
            await show_barista_management(update)
        else:
            await handle_admin_barista_management(update, context)
        return
    
    elif state == 'removing_barista':
        username_input = text.replace('@', '').strip()
        if username_input and username_input not in ['➕ Добавить', '➖ Удалить', '📋 Список', '🔙 Назад']:
            if db.remove_barista(username_input):
                await update.message.reply_text(f"✅ Бариста @{username_input} успешно удален!")
            else:
                await update.message.reply_text("❌ Бариста не найден")
            set_user_state(context, 'admin_barista')
            await show_barista_management(update)
        else:
            await handle_admin_barista_management(update, context)
        return
    
    elif state == 'finding_customer':
        await handle_customer_search(update, context, text)
        return
    elif state == 'finding_customer_by_username':
        await handle_customer_by_username(update, context)
        return
    elif state == 'changing_promotion_condition':
        try:
            new_condition = int(text)
            if 1 <= new_condition <= 20:
                db.update_promotion(required_purchases=new_condition)
                await update.message.reply_text(f"✅ Условие акции изменено на {new_condition} покупок!")
            else:
                await update.message.reply_text("❌ Число должно быть от 1 до 20")
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число")
        set_user_state(context, 'promotion_management')
        await show_promotion_management(update)
        return
    
    elif state == 'changing_promotion_description':
        if text and text not in ['📝 Название', 'Условие', '📖 Описание', '🔙 Назад']:
            db.update_promotion(description=text)
            await update.message.reply_text("✅ Описание акции успешно обновлено!")
            set_user_state(context, 'promotion_management')
            await show_promotion_management(update)
        else:
            await handle_promotion_management(update, context)
        return
    elif state == 'changing_promotion_name':
        if text and text not in ['📝 Название', 'Условие', '📖 Описание', '🔙 Назад']:
            db.update_promotion(name=text)
            await update.message.reply_text("✅ Название акции обновлено!")
            set_user_state(context, 'promotion_management')
            await show_promotion_management(update)
        else:
            await handle_promotion_management(update, context)
        return
    elif state == 'changing_promotion_condition':
        try:
            new_condition = int(text)
            if 1 <= new_condition <= 20:
                db.update_promotion(required_purchases=new_condition)
                await update.message.reply_text(f"✅ Условие акции изменено на {new_condition} покупок!")
                set_user_state(context, 'promotion_management')
                await show_promotion_management(update)
            else:
                await update.message.reply_text("❌ Число должно быть от 1 до 20")
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число")
        return
    elif state == 'scanning_qr':
        await handle_qr_input(update, context)
        return
    
    elif state == 'barista_action':
        if text == "✅ Засчитать покупку":
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                new_count = db.update_user_purchases(customer_id, 1)
                promotion = db.get_promotion()
                required = promotion[2] if promotion else 7
        
                text = f"""
✅ Покупка засчитана!

Новый счетчик: {new_count}/{required}
{'🎉 Клиент получил бесплатный напиток!' if new_count >= required else f'До бесплатного напитка: {max(0, required - new_count)}'}
        """
                await update.message.reply_text(text)
                                # Уведомляем клиента
                await notify_customer(context.bot, customer_id, new_count, required)
                set_user_state(context, 'main')
            # ВСЕГДА возвращаем в меню баристы после засчитывания покупки
                await show_barista_main(update)
            else:
                await update.message.reply_text("❌ Ошибка: клиент не найден")
    
        elif text == "🔙 Назад":  # ← ДОБАВЛЯЕМ ЭТУ ПРОВЕРКУ
            set_user_state(context, 'main')
            await update.message.reply_text("🔙 Возвращаюсь в меню...")
        # ВСЕГДА возвращаем в меню баристы после отмены сканирования
            await show_barista_main(update)
    
            return
        elif text == "➖ Отменить покупку":
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                new_count = db.update_user_purchases(customer_id, -1)
                promotion = db.get_promotion()
                required = promotion[2] if promotion else 7
            
                text = f"""
➖ Покупка отменена!

Новый счетчик: {new_count}/{required}
{'🎉 Бесплатный напиток доступен!' if new_count >= required else f'До бесплатного напитка: {max(0, required - new_count)}'}
            """
                await update.message.reply_text(text)
                set_user_state(context, 'main')
                if role == 'barista':
                    await show_barista_main(update)
                else:
                    await show_admin_main(update)
            else:
                await update.message.reply_text("❌ Ошибка: клиент не найден")
    
        elif text == "🔙 Назад в меню":
            set_user_state(context, 'main')
            await update.message.reply_text("🔙 Возвращаюсь в меню...")
            if role == 'barista':
                await show_barista_main(update)
            else:
                await show_admin_main(update)
    
        return
    elif state == 'admin_customer_actions':
        print(f"[DEBUG] admin_customer_actions text='{update.message.text}'")
        customer_id = context.user_data.get('current_customer')
        print(f"[DEBUG] current_customer={customer_id}")

        promotion = db.get_promotion()
        required = promotion[2] if promotion else 7

        if text.startswith("➕"):
            print("[DEBUG] нажата кнопка ➕")
            new_count = db.update_user_purchases(customer_id, 1)
            print(f"[DEBUG] новый счётчик = {new_count}")
        elif text.startswith("➖"):
            print("[DEBUG] нажата кнопка ➖")
            new_count = db.update_user_purchases(customer_id, -1)
            print(f"[DEBUG] новый счётчик = {new_count}")
        elif text.startswith("🔙"):
            print("[DEBUG] нажата кнопка 🔙")
            set_user_state(context, 'admin_customers')
            await show_customer_management(update)
            return
        else:
            print(f"[DEBUG] неизвестная кнопка: '{text}'")
            return

        # ⬇⬇⬇ ОБНОВЛЯЕМ карточку и ОСТАЁМСЯ ТУТ же ⬇⬇⬇
        name = f"@{context.user_data.get('current_username') or 'Гость'}"
        msg = f"✅ Обновлено!\n\n👤 {name}\n📊 Новый счётчик: {new_count}/{required}\n🎯 До подарка: {max(0, required - new_count)}"
        if new_count == 0:
            msg += "\n\n🎉 Пользователь получил бесплатный напиток!"

        keyboard = [
            [KeyboardButton("➕ Начислить")],
            [KeyboardButton("➖ Отменить")],
            [KeyboardButton("🔙 Назад")]
        ]
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        # ⬇⬇⬇ НЕ выходим – остаёмся в admin_customer_actions ⬇⬇⬇
        # НЕ вызываем set_user_state и show_customer_management
    # Обработка кнопки "Назад" в разных режимах
    if text == "🔙 Назад":
        if state in ['client_mode', 'barista_mode']:
            set_user_state(context, 'main')
            await show_admin_main(update)
            return
        elif state == 'admin_barista':
            set_user_state(context, 'main')
            await show_admin_main(update)
            return
        elif state == 'admin_customers':
            if text == "Найти пользователя":  # ← ПРОСТОЙ ТЕКСТ
                set_user_state(context, 'finding_customer_by_username')
                await update.message.reply_text("Введите @username пользователя (без @):")
            elif text == "🔍 Найти пользователя":
                set_user_state(context, 'finding_customer_by_username')
                await update.message.reply_text("Введите @username пользователя (без @):")
                return
            elif text == "🔙 Назад":
                set_user_state(context, 'main')
                await show_admin_main(update)
            return
        elif state == 'admin_settings':
            set_user_state(context, 'main')
            await show_admin_main(update)
            return
        
        elif state == 'main' and role == 'admin':
            # Если уже в главном меню админа, просто обновляем
            await show_admin_main(update)
            return
    
    # Основная обработка по ролям и состояниям
    # Основная обработка по ролям и состояниям
    if state == 'main':
        if role == 'admin':
        # ← ДОБАВИТЬ ПРЯМУЮ ОБРАБОТКУ КНОПОК АДМИНА ↓
            if text == "👥 Бариста":
                set_user_state(context, 'admin_barista')
                await show_barista_management(update)
                return
            elif text == "👤 Посетители":
                print("[DEBUG] нажата кнопка Посетители")
                set_user_state(context, 'admin_customers')
                await show_all_customers(update)
                return          # важно, иначе уйдёт дальше
            elif text == "⚙️ Настройки":
                set_user_state(context, 'admin_settings')
                await show_admin_settings(update)
                return
            else:
                await handle_admin_main(update, context)
        elif role == 'barista':
            await handle_barista_mode(update, context)
        else:
            await handle_client_mode(update, context)
    
    elif state == 'client_mode':
        await handle_client_mode(update, context)
    
    elif state == 'barista_mode':
        await handle_barista_mode(update, context)
    
    elif state == 'admin_barista':
        await handle_admin_barista_management(update, context)
    
    elif state == 'admin_customers':
        await handle_admin_customer_management(update, context)
    
    elif state == 'admin_settings':
        await handle_admin_settings(update, context)
    
    elif state == 'promotion_management':
        await handle_promotion_management(update, context)
        return
    elif state == 'finding_customer_by_username':
        await handle_customer_by_username(update, context)
        return
    else:
        set_user_state(context, 'main')
        await start(update, context)

async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создаёт и отправляет админу резервную копию БД"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    try:
        path = db.backup_db()  # создаём копию
        await update.message.reply_document(
            document=open(path, 'rb'),
            caption=f"📦 Резервная копия БД\n📅 {datetime.datetime.now():%d.%m.%Y %H:%M}"
        )
        db.cleanup_old_backups(7)   # оставляем 7 последних копий
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при создании бэкапа:\n{e}")

async def handle_barista_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("DEBUG callback triggered")   # ← должно появиться в консоли
    query = update.callback_query
    await query.answer()

    data = query.data
    print("DEBUG callback data:", data)  # ← увидим, что пришло

    if data.startswith('cancel_'):
        # возвращаем баристу в главное меню
        await show_barista_main(update)
        # редактируем сообщение, чтобы кнопки исчезли
        await query.edit_message_text("🔄 Возвращаюсь в меню баристы...")
async def handle_customer_by_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода @username после нажатия кнопки 'Найти пользователя'"""
    print("[DEBUG] 1. вошли в handle_customer_by_username")
    username_input = update.message.text.strip().lstrip('@').lstrip('‘').lstrip('’').lstrip('"').lstrip("'")
    print(f"[DEBUG] 2. username_input='{username_input}'")

    if not username_input:
        print("[DEBUG] 3. username_input пустой – выходим")
        await update.message.reply_text("❌ Введите корректный @username")
        set_user_state(context, 'admin_customers')
        return

    print("[DEBUG] 4. ищем в БД...")
    user_data = db.get_user_by_username_exact(username_input)
    print(f"[DEBUG] 5. user_data = {user_data}")

    if user_data:
        print("[DEBUG] 6. user_data НЕ ПУСТОЙ – показываем карточку")
        customer_id, username, first_name, last_name = user_data
        purchases = db.get_user_stats(customer_id)
        promotion = db.get_promotion()
        required = promotion[2] if promotion else 7

        user_display_name = f"@{username}" if username else f"{first_name} {last_name}".strip() or "Гость"
        text = f"📋 Найден пользователь:\n\n👤 {user_display_name}\n📊 Покупок: {purchases}/{required}\n🎯 До бесплатного: {max(0, required - purchases)}\n{'🎉 Бесплатный напиток доступен!' if purchases >= required else 'Продолжайте в том же духе!'}"

        keyboard = [
            [KeyboardButton("➕ Начислить покупку")],
            [KeyboardButton("➖ Отменить покупку")],
            [KeyboardButton("🔙 Назад")]
        ]
        print("[DEBUG] 7. отправляю сообщение с клавиатурой")
        await update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

        print("[DEBUG] 8. сохраняю customer_id и переключаю состояние")
        context.user_data['current_customer'] = customer_id
        context.user_data['current_username'] = username or f"{first_name} {last_name}".strip() or "Гость"
        set_user_state(context, 'admin_customer_actions')
        print("[DEBUG] 9. выходим из функции")
        return

    print("[DEBUG] 6. user_data ПУСТОЙ – сообщаем 'не найден'")
    await update.message.reply_text("❌ Пользователь не найден. Попробуйте ещё раз:")
# ================== ЗАПУСК ==================
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("backup", cmd_backup))

    # === ежедневный бэкап (04:00) и чистка (04:01) ===
    import threading, schedule, time
    def daily_job():
        while True:
            schedule.run_pending()
            time.sleep(60)

    schedule.every().day.at("04:00").do(db.backup_db)
    schedule.every().day.at("04:01").do(db.cleanup_old_backups, 7)
    threading.Thread(target=daily_job, daemon=True).start()

    print("🚀 Бот запускается с исправленной архитектурой...")
    application.run_polling()


if __name__ == "__main__":
    main()