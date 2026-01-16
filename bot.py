from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import datetime
from config import BOT_TOKEN, ADMIN_IDS
from database import Database
from qr_manager import generate_qr_code, parse_qr_data, read_qr_from_image
from keyboards import *
import asyncio



import random

def get_random_user_emoji():
    """Возвращает случайный эмодзи для отображения пользователя"""
    user_emojis = [
        "🧘‍♀️", "🤸‍♂️", "🛀", "🤾‍♀️", "🏄‍♂️", "🏂", "⛷", "🧖‍♀️", "🧌", "🕴",
        "🧙‍♂️", "🧛‍♂️", "🎅", "👼", "👨‍🚀", "👩‍🏫", "🧏", "💁‍♂️", "👹", 
        "🙊", "🙉", "🙈"
    ]
    return random.choice(user_emojis)

def get_coffee_progress(current, total, style=None):  # ← ДОБАВЬ style=None
    """Создает визуальный прогресс-бар из случайного набора эмодзи"""
    if total <= 0:
        return "❌ Ошибка акции"
    
    filled = min(current, total)
    
    # Случайный выбор стиля прогресс-бара
    styles = [
        # Стиль 1: ice
        {
            'filled': '🧋', 
            'empty': '🧊', 
            'gift': '🧊'
        },
        # Стиль 2: чёрный кофе
        {
            'filled': '☕', 
            'empty': '🔳', 
            'gift': '🔲'
        },
        # Стиль 3: геометри
        {
            'filled': '☕', 
            'empty': '⚪', 
            'gift': '🟤'
        },
        # Стиль 4: стаканы
        {
            'filled': '🥤', 
            'empty': '⚪', 
            'gift': '🔴'
        },
        # Стиль 5: базовый
        {
            'filled': '☕', 
            'empty': '▫', 
            'gift': '🎁'
        },
                {
            'filled': '🍜', 
            'empty': '◾', 
            'gift': '🈹'
        },
                {
            'filled': '🍪', 
            'empty': '◻', 
            'gift': '🉑'
        },
                {
            'filled': '🟣', 
            'empty': '⚪', 
            'gift': '⬛'
        },
        {
            'filled': '🧋', 
            'empty': '⚪', 
            'gift': '🟠'
        },
    ]
    
    # Выбираем случайный стиль ЕСЛИ не передан
    if style is None:
        style = random.choice(styles)
    
    if filled >= total:
        # Все чашки заполнены - подарок активирован
        return style['filled'] * total
    else:
        empty = total - 1 - filled  # клетки до подарка
        progress = style['filled'] * filled     # Заполненные
        progress += style['empty'] * empty      # Пустые клетки
        progress += style['gift']               # Подарочная клетка
        return progress


async def notify_customer(bot, customer_id, new_count, required):
    # Получаем данные клиента для имени
    cursor = db.conn.cursor()
    cursor.execute('SELECT username, first_name, last_name FROM users WHERE user_id = ?', (customer_id,))
    user_info = cursor.fetchone()
    
    username = user_info[0] if user_info and user_info[0] else "Не указан"
    first_name = user_info[1] if user_info and user_info[1] else ""
    last_name = user_info[2] if user_info and user_info[2] else ""

# ПРИОРИТЕТ: Имя Фамилия > username > Гость
    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = f"@{username}" if username and username != "Не указан" else "Гость"
    # ИСПРАВЛЕНИЕ: Не запрашиваем purchases_count повторно, используем new_count
    # Проверяем, была ли это 6-я покупка (перед подарком)
# Проверяем, была ли это 6-я покупка (перед подарком)
    was_sixth_purchase = (new_count == required - 1)  # 6 покупок при required=7

# Проверяем, была ли это 7-я покупка (подарок)
    was_seventh_purchase = (new_count == 0)  # сброс после 7-й покупки

# Прогресс-бар после начисления
    if was_seventh_purchase:
    # Показываем полный прогресс-бар для 7-й покупки
        progress_bar = get_coffee_progress(required, required)  # 7 из 7
    else:
        progress_bar = get_coffee_progress(new_count, required)
    
    try:
        # ОТПРАВЛЯЕМ СТИКЕР И СООБЩЕНИЕ ОДНОВРЕМЕННО
        sticker_msg = await bot.send_sticker(customer_id, "CAACAgIAAxkBAAIXcmkJz75zJHyaWzadj8tpXsWv8PTsAAKgkwACe69JSNZ_88TxnRpuNgQ")
        
        # Сразу отправляем сообщение с прогресс-баром
        if was_seventh_purchase:
            message = f"{user_display_name}\n\n{progress_bar}            ☑ new    \n\nНапиток в подарок 🎁"
        elif was_sixth_purchase:
            message = f"{user_display_name}\n\n{progress_bar}            ☑ new    \n\nСледующий напиток в подарок"
        else:
            message = f"{user_display_name}\n\n{progress_bar}            ☑ new    "
        
        await bot.send_message(customer_id, message)
        
        # Удаляем стикер через 4 секунды
        async def delete_sticker_later():
            await asyncio.sleep(4)
            try:
                await sticker_msg.delete()
            except Exception:
                pass
        
        asyncio.create_task(delete_sticker_later())
    
    except Exception as e:
        print(f"❌ Не удалось отправить стикер клиенту {customer_id}: {e}")
        if was_seventh_purchase:
            message = f"{user_display_name}\n\n{progress_bar}            ☑ new    \n\nНапиток в подарок 🎁"
        elif was_sixth_purchase:
            message = f"{user_display_name}\n\n{progress_bar}            ☑ new    \n\nСледующий напиток в подарок"
        else:
            message = f"{user_display_name}\n\n{progress_bar}            ☑ new    "
        await bot.send_message(customer_id, message)
        
async def get_sticker_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения ID любого стикера"""
    await update.message.reply_text("Отправьте мне стикер чтобы получить его ID")

# И обработчик для стикеров будет использовать ту же логику
async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для получения ID стикера"""
    sticker = update.message.sticker
    sticker_id = sticker.file_id
    
    await update.message.reply_text(
        f"📦 ID стикера:\n`{sticker_id}`\n\n"
        f"🎭 Эмодзи: {sticker.emoji or 'нет'}\n"
        f"📏 Набор: {sticker.set_name or 'нет'}",
        parse_mode='Markdown'
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
        await show_client_main(update, context)  # ← ДОБАВЬТЕ context здесь
    print(f"🔍 user_id={user_id}, username=@{user.username}")
    print(f"📨 роль={get_user_role(user_id, user.username)}")
# ================== РЕЖИМ КЛИЕНТА ==================
async def show_client_main(update: Update, context: ContextTypes.DEFAULT_TYPE = None):
    user = update.effective_user
    user_id = user.id
    role = get_user_role(user.id, user.username)

    print(f"🔧 show_client_main: role={role}, state={get_user_state(context)}")  # ← ДОБАВЬ ЭТУ СТРОКУ

    text = """
🤎 Добро пожаловать в CoffeeRina (bot)!
    """

    keyboard = get_client_keyboard_with_back() if role == 'admin' else get_client_keyboard()
    
    print(f"🔧 Клавиатура: {keyboard}")  # ← И ЭТУ СТРОКУ

    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    
    # ДОБАВЬТЕ ЭТОТ БЛОК: автоматическая отправка QR-кода клиенту
    if role == 'client' or (role == 'admin' and context and get_user_state(context) == 'client_mode'):
        # Ждем 2 секунды перед отправкой QR-кода
        await asyncio.sleep(1.5)
        await send_qr_code(update, user_id)

async def handle_client_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    print(f"🟡 DEBUG handle_client_mode: text='{text}', user_id={user_id}")
    
    if text == "📱 Мой QR":
        await send_qr_code(update, user_id)
    elif text == "🎁 Акции":
        await show_promotion_info_with_context(update, context)
    elif text == "📞 Привязать номер":
        set_user_state(context, 'setting_phone')
        await update.message.reply_text("🖇 Введите ваш номер телефона (без '8') и имя через пробел\nПример👇\n\n9996664422 Саша")
    elif text == "🔙 Назад" and is_admin(user_id):
        set_user_state(context, 'main')
        await show_admin_main(update)

# ================== РЕЖИМ БАРИСТЫ ==================
async def show_barista_main(update: Update):
    user = update.effective_user
    role = get_user_role(user.id, user.username)
    
    text = "🐾 Привет бариста! Отправь QR или номер"
    
    if role == 'admin':
        if update.message:
            await update.message.reply_text(text, reply_markup=get_barista_keyboard_with_back())
        else:
            await update.callback_query.edit_message_text(text, reply_markup=get_barista_keyboard_with_back())
    else:
        if update.message:
            await update.message.reply_text(text, reply_markup=get_barista_keyboard())
        else:
            await update.callback_query.edit_message_text(text, reply_markup=get_barista_keyboard())


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фотографии с QR-кодом"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    state = get_user_state(context)
    
    role = get_user_role(user_id, username)
    
    if role != 'barista' and not (role == 'admin' and state == 'barista_mode'):
        await update.message.reply_text("❌ Эта функция доступна только баристам")
        return
    
    try:
        processing_msg = await update.message.reply_text("🔍 Обрабатываю QR-код...")
        
        # Сначала получаем фото
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        qr_data = read_qr_from_image(bytes(photo_bytes))
        if not qr_data:
            await processing_msg.edit_text("❌ Не удалось распознать QR-код")
            return
        
        customer_id = parse_qr_data(qr_data)
        if not customer_id:
            await processing_msg.edit_text("❌ Неверный формат QR-кода")
            return
        
        # ТЕПЕРЬ УДАЛЯЕМ ФОТО И СООБЩЕНИЕ ОБ ОБРАБОТКЕ
        await update.message.delete()  # удаляем фото QR-кода
        await processing_msg.delete()  # удаляем сообщение "Обрабатываю..."
        
        # ✅ ДОБАВЛЯЕМ УВЕДОМЛЕНИЕ О НАЙДЕННОМ КЛИЕНТЕ
        await update.message.reply_text("✅ Найден клиент по QR-коду")
        await asyncio.sleep(0.5)
        
        await process_customer_scan(update, context, customer_id)

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обработки: {str(e)}")

async def process_customer_scan(update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: int):
    """Обработка сканирования клиента с автоматическим обновлением клавиатуры"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    state = get_user_state(context)
    role = get_user_role(user_id, username)

    # СОЗДАЕМ НОВЫЕ настройки для каждого клиента
    styles = [
        {'filled': '🧋', 'empty': '🧊', 'gift': '🧊'},
        {'filled': '☕', 'empty': '🔳', 'gift': '🔲'},
        {'filled': '☕', 'empty': '⚪', 'gift': '🟤'},
        {'filled': '🥤', 'empty': '⚪', 'gift': '🔴'},
        {'filled': '☕', 'empty': '▫', 'gift': '🎁'},
        {'filled': '🍜', 'empty': '◾', 'gift': '🈹'},
        {'filled': '🍪', 'empty': '◻', 'gift': '🉑'},
        {'filled': '🟣', 'empty': '⚪', 'gift': '⬛'},
        {'filled': '🧋', 'empty': '⚪', 'gift': '🟠'},
    ]

# ВСЕГДА создаем новые настройки для нового клиента
    context.user_data['customer_style'] = random.choice(styles)
    context.user_data['customer_emoji'] = get_random_user_emoji()

    style = context.user_data['customer_style']
    user_emoji = context.user_data['customer_emoji']
    
    style = context.user_data['customer_style']
    user_emoji = context.user_data['customer_emoji']
    
    # Получаем данные клиента
    purchases = db.get_user_stats(customer_id)
    if purchases is None:
        await update.message.reply_text("❌ Клиент не найден в базе данных.")
        return
    
    cursor = db.conn.cursor()
    cursor.execute('SELECT username, first_name, last_name, phone FROM users WHERE user_id = ?', (customer_id,))
    user_info = cursor.fetchone()
    
    username = user_info[0] if user_info and user_info[0] else "Не указан"
    first_name = user_info[1] if user_info and user_info[1] else ""
    last_name = user_info[2] if user_info and user_info[2] else ""
    phone = user_info[3] if user_info and user_info[3] else "Не указан"
    
    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = f"@{username}" if username and username != "Не указан" else "Гость"
    
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    # Создаем визуальный прогресс-бар
    progress_bar = get_coffee_progress(purchases, required, style)

    # Улучшенная карточка клиента
    if purchases >= required:

        text = f"{user_emoji} {user_display_name}\n📞 {phone}\n\n{progress_bar}\n\n🎉 Бесплатный напиток!"
    else:
        remaining = required - purchases - 1
        
        if remaining == 0:
            status_text = "Следующий 🎁"
        else:
            status_text = f"Ещё {remaining}" 
    
        text = f"""
{user_emoji} {user_display_name}

{progress_bar}

{status_text}
"""
    
    # Сохраняем ID клиента для возможного повторного начисления через ✔ Начислить
    context.user_data['current_customer'] = customer_id
    
    # ✅ АВТОМАТИЧЕСКИ ОБНОВЛЯЕМ КЛАВИАТУРУ
    keyboard = [
        [KeyboardButton("✔ Начислить")],
        [KeyboardButton("📲 Добавить номер")],
        [KeyboardButton("🧾 Инфо")]
    ]
    
    if role == 'admin':
        keyboard.append([KeyboardButton("🔙 Назад")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем сообщение с информацией о клиенте и ОБНОВЛЕННОЙ клавиатурой
    await update.message.reply_text(text, reply_markup=reply_markup)    
    # Бариста теперь может нажать ✔ Начислить для начисления покупки
async def process_coffee_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: int):
    """Обработка начисления покупки по кнопке ✔ Начислить"""
    print(f"🔴 DEBUG process_coffee_purchase: начали, customer_id={customer_id}")
    styles = [
        {'filled': '🧋', 'empty': '🧊', 'gift': '🧊'},
        {'filled': '☕', 'empty': '🔳', 'gift': '🔲'},
        {'filled': '☕', 'empty': '⚪', 'gift': '🟤'},
        {'filled': '🥤', 'empty': '⚪', 'gift': '🔴'},
        {'filled': '☕', 'empty': '▫', 'gift': '🎁'},
        {'filled': '🍜', 'empty': '◾', 'gift': '🈹'},
        {'filled': '🍪', 'empty': '◻', 'gift': '🉑'},
        {'filled': '🟣', 'empty': '⚪', 'gift': '⬛'},
        {'filled': '🧋', 'empty': '⚪', 'gift': '🟠'},
    ]
    
    style = context.user_data.get('customer_style', random.choice(styles))
    user_emoji = context.user_data.get('customer_emoji', get_random_user_emoji())
    user_id = update.effective_user.id
    
    # Получаем текущее количество покупок ДО начисления
    current_purchases = db.get_user_stats(customer_id)
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    print(f"🟡 DEBUG: ДО начисления - current_purchases={current_purchases}, required={required}")

    # Начисляем покупку
    new_count = db.update_user_purchases(customer_id, 1)

    print(f"🟡 DEBUG: ПОСЛЕ начисления - new_count={new_count}")

    # Получаем данные клиента
    cursor = db.conn.cursor()
    cursor.execute('SELECT username, first_name, last_name FROM users WHERE user_id = ?', (customer_id,))
    user_info = cursor.fetchone()

    username = user_info[0] if user_info and user_info[0] else "Не указан"
    first_name = user_info[1] if user_info and user_info[1] else ""
    last_name = user_info[2] if user_info and user_info[2] else ""

# ПРИОРИТЕТ: Имя Фамилия > username > Гость
    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = f"@{username}" if username and username != "Не указан" else "Гость"

    # Надпись показываем когда было 5 покупок (стало 6)
    show_gift_message = (current_purchases == required - 2)  # 5 покупок при required=7
    
    # Анимация подарка когда было 6 покупок (стало 0) - 7-я покупка
    show_gift_animation = (current_purchases == required - 1)  # 6 покупок при required=7
    
    print(f"🟡 DEBUG: show_gift_message={show_gift_message} (current_purchases={current_purchases} == required-2={required-2})")
    print(f"🟡 DEBUG: show_gift_animation={show_gift_animation} (current_purchases={current_purchases} == required-1={required-1})")

    # Прогресс-бар
    progress_bar = get_coffee_progress(new_count, required, style)
    
    # Формируем сообщение для баристы
    # Формируем сообщение для баристы
    if show_gift_message:
        text = f"{user_emoji} {user_display_name}\n\n{progress_bar}            ☑ new    \n\nСледующий напиток в подарок"
    else:
        text = f"{user_emoji} {user_display_name}\n\n{progress_bar}            ☑ new    "
        print(f"🟢 DEBUG: НЕ показываем надпись")

    # Отправляем сообщение баристе
    # СНАЧАЛА стикер на 3 секунды
    sticker_msg = await update.message.reply_sticker("CAACAgIAAxkBAAIXcmkJz75zJHyaWzadj8tpXsWv8PTsAAKgkwACe69JSNZ_88TxnRpuNgQ")

# ПОТОМ сообщение с прогресс-баром
    await update.message.reply_text(text)

# Удаляем стикер через 3 секунды
    async def delete_sticker_later():
        await asyncio.sleep(3)
        try:
            await sticker_msg.delete()
        except Exception:
            pass

    asyncio.create_task(delete_sticker_later())
    
    # Анимация подарка на 7-й покупке (когда счетчик сбрасывается)
    if show_gift_animation:
        print(f"🎁 DEBUG: Показываем анимацию подарка (7-я покупка)")
        gift_msg = await update.message.reply_text("🎁")
        await asyncio.sleep(5)
        try:
            await gift_msg.delete()
        except:
            pass
    
    # Уведомляем клиента
    await notify_customer(context.bot, customer_id, new_count, required)
    
    # ВАЖНО: НЕ меняем состояние! Остаемся в том же режиме баристы
    context.user_data['current_customer'] = customer_id
    
    print(f"🟢 DEBUG process_coffee_purchase: закончили")

async def show_admin_main(update: Update):
    text = """
👑 Панель администратора CoffeeRina
    """
    if update.message:
        await update.message.reply_text(text, reply_markup=get_admin_main_keyboard())
    else:
        await update.callback_query.edit_message_text(text, reply_markup=get_admin_main_keyboard())

async def handle_admin_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📙 Баристы":
        set_user_state(context, 'admin_barista')
        await show_barista_management(update)
    elif text == "📒 Посетители":
        set_user_state(context, 'admin_customers')
        await show_all_customers(update)
    elif text == "📣 Рассылка":  # ← ИЗМЕНИТЕ ЭТОТ БЛОК
        set_user_state(context, 'broadcast_message')
        # НЕ УБИРАЕМ КЛАВИАТУРУ, просто меняем состояние
        await update.message.reply_text(
            "✍ Введите текст для рассылки:\n\n"
            "!c - только клиентам\n"
            "!b - только баристам\n"
            "без префикса - всем пользователям"
        )
    elif text == "⚙️ Опции":
        set_user_state(context, 'admin_settings')
        await show_admin_settings(update)

# ================== РАССЫЛКА ==================
async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текста рассылки"""
    print(f"🎯 DEBUG handle_broadcast_message: text='{update.message.text}', state='{get_user_state(context)}'")
    
    if get_user_state(context) != 'broadcast_message':
        print("❌ DEBUG: Не в состоянии broadcast_message")
        return
    
    text = update.message.text
    print(f"🟢 DEBUG: Обрабатываем текст рассылки: '{text}'")
    
    # ЕСЛИ это кнопка - выходим из состояния рассылки
    if text in ["📙 Баристы", "📒 Посетители", "📣 Рассылка", "⚙️ Опции", "🔙 Назад"]:
        print("🔴 DEBUG: Это кнопка, выходим из рассылки")
        set_user_state(context, 'main')
        await handle_admin_main(update, context)
        return
    
    broadcast_text = text
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Доступ запрещён")
        set_user_state(context, 'main')
        return
    
    # Сохраняем текст для отправки
    context.user_data['broadcast_text'] = broadcast_text
    context.user_data['admin_chat_id'] = user_id
    
    print(f"💾 DEBUG: Сохранили broadcast_text: '{broadcast_text}'")
    
    # ПРЕДПРОСМОТР с инлайн кнопками
# ПРЕДПРОСМОТР с инлайн кнопками
    target_info = ""
    if broadcast_text.startswith('!c '):
        target_info = " (только клиентам)"
    elif broadcast_text.startswith('!b '):
        target_info = " (только баристам)"
    else:
        target_info = " (всем пользователям)"

    preview_text = f"📣 Предпросмотр рассылки{target_info}:\n\n{broadcast_text}"

    keyboard = [
        [
            InlineKeyboardButton("✅ Отправить", callback_data="broadcast_send"),
            InlineKeyboardButton("❌ Отменить", callback_data="broadcast_cancel")
        ]
    ]
    
    print("🔄 DEBUG: Показываем превью...")
    
    try:
        preview_msg = await update.message.reply_text(
            preview_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        print("✅ DEBUG: Превью показано успешно")
    except Exception as e:
        print(f"❌ DEBUG: Ошибка при показе превью: {e}")
        return
    
    context.user_data['preview_msg_id'] = preview_msg.message_id
    set_user_state(context, 'broadcast_preview')
    print("🔄 DEBUG: Перешли в состояние broadcast_preview")


async def handle_broadcast_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка инлайн кнопок рассылки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    if data == "broadcast_send":
        await send_broadcast_to_users(update, context)
    elif data == "broadcast_cancel":
        await query.edit_message_text("❌ Рассылка отменена")
        set_user_state(context, 'main')
        await show_admin_main(update)
    elif data == "broadcast_delete":
        await delete_broadcast_from_users(update, context)

async def send_broadcast_to_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет рассылку пользователям с фильтрацией"""
    query = update.callback_query
    broadcast_text = context.user_data.get('broadcast_text')
    
    if not broadcast_text:
        await query.edit_message_text("❌ Ошибка: текст рассылки не найден")
        return
    
    # Определяем фильтр получателей
    target_audience = "all"  # по умолчанию всем
    
    if broadcast_text.startswith('!b '):
        target_audience = "baristas"
        broadcast_text = broadcast_text[3:].strip()  # Убираем /b
    elif broadcast_text.startswith('!c '):
        target_audience = "clients" 
        broadcast_text = broadcast_text[3:].strip()  # Убираем /c
    
    # Обновляем существующее сообщение
    await query.edit_message_text(
        f"🔄 Отправка рассылки...\n\nЦелевая аудитория: {target_audience}\n\n{broadcast_text}"
    )
    
    # Получаем всех пользователей
    all_user_ids = db.get_all_user_ids()
    sent_count = 0
    failed_count = 0
    sent_messages = []
    
    admin_id = context.user_data.get('admin_chat_id')
    
    for customer_id in all_user_ids:
        if customer_id == admin_id:
            continue
        
        # Определяем роль пользователя
        cursor = db.conn.cursor()
        cursor.execute('SELECT username FROM users WHERE user_id = ?', (customer_id,))
        user_info = cursor.fetchone()
        username = user_info[0] if user_info else None
        user_role = get_user_role(customer_id, username)
        
        # Применяем фильтр
        if target_audience == "baristas" and user_role != "barista":
            continue  # Пропускаем не-барист
        elif target_audience == "clients" and user_role != "client":
            continue  # Пропускаем не-клиентов
        # Если target_audience == "all" - отправляем всем
            
        try:
            sent_msg = await context.bot.send_message(
                chat_id=customer_id,
                text=broadcast_text
            )
            sent_count += 1
            sent_messages.append((customer_id, sent_msg.message_id))
        except Exception as e:
            print(f"❌ Не удалось отправить пользователю {customer_id}: {e}")
            failed_count += 1
        await asyncio.sleep(0.1)
    
    # Сохраняем информацию для удаления
    if sent_messages:
        context.user_data['last_broadcast'] = {
            'messages': sent_messages,
            'text': broadcast_text,
            'target': target_audience
        }
        
        # Показываем результат
        audience_text = {
            "all": "всем пользователям",
            "baristas": "только баристам", 
            "clients": "только клиентам"
        }
        
        result_text = (
            f"✅ Рассылка отправлена!\n"
            f"🎯 Аудитория: {audience_text[target_audience]}\n"
            f"📤 Отправлено: {sent_count}\n\n"
            f"Текст: {broadcast_text}"
        )
        
        keyboard = [[
            InlineKeyboardButton("🗑️ Удалить у всех", callback_data="broadcast_delete")
        ]]
        
        await query.edit_message_text(
            result_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text("❌ Не удалось отправить ни одному пользователю")
    
    set_user_state(context, 'main')
    await show_admin_main(update)


async def delete_broadcast_from_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет рассылку у всех пользователей"""
    query = update.callback_query
    await query.answer()
    
    broadcast_data = context.user_data.get('last_broadcast')
    if not broadcast_data:
        await query.edit_message_text("❌ Нет данных о последней рассылке")
        return
    
    # Обновляем сообщение - показываем "удаление..."
    await query.edit_message_text("🔄 Удаление сообщений у пользователей...")
    
    deleted_count = 0
    for user_id, message_id in broadcast_data['messages']:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=message_id)
            deleted_count += 1
        except Exception as e:
            print(f"❌ Не удалось удалить у {user_id}: {e}")
        await asyncio.sleep(0.1)
    
    await query.edit_message_text(
        f"🗑️ Удалено {deleted_count} сообщений рассылки\n"
        f"Текст: {broadcast_data['text']}"
    )
    
    # Очищаем данные
    context.user_data.pop('last_broadcast', None)
    
async def show_barista_management(update: Update):
    baristas = db.get_all_baristas()
    text = "📜 Список барист:\n\n"

    if baristas:
        for barista in baristas:
            username = barista[0]          # ← только username
            text += f"@{username}\n"
    else:
        text += "Баристы не добавлены"

    text += "\nВыберите действие:"

    await update.message.reply_text(text, reply_markup=get_admin_barista_keyboard())

async def show_customer_management(update: Update):
    text = "📒 Посетители\n\nИспользуйте кнопки ниже для поиска и управления клиентами"
    await update.message.reply_text(text, reply_markup=get_admin_customers_keyboard())

async def show_all_customers(update: Update):
    print('[DEBUG] show_all_customers вызвана')
    users = db.get_all_users()  # ← нужно добавить в database.py
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    if not users:
        text = "📂 Клиентов пока нет."
    else:
        text = "📖 Список пользователей:\n\n"
        for u in users:
            user_id, username, first_name, last_name, purchases, phone = u
            print(f"[DEBUG] user_id={user_id}, username='{username}', first_name='{first_name}', last_name='{last_name}', phone='{phone}'")
            
            # Формируем информацию о пользователе
            user_info_parts = []
            
            # 1. Имя (если есть)
            clean_last_name = last_name if last_name and last_name != "None" else ""
            full_name = f"{first_name or ''} {clean_last_name}".strip()
            if full_name:
                user_info_parts.append(f"{full_name}")
            
            # 2. @username (если есть и не "Не указан")
            if username and username != "Не указан":
                user_info_parts.append(f"@{username}")
            
            # 3. Телефон (если есть)
            if phone:
                user_info_parts.append(f"{phone}")
            
            # 4. ID (для отладки/резерв)
            if not user_info_parts:
                user_info_parts.append(f"ID: {user_id}")
            
            # Объединяем все части
            user_display = " • ".join(user_info_parts)
            
            # Добавляем счетчик покупок
            text += f"{user_display} — {purchases}/{required}\n"
            
    if users:
        # Добавляем инструкцию после списка
        text += "\n\n🔍 Для поиска отправьте:\n• Номер телефона (10 цифр)\n• Последние 4 цифры номера\n• @username пользователя"
    
    await update.message.reply_text(
        text,
        reply_markup=get_admin_customers_keyboard_after_list()
    )

async def show_admin_settings(update: Update):
    promotion = db.get_promotion()
    text = f"""
⚙️ Опции

Выберите раздел:
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
    print(f"DEBUG admin_customers text: '{text}'")
    
    if text == "🔙 Назад":
        set_user_state(context, 'main')
        await show_admin_main(update)
        return
    
    # Если админ в разделе "Пользователи" ввел что-то (не кнопку "Назад")
    # Это может быть: номер (10 цифр), последние 4 цифры, @username, или номер+имя
    await handle_admin_customer_search(update, context, text)

async def handle_admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📝 Изменить акции":
        set_user_state(context, 'promotion_management')
        await show_promotion_management(update)
    elif text == "🤎 Я гость":
        set_user_state(context, 'client_mode')
        await show_client_main(update, context)  # ← ДОБАВЬТЕ context
    elif text == "🐾 Я бариста":
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
# Приоритет: Имя Фамилия > username > Гость
        clean_last_name = last_name if last_name and last_name != "None" else ""
        user_display_name = f"{first_name} {clean_last_name}".strip()
        if not user_display_name:
            user_display_name = f"@{username}" if username else "Гость"
        
        # Создаем прогресс-бар
        # Создаем прогресс-бар
        progress_bar = get_coffee_progress(purchases, required)

        if purchases >= required:
            user_emoji = get_random_user_emoji()
            text = f"""
{user_emoji} {user_display_name}

{progress_bar}

🎉 Бесплатный напиток доступен!
            """
        else:
            remaining = required - purchases - 1
            user_emoji = get_random_user_emoji()
            if remaining == 0:
                status_text = "Следующий 🎁"
            else:
                status_text = f"Ещё {remaining}"
    
            text = f"""
{user_emoji} {user_display_name}

{progress_bar}

{status_text}
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
    
    # 1. Обработка подтверждения удаления (ДОБАВЬ ЭТО ПЕРВЫМ)
    if data.startswith('confirm_delete_'):
        customer_id = int(data.replace('confirm_delete_', ''))
        
        # Удаляем пользователя
        if db.delete_user(customer_id):
            await query.edit_message_text(f"✅ Пользователь удален")
            
            # Возвращаем в меню пользователей
            set_user_state(context, 'admin_customers')
            
            # Удаляем сообщение с кнопками управления (если есть)
            msg_id = context.user_data.get('admin_customer_message_id')
            if msg_id:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=msg_id
                    )
                except:
                    pass
            
            # Показываем меню пользователей
            await show_customer_management(update)
        else:
            await query.edit_message_text(f"❌ Ошибка при удалении пользователя")
        return
    
    elif data.startswith('cancel_delete_'):
        customer_id = int(data.replace('cancel_delete_', ''))
        # Возвращаемся к карточке пользователя
        await show_customer_card_admin(update, context, customer_id)
        return
    
    # 2. Обработка broadcast
    if data.startswith('broadcast_'):
        await handle_broadcast_buttons(update, context)
        return
    
    # 3. Обработка стилей прогресс-бара
    elif data.startswith('style_'):
        # Формат: style_prev_X или style_next_X (X = user_id)
        action, user_id_str = data.split('_')[1], data.split('_')[2]
        user_id = int(user_id_str)
        
        # Получаем текущий индекс стиля (если нет - начинаем с 0)
        style_index = context.user_data.get(f'style_index_{user_id}', 0)
        
        # Список всех стилей (должен совпадать с get_coffee_progress)
        all_styles = [
            {'filled': '🧋', 'empty': '🧊', 'gift': '🧊'},
            {'filled': '☕', 'empty': '🔳', 'gift': '🔲'},
            {'filled': '☕', 'empty': '⚪', 'gift': '🟤'},
            {'filled': '🥤', 'empty': '⚪', 'gift': '🔴'},
            {'filled': '☕', 'empty': '▫', 'gift': '🎁'},
            {'filled': '🍜', 'empty': '◾', 'gift': '🈹'},
            {'filled': '🍪', 'empty': '◻', 'gift': '🉑'},
            {'filled': '🟣', 'empty': '⚪', 'gift': '⬛'},
            {'filled': '🧋', 'empty': '⚪', 'gift': '🟠'},
        ]
        
        # Меняем индекс
        if action == 'prev':
            style_index = (style_index - 1) % len(all_styles)
        elif action == 'next':
            style_index = (style_index + 1) % len(all_styles)
        
        # Сохраняем новый индекс
        context.user_data[f'style_index_{user_id}'] = style_index
        
        # Показываем обновленный прогресс-бар
        await show_progress_with_choice(update, context, user_id)
        return
    
    # 4. Обработка админских действий над пользователем (НОВАЯ СЕКЦИЯ)
    elif data.startswith('admin_'):
        parts = data.split('_')
        if len(parts) < 3:
            return
        
        action = parts[1]
        customer_id = int(parts[2])
        
        if action == 'add':
            # Начислить покупку
            new_count = db.update_user_purchases(customer_id, 1)
            await update_customer_card(update, context, customer_id, new_count)
            
        elif action == 'remove':
            # Отменить покупку
            new_count = db.update_user_purchases(customer_id, -1)
            await update_customer_card(update, context, customer_id, new_count)
            
        elif action == 'delete':
            # Удалить пользователя
            await handle_delete_user(update, context, customer_id)
            
        return
    
    # 5. Обработка начисления/списания покупок (старый код)
    if data.startswith('add_'):
        customer_id = int(data.replace('add_', ''))
        # Логика начисления покупки
        await process_coffee_purchase(update, context, customer_id)
        
    elif data.startswith('remove_'):
        customer_id = int(data.replace('remove_', ''))
        # Логика списания покупки
        new_count = db.update_user_purchases(customer_id, -1)
        await query.edit_message_text(f"✅ Покупка отменена. Новый счетчик: {new_count}")
        
    elif data == 'back_to_customers':
        set_user_state(context, 'admin_customers')
        await show_customer_management(update)
# ================== БАЗОВЫЕ ФУНКЦИИ ==================
async def send_qr_code(update: Update, user_id: int):
    qr_image = generate_qr_code(user_id)
    caption = "📱 Ваш персональный QR-код\n\nПокажите его баристе при заказе"
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
    print(f"🔵 DEBUG show_promotion_info: вызвана")
    user = update.effective_user
    user_id = user.id
    
    # НУЖНО ПОЛУЧИТЬ context
    # В обычном вызове context передается отдельно
    # Так как у нас нет context здесь, создадим фиктивный или изменим вызов
    
    # Отправляем описание акции
    promotion = db.get_promotion()
    if promotion:
        promotion_text = (
            f"🎁 {promotion[1]}\n\n"
            f"{promotion[3] if promotion[3] else 'Покажите QR-код при каждой покупке'}"
        )
    else:
        promotion_text = "Акция ещё не настроена"
    
    # Сохраняем сообщение об акции для удаления
    promotion_msg = await update.message.reply_text(promotion_text)
    
    # Вместо вызова show_progress_with_choice, покажем простой прогресс-бар
    # (потом доработаем, когда разберемся с context)
    purchases = db.get_user_stats(user_id)
    required = promotion[2] if promotion else 7
    
    progress_bar = get_coffee_progress(purchases, required)
    
    # Получаем имя для отображения
    cursor = db.conn.cursor()
    cursor.execute('SELECT first_name, last_name FROM users WHERE user_id = ?', (user_id,))
    user_info = cursor.fetchone()
    
    first_name = user_info[0] if user_info and user_info[0] else ""
    last_name = user_info[1] if user_info and user_info[1] else ""
    
    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = f"@{user.username}" if user.username else "Гость"
    
    # Текст с прогресс-баром
    if purchases >= required:
        text = f"{user_display_name}\n\n{progress_bar}\n\n🎉 Бесплатный напиток доступен!"
    else:
        remaining = required - purchases - 1
        if remaining == 0:
            status_text = "Следующий 🎁"
        else:
            status_text = f"Ещё {remaining}"
        text = f"{user_display_name}\n\n{progress_bar}\n\n{status_text}"
    
    # Показываем без кнопок для начала
    await update.message.reply_text(text)
    
    # Удаляем сообщение об акции через 5 секунд
    async def delete_promotion_message():
        await asyncio.sleep(5)
        try:
            await promotion_msg.delete()
        except Exception:
            pass
    
    asyncio.create_task(delete_promotion_message())

async def show_barista_promotion_info(update: Update):
    print(f"🔴 DEBUG: show_barista_promotion_info вызвана")
    # Только одно сообщение - инструкция
    instruction_text = """
Акция 🎁 7-й напиток в подарок

Начисляем +1 за покупку напитка или десерта
1 чек = 1 '✔ Начислить'

Как найти 🔎

📸 по QR:
- Пользователь показывает QR
- Фотографируете QR и отправляете в этот чат
- Карточка пользователя
- Кнопку '✔ Начислить'

📞 по номеру:
- Посетитель говорит номер
- Отправляете номер в этот чат в формате: 9998887766 Олег
- Карточка посетителя
- Кнопку '✔ Начислить'

Как добавить по номеру 📲

- Кнопку '📲 Добавить номер'
- Отправь в чат НОМЕР ИМЯ как тут: 9996664422 Саша
- Гость добавлен, карточка посетителя
- Кнопку '✔ Начислить'

Перезапуск бота - команда /start
    """
    
    # Отправляем только одно сообщение с инструкцией
    await update.message.reply_text(instruction_text)
    print(f"🟢 DEBUG: сообщение отправлено")

async def show_progress_with_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Показывает прогресс-бар с кнопками выбора стиля"""
    # Получаем данные пользователя
    purchases = db.get_user_stats(user_id)
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7
    
    # Получаем выбранный стиль
    all_styles = [
        {'filled': '🧋', 'empty': '🧊', 'gift': '🧊'},
        {'filled': '☕', 'empty': '🔳', 'gift': '🔲'},
        {'filled': '☕', 'empty': '⚪', 'gift': '🟤'},
        {'filled': '🥤', 'empty': '⚪', 'gift': '🔴'},
        {'filled': '☕', 'empty': '▫', 'gift': '🎁'},
        {'filled': '🍜', 'empty': '◾', 'gift': '🈹'},
        {'filled': '🍪', 'empty': '◻', 'gift': '🉑'},
        {'filled': '🟣', 'empty': '⚪', 'gift': '⬛'},
        {'filled': '🧋', 'empty': '⚪', 'gift': '🟠'},
    ]
    
    style_index = context.user_data.get(f'style_index_{user_id}', 0)
    style = all_styles[style_index]
    
    # Создаем прогресс-бар с ВЫБРАННЫМ стилем
    progress_bar = get_coffee_progress(purchases, required, style)
    
    # Получаем имя для отображения
    cursor = db.conn.cursor()
    cursor.execute('SELECT first_name, last_name FROM users WHERE user_id = ?', (user_id,))
    user_info = cursor.fetchone()
    
    first_name = user_info[0] if user_info and user_info[0] else ""
    last_name = user_info[1] if user_info and user_info[1] else ""
    
    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = f"@{update.effective_user.username}" if update.effective_user.username else "Гость"
    
    # Текст с прогресс-баром
    if purchases >= required:
        text = f"{user_display_name}\n\n{progress_bar}\n\n🎉 Бесплатный напиток доступен!"
    else:
        remaining = required - purchases - 1
        if remaining == 0:
            status_text = "Следующий 🎁"
        else:
            status_text = f"Ещё {remaining}"
        text = f"{user_display_name}\n\n{progress_bar}\n\n{status_text}"
    
    # Инлайн-кнопки для переключения стилей
    keyboard = [
        [
            InlineKeyboardButton("←", callback_data=f"style_prev_{user_id}"),
            InlineKeyboardButton(f"Стиль {style_index + 1}/{len(all_styles)}", callback_data="noop"),
            InlineKeyboardButton("→", callback_data=f"style_next_{user_id}")
        ]
    ]
    
    # Редактируем существующее сообщение или отправляем новое
    try:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except:
        # Если это новый вызов (не callback)
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_promotion_info_with_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает акцию и прогресс-бар с выбором стиля (с context)"""
    print(f"🔵 DEBUG show_promotion_info_with_context: вызвана")
    user = update.effective_user
    user_id = user.id
    
    # Отправляем описание акции
    promotion = db.get_promotion()
    if promotion:
        promotion_text = (
            f"🎁 {promotion[1]}\n\n"
            f"{promotion[3] if promotion[3] else 'Покажите QR-код при каждой покупке'}"
        )
    else:
        promotion_text = "Акция ещё не настроена"
    
    promotion_msg = await update.message.reply_text(promotion_text)
    
    # Ждем 2 секунды
    await asyncio.sleep(2)
    
    # Теперь можно вызвать функцию с кнопками
    await show_progress_with_choice(update, context, user_id)
    
    # Удаляем сообщение об акции через 5 секунд
    async def delete_promotion_message():
        await asyncio.sleep(5)
        try:
            await promotion_msg.delete()
        except Exception:
            pass
    
    asyncio.create_task(delete_promotion_message())
# ================== ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = get_user_state(context)
    text = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username
        
    role = get_user_role(user_id, username)
    print(f"🔴 DEBUG ВХОД: text='{text}', state='{state}', role='{role}'")

    # ✅ ПЕРЕМЕСТИ ЭТУ ПРОВЕРКУ СЮДА - САМОЕ ПЕРВОЕ!
    if state == 'broadcast_message':
        print(f"🟢 DEBUG: Передаем в handle_broadcast_message: '{text}'")
        await handle_broadcast_message(update, context)
        return

    # ✅ ДОБАВЬ ЭТОТ БЛОК ДЛЯ ОБЫЧНЫХ БАРИСТ В СОСТОЯНИИ MAIN
# ✅ ДОБАВЬ ЭТОТ БЛОК ДЛЯ ОБЫЧНЫХ БАРИСТ В СОСТОЯНИИ MAIN
    if role == 'barista' and state == 'main':
        if text == "📲 Добавить номер":
            set_user_state(context, 'adding_customer')
            await update.message.reply_text("💬 Для добавления отправь\nНОМЕР ИМЯ\nв формате как это:\n\n9996664422 Саша")
            return
        elif text == "✔ Начислить":
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                await process_coffee_purchase(update, context, customer_id)
            else:
                await update.message.reply_text("❌ Сначала найдите клиента по QR или номеру")
            return
        elif text == "🧾 Инфо":
            await show_barista_promotion_info(update)
            return

        # ⭐⭐⭐ ДОБАВЛЯЕМ ПОИСК ПО НОМЕРУ ДЛЯ ОБЫЧНЫХ БАРИСТ ⭐⭐⭐
        # Поиск по 4 цифрам
        elif text.isdigit() and len(text) == 4:
            results = db.find_user_by_phone_last4(text)

            if results is None:
                await update.message.reply_text(f"❌ {text} не найден")
            elif isinstance(results, list) and len(results) > 1:
                # Множественные совпадения
                context.user_data['multiple_customers'] = results
                context.user_data['search_last4'] = text

                keyboard = []
                for customer_id in results:
                    cursor = db.conn.cursor()
                    cursor.execute('SELECT first_name, last_name, phone FROM users WHERE user_id = ?', (customer_id,))
                    user_info = cursor.fetchone()

                    if user_info:
                        first_name, last_name, phone = user_info
                        name = f"{first_name or ''} {last_name or ''}".strip() or f"Клиент {customer_id}"
                        display_phone = phone[-4:] if phone else "???"
                        keyboard.append([KeyboardButton(f"📞 {name} ({display_phone})")])

                keyboard.append([KeyboardButton("🔙 Отменить")])

                await update.message.reply_text(
                    f"🔍 Найдено {len(results)} клиента с окончанием **{text}**:\nВыберите нужного:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
                set_user_state(context, 'selecting_customer')
                return
            else:
                # Одно совпадение
                customer_id = results if not isinstance(results, list) else results[0]
                await update.message.reply_text("✅ Найден клиент")
                await asyncio.sleep(0.5)
                await process_customer_scan(update, context, customer_id)
            return

        # Поиск по 10 цифрам
        elif text.isdigit() and len(text) == 10:
            customer_id = db.find_user_by_phone(text)
            if customer_id:
                await update.message.reply_text("✅ Найден клиент по номеру")
                await asyncio.sleep(0.5)
                await process_customer_scan(update, context, customer_id)
            else:
                await update.message.reply_text(f"❌ Клиент с номером {text} не найден\n\nИспользуйте формат: 9996664422 Саша")
            return

        # Поиск по номеру и имени
        elif " " in text:
            try:
                # Разделяем по первому пробелу: номер имя
                parts = text.split(" ", 1)
                phone = parts[0].strip()
                name = parts[1].strip()

                if phone.isdigit() and len(phone) == 10:
                    customer_id = db.find_user_by_phone(phone)

                    if customer_id:
                        await update.message.reply_text("✅ Найден клиент")
                        await asyncio.sleep(0.5)
                        await process_customer_scan(update, context, customer_id)
                    else:
                        import random
                        new_customer_id = random.randint(1000000000, 9999999999)

                        db.get_or_create_user(new_customer_id, "", name, "")
                        db.update_user_phone(new_customer_id, phone)

                        await update.message.reply_text(f"✅ Создан новый клиент: {name} ({phone})")
                        await asyncio.sleep(0.5)
                        await process_customer_scan(update, context, new_customer_id)

                    return
                else:
                    await update.message.reply_text("❌ Номер должен быть 10 цифр")

            except (ValueError, IndexError):
                await update.message.reply_text("❌ Формат: номер имя\nПример: 9996664422 Саша")
            return

        # Если обычный бариста в main состоянии нажал другую кнопку - показываем меню баристы
        elif text in ["📲 Добавить номер", "✔ Начислить", "🧾 Инфо"]:
            # Эти кнопки уже обработаны выше
            pass
        else:
            # Показываем меню баристы для обычных барист в состоянии main
            await show_barista_main(update)
            return

    elif state == 'selecting_customer':
        if text.startswith("📞 "):
            # Извлекаем customer_id из кнопки
            customer_id = None
            results = context.user_data.get('multiple_customers', [])
            
            for cid in results:
                cursor = db.conn.cursor()
                cursor.execute('SELECT first_name, last_name, phone FROM users WHERE user_id = ?', (cid,))
                user_info = cursor.fetchone()
                
                if user_info:
                    first_name, last_name, phone = user_info
                    name = f"{first_name or ''} {last_name or ''}".strip() or f"Клиент {cid}"
                    display_phone = phone[-4:] if phone else "???"
                    
                    if f"📞 {name} ({display_phone})" == text:
                        customer_id = cid
                        break
            
            if customer_id:
                await process_customer_scan(update, context, customer_id)
                # Очищаем временные данные
                context.user_data.pop('multiple_customers', None)
                context.user_data.pop('search_last4', None)
            else:
                await update.message.reply_text("❌ Ошибка выбора клиента")
        
        elif text == "🔙 Отменить":
            set_user_state(context, 'barista_mode')
            await show_barista_main(update)
        
        return
    
    elif state == 'selecting_customer_admin':
        if text.startswith("📞 "):
            # Извлекаем customer_id из кнопки
            customer_id = None
            results = context.user_data.get('multiple_customers', [])
            
            for cid in results:
                cursor = db.conn.cursor()
                cursor.execute('SELECT first_name, last_name, phone FROM users WHERE user_id = ?', (cid,))
                user_info = cursor.fetchone()
                
                if user_info:
                    first_name, last_name, phone = user_info
                    name = f"{first_name or ''} {last_name or ''}".strip() or f"Клиент {cid}"
                    display_phone = phone[-4:] if phone else "???"
                    
                    if f"📞 {name} ({display_phone})" == text:
                        customer_id = cid
                        break
            
            if customer_id:
                await show_customer_card_admin(update, context, customer_id)
                # Очищаем временные данные
                context.user_data.pop('multiple_customers', None)
                context.user_data.pop('search_last4', None)
            else:
                await update.message.reply_text("❌ Ошибка выбора клиента")
        
        elif text == "🔙 Отменить":
            set_user_state(context, 'admin_customers')
            await update.message.reply_text(
                "📒 Раздел пользователей\n\n"
                "Отправьте:\n"
                "• Номер телефона (10 цифр)\n"
                "• Последние 4 цифры номера\n"
                "• @username пользователя\n\n"
                "Или нажмите 🔙 Назад",
                reply_markup=get_admin_customers_keyboard()
            )
        
        return
    
    if text == "🔙 Назад" and state == 'barista_mode':
        set_user_state(context, 'admin_settings')
        await show_admin_settings(update)
        return  

    if text == "📲 Добавить номер" and state == 'barista_mode':
        set_user_state(context, 'adding_customer')
        await update.message.reply_text("💬 Для добавления отправь\nНОМЕР ИМЯ\nв формате как это:\n\n9996664422 Саша")
        return
    
    print(f"📨 Сообщение: '{text}', состояние: {state}, роль: {role}")

    if state == 'adding_customer':
        # Обрабатываем ввод номера и имени после нажатия кнопки "📲 Добавить номер"
        
        # ПРОВЕРЯЕМ СПЕЦИАЛЬНЫЕ КОМАНДЫ ПЕРВЫМИ
        if text == "🔙 Назад":
            set_user_state(context, 'barista_mode')
            await show_barista_main(update)
            return
        elif text == "✔ Начислить":
            set_user_state(context, 'barista_mode')
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                await process_coffee_purchase(update, context, customer_id)
            else:
                await update.message.reply_text("❌ Сначала найдите клиента по QR или номеру")
            return
        elif text == "🧾 Инфо":
            set_user_state(context, 'barista_mode')
            await show_barista_promotion_info(update)  # ← УБРАЛ await show_barista_main(update)
            return
        elif text == "📲 Добавить номер":
            # Игнорируем повторное нажатие той же кнопки
            return
        
        # ... остальной код без изменений
        
        # Только потом проверяем ввод номера
        if " " in text:
            try:
                parts = text.split(" ", 1)
                phone = parts[0].strip()
                name = parts[1].strip()
                
                if phone.isdigit() and len(phone) == 10:
                    customer_id = db.find_user_by_phone(phone)
                    
                    if customer_id:
                        await update.message.reply_text("✅ Найден клиент")
                        await asyncio.sleep(0.5)
                        await process_customer_scan(update, context, customer_id)
                    else:
                        import random
                        new_customer_id = random.randint(1000000000, 9999999999)
                        
                        db.get_or_create_user(new_customer_id, "", name, "")
                        db.update_user_phone(new_customer_id, phone)
                        
                        await update.message.reply_text(f"✅ Создан новый клиент: {name} ({phone})")
                        await asyncio.sleep(0.5)
                        await process_customer_scan(update, context, new_customer_id)
                    
                    # Возвращаем в режим баристы
                    set_user_state(context, 'barista_mode')
                    
                else:
                    await update.message.reply_text("❌ Номер должен быть 10 цифр")
                    
            except (ValueError, IndexError):
                await update.message.reply_text("❌ Формат: номер имя\nПример: 9996664422 Саша")
        else:
            await update.message.reply_text("❌ Введите номер и имя через пробел\nПример: 9996664422 Саша\n\nИли нажмите '🔙 Назад' для отмены")
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
    
    elif state == 'broadcast_message':
    
        print(f"🟢 DEBUG: Передаем в handle_broadcast_message: '{text}'")
        await handle_broadcast_message(update, context)
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
    
    
    elif state == 'barista_mode':
        if text.isdigit() and len(text) == 4:
            results = db.find_user_by_phone_last4(text)

            if results is None:
                await update.message.reply_text(f"❌ {text} не найден")
            elif isinstance(results, list) and len(results) > 1:
                # Множественные совпадения
                context.user_data['multiple_customers'] = results
                context.user_data['search_last4'] = text

                keyboard = []
                for customer_id in results:
                    cursor = db.conn.cursor()
                    cursor.execute('SELECT first_name, last_name, phone FROM users WHERE user_id = ?', (customer_id,))
                    user_info = cursor.fetchone()

                    if user_info:
                        first_name, last_name, phone = user_info
                        name = f"{first_name or ''} {last_name or ''}".strip() or f"Клиент {customer_id}"
                        display_phone = phone[-4:] if phone else "???"
                        keyboard.append([KeyboardButton(f"📞 {name} ({display_phone})")])

                keyboard.append([KeyboardButton("🔙 Отменить")])

                await update.message.reply_text(
                    f"🔍 Найдено {len(results)} клиента с окончанием **{text}**:\nВыберите нужного:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
                set_user_state(context, 'selecting_customer')
                return
            else:
                # Одно совпадение
                customer_id = results if not isinstance(results, list) else results[0]
                await update.message.reply_text("✅ Найден клиент")
                await asyncio.sleep(0.5)
                await process_customer_scan(update, context, customer_id)
            return

        if text == "🧾 Инфо":
            await show_barista_promotion_info(update)
            return
        elif text == "✔ Начислить":
            print(f"🟡 DEBUG: Обрабатываем +1, текущее состояние: {state}")
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                await process_coffee_purchase(update, context, customer_id)
            else:
                await update.message.reply_text("❌ Сначала найдите клиента по QR или номеру")
            return
        elif text == "📲 Добавить номер":  # ← ДОБАВЬ ЭТУ СТРОКУ
            set_user_state(context, 'adding_customer')
            await update.message.reply_text("💬 Для добавления отправь\nНОМЕР ИМЯ\nв формате как это:\n\n9996664422 Саша")
            return
        elif " " in text:
            try:
                # Разделяем по первому пробелу: номер имя
                parts = text.split(" ", 1)
                phone = parts[0].strip()
                name = parts[1].strip()
                
                if phone.isdigit() and len(phone) == 10:
                    customer_id = db.find_user_by_phone(phone)
                    
                    if customer_id:
                        await update.message.reply_text("✅ Найден клиент")
                        await asyncio.sleep(0.5)
                        await process_customer_scan(update, context, customer_id)
                    else:
                        import random
                        new_customer_id = random.randint(1000000000, 9999999999)
                        
                        db.get_or_create_user(new_customer_id, "", name, "")
                        db.update_user_phone(new_customer_id, phone)
                        
                        await update.message.reply_text(f"✅ Создан новый клиент: {name} ({phone})")
                        await asyncio.sleep(0.5)
                        await process_customer_scan(update, context, new_customer_id)
                    
                    # ВОЗВРАЩАЕМ В РЕЖИМ БАРИСТЫ ПОСЛЕ ОБРАБОТКИ
                    set_user_state(context, 'barista_mode')
                    
                else:
                    await update.message.reply_text("❌ Номер должен быть 10 цифр")
                    
            except (ValueError, IndexError):
                await update.message.reply_text("❌ Формат: номер имя\nПример: 9996664422 Саша")


        elif text.isdigit() and len(text) == 10:
            customer_id = db.find_user_by_phone(text)
            if customer_id:
                await update.message.reply_text("✅ Найден клиент по номеру")
                await asyncio.sleep(0.5)
                await process_customer_scan(update, context, customer_id)
            else:
                await update.message.reply_text(f"❌ Клиент с номером {text} не найден\n\nИспользуйте формат: 9996664422 Саша")
        else:
            await update.message.reply_text("📸 Отправьте фото QR или введите номер имя\nПример: 9996664422 Саша")

    elif state == 'barista_action':
        if text == "✔ Засчитать покупку":
            # УБРАТЬ УДАЛЕНИЕ: await update.message.delete() - УДАЛИТЕ ЭТУ СТРОКУ
    
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                new_count = db.update_user_purchases(customer_id, 1)
                promotion = db.get_promotion()
                required = promotion[2] if promotion else 7

                # ДОБАВИТЬ: получаем имя клиента
                cursor = db.conn.cursor()
                cursor.execute('SELECT username, first_name, last_name FROM users WHERE user_id = ?', (customer_id,))
                user_info = cursor.fetchone()
            
                username = user_info[0] if user_info and user_info[0] else "Не указан"
                first_name = user_info[1] if user_info and user_info[1] else ""
                last_name = user_info[2] if user_info and user_info[2] else ""
            
                user_display_name = f"@{username}" if username != "Не указан" else f"{first_name} {last_name}".strip()
                if not user_display_name:
                    user_display_name = "Гость"

                progress_bar = get_coffee_progress(new_count, required)
                if new_count >= required:
                    text = f"{user_display_name}\t\t☑️ + 1\n\n{progress_bar}\n\n🎉 Бесплатный напиток активирован!"
                else:
                    # ИСПРАВЛЕНИЕ: правильный расчет до бесплатного напитка
                    remaining_for_free = max(0, required - new_count - 1)
                    text = f"{user_display_name}\t\t☑️ + 1\n\n{progress_bar}\n\nДо бесплатного напитка: {remaining_for_free}"
            
                # ЗАМЕНИТЬ СООБЩЕНИЕ вместо создания нового
                customer_card_message_id = context.user_data.get('customer_card_message_id')
                if customer_card_message_id:
                    try:
                        # УДАЛИТЬ первое сообщение (карточку клиента)
                        await context.bot.delete_message(
                            chat_id=update.effective_chat.id,
                            message_id=customer_card_message_id
                        )
                    except Exception:
                        pass  # Игнорируем ошибки удаления

                # СОЗДАЕМ ТУ ЖЕ КЛАВИАТУРУ для обновленного сообщения
                keyboard = [
                    [KeyboardButton("✔ Засчитать покупку")],
                    [KeyboardButton("🔙 Назад")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
                # ОТПРАВИТЬ новое сообщение с ТОЙ ЖЕ КЛАВИАТУРОЙ
                new_message = await update.message.reply_text(text, reply_markup=reply_markup)
                context.user_data['customer_card_message_id'] = new_message.message_id
            
                # Уведомляем клиента
                await notify_customer(context.bot, customer_id, new_count, required)
    
                # ⚠️ УБРАЛИ возврат в меню баристы - остаемся в barista_action
                # Теперь можно начислить еще или отправить новый QR
                return
            else:
                await update.message.reply_text("❌ Ошибка: клиент не найден")

        elif text == "➖ Отменить покупку":
            # Удаляем сообщение с кнопкой "➖ Отменить покупку"
            await update.message.delete()
        
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                new_count = db.update_user_purchases(customer_id, -1)
                promotion = db.get_promotion()
                required = promotion[2] if promotion else 7
    
                # ДОБАВЬТЕ ВИЗУАЛЬНЫЙ ПРОГРЕСС И ЗДЕСЬ
                progress_bar = get_coffee_progress(new_count, required)
                if new_count >= required:
                    text = f"➖ Покупка отменена!\n\n{progress_bar}\n🎉 Бесплатный напиток доступен!"
                else:
                    text = f"➖ Покупка отменена!\n\n{progress_bar}\nДо бесплатного напитка: {max(0, required - new_count)}"
        
                await update.message.reply_text(text)
                if role == 'barista':
                    set_user_state(context, 'main')
                    await show_barista_main(update)
                else:
                    set_user_state(context, 'barista_mode')
                    await show_barista_main(update)
                return
            else:
                await update.message.reply_text("❌ Ошибка: клиент не найден")
                
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
        if state == 'barista_mode':  # ← ДОБАВЬТЕ ЭТУ СТРОКУ ПЕРВОЙ
            set_user_state(context, 'admin_settings')
            await show_admin_settings(update)
            return
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
        if role == 'admin' and state != 'barista_mode':
        # ← ДОЛЖНЫ БЫТЬ ВСЕ ЭТИ КНОПКИ:
            if text == "📙 Баристы":
                set_user_state(context, 'admin_barista')
                await show_barista_management(update)
                return
            elif text == "📒 Посетители":
                print("[DEBUG] нажата кнопка Посетители")
                set_user_state(context, 'admin_customers')
                await show_all_customers(update)
                return
            elif text == "📣 Рассылка":
                print(f"🟡 DEBUG: Устанавливаем состояние broadcast_message")
                set_user_state(context, 'broadcast_message')
                await update.message.reply_text(
                    "✍ Введите текст для рассылки:\n\n"
                    "!c только клиентам\n"
                    "!b только баристам\n"
                    "без префикса - всем пользователям\n\n"
                )
                return
            elif text == "⚙️ Опции":
                set_user_state(context, 'admin_settings')
                await show_admin_settings(update)
                return
            else:
                await handle_admin_main(update, context)

        elif role == 'client':  # ← ДОБАВЬ ЭТОТ БЛОК
            if text == "📱 Мой QR":
                await send_qr_code(update, user_id)
                return
            elif text == "🎁 Акции":
                await show_promotion_info_with_context(update, context)
                return
            elif text == "📞 Привязать номер":
                set_user_state(context, 'setting_phone')
                await update.message.reply_text("🖇 Введите ваш номер телефона (без '8') и имя через пробел\nПример👇\n\n9996664422 Саша")
                return
    
    elif state == 'client_mode':
        await handle_client_mode(update, context)

    elif state == 'setting_phone':
        # ПРОВЕРЯЕМ СПЕЦИАЛЬНЫЕ КОМАНДЫ ПЕРВЫМИ
        if text == "🔙 Назад":
            set_user_state(context, 'client_mode')
            await show_client_main(update, context)
            return
        elif text == "📱 Мой QR":
            set_user_state(context, 'client_mode')
            await send_qr_code(update, user_id)
            return
        elif text == "🎁 Акции":
            set_user_state(context, 'client_mode')
            await show_promotion_info_with_context(update, context)
            return
        
        # Только потом проверяем ввод номера
        if " " in text:
            try:
                parts = text.split(" ", 1)
                phone = parts[0].strip()
                name = parts[1].strip()
            
                if phone.isdigit() and len(phone) == 10:
                    user_id = update.effective_user.id
                
                    # Обновляем имя и номер
                    cursor = db.conn.cursor()
                    cursor.execute('UPDATE users SET first_name = ?, phone = ? WHERE user_id = ?', (name, phone, user_id))
                    db.conn.commit()
                
                    await update.message.reply_text(f"✅ Ваш профиль обновлен: {name} ({phone}) теперь вы можете баристе называть номер при заказе")
                    set_user_state(context, 'client_mode')
                    await show_client_main(update, context)
                else:
                    await update.message.reply_text("❌ Номер должен быть 10 цифр")
                
            except (ValueError, IndexError):
                await update.message.reply_text("❌ Формат: номер имя\nПример: 9996664422 Саша")
        else:
            await update.message.reply_text("❌ Введите номер и имя через пробел\nПример: 9996664422 Саша\n\nИли нажмите '🔙 Назад' для отмены")


    elif state == 'admin_barista':
        await handle_admin_barista_management(update, context)
    
    elif state == 'admin_customers':
        await handle_admin_customer_management(update, context)
    
    elif state == 'admin_settings':
        if text == "📝 Изменить акции":
            set_user_state(context, 'promotion_management')
            await show_promotion_management(update)
        elif text == "🤎 Я гость":
            set_user_state(context, 'client_mode')
            await show_client_main(update, context)
        elif text == "🐾 Я бариста":
            set_user_state(context, 'barista_mode')
            await show_barista_main(update)
        elif text == "🔙 Назад":
            set_user_state(context, 'main')
            await show_admin_main(update)
        else:
            # Если нажата неизвестная кнопка, показываем меню настроек снова
            await show_admin_settings(update)
        return
    
    elif state == 'promotion_management':
        await handle_promotion_management(update, context)
        return
    elif state == 'finding_customer_by_username':
        await handle_customer_by_username(update, context)
        return
    else:
        # Если неизвестная команда, просто игнорируем или показываем текущее меню
        print(f"⚠️ DEBUG: Неизвестная команда '{text}', состояние: {state}")
        
        # Обрабатываем кнопки которые попали сюда
        if text == "✔ Начислить" and state == 'barista_mode':
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                await process_coffee_purchase(update, context, customer_id)
            else:
                await update.message.reply_text("❌ Сначала найдите клиента по QR или номеру")
        elif text == "🧾 Инфо" and state == 'barista_mode':
            await show_barista_promotion_info(update)
            return
        elif text == "📲 Добавить номер" and (state == 'barista_mode' or (state == 'main' and role == 'barista')):  # ← ИЗМЕНИ ЭТУ СТРОКУ
            set_user_state(context, 'adding_customer')
            await update.message.reply_text("💬 Для добавления отправь\nНОМЕР ИМЯ\nв формате как это:\n\n9996664422 Саша")
        # Вместо перезапуска показываем текущее меню
        elif state == 'barista_mode':
            await show_barista_main(update)
        elif state == 'client_mode':
            await show_client_main(update, context)
        elif state == 'main' and role == 'admin':
            await show_admin_main(update)
        elif state == 'main' and role == 'barista':  # ← ДОБАВЬ ЭТУ СТРОКУ
            await show_barista_main(update)

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

        # Приоритет: Имя Фамилия > username > Гость
        # Обрабатываем случай когда last_name = "None" (строка)
        clean_last_name = last_name if last_name and last_name != "None" else ""
        user_display_name = f"{first_name} {clean_last_name}".strip()
        if not user_display_name:
            user_display_name = f"@{username}" if username else "Гость"

        # Создаем прогресс-бар
        progress_bar = get_coffee_progress(purchases, required)

        if purchases >= required:
            user_emoji = get_random_user_emoji()
            text = f"""
{user_emoji} {user_display_name}

{progress_bar}

🎉 Бесплатный напиток доступен!
"""
        else:
            remaining = required - purchases - 1
            user_emoji = get_random_user_emoji()
            if remaining == 0:
                status_text = "Следующий 🎁"
            else:
                status_text = f"Ещё {remaining}"
    
            text = f"""
{user_emoji} {user_display_name}

{progress_bar}

{status_text}
"""

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
    await update.message.reply_text("❌ Пользователь не найден.")

async def handle_admin_customer_search(update: Update, context: ContextTypes.DEFAULT_TYPE, search_query: str):
    """Поиск пользователя администратором по номеру или @username"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # 1. Поиск по 4 последним цифрам номера
    if search_query.isdigit() and len(search_query) == 4:
        results = db.find_user_by_phone_last4(search_query)
        
        if results is None:
            await update.message.reply_text(f"❌ Клиент с окончанием {search_query} не найден")
        elif isinstance(results, list) and len(results) > 1:
            # Множественные совпадения
            context.user_data['multiple_customers'] = results
            context.user_data['search_last4'] = search_query
            
            keyboard = []
            for customer_id in results:
                cursor = db.conn.cursor()
                cursor.execute('SELECT first_name, last_name, phone FROM users WHERE user_id = ?', (customer_id,))
                user_info = cursor.fetchone()
                
                if user_info:
                    first_name, last_name, phone = user_info
                    name = f"{first_name or ''} {last_name or ''}".strip() or f"Клиент {customer_id}"
                    display_phone = phone[-4:] if phone else "???"
                    keyboard.append([KeyboardButton(f"📞 {name} ({display_phone})")])
            
            keyboard.append([KeyboardButton("🔙 Отменить")])
            
            await update.message.reply_text(
                f"🔍 Найдено {len(results)} клиента с окончанием **{search_query}**:\nВыберите нужного:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            set_user_state(context, 'selecting_customer_admin')
            return
        else:
            # Одно совпадение
            customer_id = results if not isinstance(results, list) else results[0]
            await show_customer_card_admin(update, context, customer_id)
        return
    
    # 2. Поиск по полному номеру (10 цифр)
    elif search_query.isdigit() and len(search_query) == 10:
        customer_id = db.find_user_by_phone(search_query)
        if customer_id:
            await show_customer_card_admin(update, context, customer_id)
        else:
            await update.message.reply_text(f"❌ Клиент с номером {search_query} не найден")
        return
    
    # 3. Поиск по @username (убираем @ если есть)
    elif search_query.startswith('@'):
        username_input = search_query[1:].strip()
        user_data = db.get_user_by_username_exact(username_input)
        
        if user_data:
            customer_id = user_data[0]
            await show_customer_card_admin(update, context, customer_id)
        else:
            await update.message.reply_text(f"❌ Пользователь @{username_input} не найден")
        return
    
    # 4. Поиск по username без @
    else:
        # Пробуем найти по username без @
        user_data = db.get_user_by_username_exact(search_query)
        if user_data:
            customer_id = user_data[0]
            await show_customer_card_admin(update, context, customer_id)
            return
    
    # 5. Если ничего не нашли
    await update.message.reply_text(
        "❌ Пользователь не найден. Ищите по:\n"
        "• Номеру телефона (10 цифр)\n"
        "• Последним 4 цифрам номера\n"
        "• @username пользователя\n\n"
        "Или нажмите 🔙 Назад"
    )

async def show_customer_card_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: int):
    """Показывает карточку пользователя администратору с управлением"""
    # Получаем данные пользователя
    cursor = db.conn.cursor()
    cursor.execute('SELECT username, first_name, last_name, phone, purchases_count FROM users WHERE user_id = ?', (customer_id,))
    user_info = cursor.fetchone()
    
    if not user_info:
        await update.message.reply_text("❌ Пользователь не найден")
        return
    
    username, first_name, last_name, phone, purchases = user_info
    
    # Формируем информацию о пользователе
    user_info_parts = []
    
    # Имя
    clean_last_name = last_name if last_name and last_name != "None" else ""
    full_name = f"{first_name or ''} {clean_last_name}".strip()
    if full_name:
        user_info_parts.append(f"👤 {full_name}")
    
    # @username
    if username and username != "Не указан":
        user_info_parts.append(f"📱 @{username}")
    
    # Телефон
    if phone:
        user_info_parts.append(f"📞 {phone}")
    
    # ID
    user_info_parts.append(f"🆔 {customer_id}")
    
    user_display = "\n".join(user_info_parts)
    
    # Получаем прогресс
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7
    
    # Создаем прогресс-бар
    progress_bar = get_coffee_progress(purchases, required)
    
    # Формируем сообщение
    text = f"""
{user_display}

{progress_bar}
{purchases}/{required}

Выберите действие:
"""
    
    # СОЗДАЕМ INLINE-КЛАВИАТУРУ с кнопкой удаления
    inline_keyboard = [
        [
            InlineKeyboardButton("➕ Начислить", callback_data=f"admin_add_{customer_id}"),
            InlineKeyboardButton("➖ Отменить", callback_data=f"admin_remove_{customer_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"admin_delete_{customer_id}")
        ]
    ]
    
    # СОЗДАЕМ REPLY-КЛАВИАТУРУ (обычные кнопки)
    reply_keyboard = [
        [KeyboardButton("✏️ Изменить данные")],
        [KeyboardButton("🔙 Назад")]
    ]
    
    # Сохраняем ID пользователя для дальнейших действий
    context.user_data['current_customer'] = customer_id
    context.user_data['current_username'] = username or f"{first_name} {last_name}".strip()
    
    # Отправляем сообщение с ДВУМЯ клавиатурами
    # Сначала inline-кнопки
    message = await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard)
    )
    
    # Сохраняем ID сообщения для возможного редактирования
    context.user_data['admin_customer_message_id'] = message.message_id
    
    # Потом reply-кнопки
    await update.message.reply_text(
        "Используйте кнопки выше для управления или:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    )
    
    # Меняем состояние на управление конкретным пользователем
    set_user_state(context, 'admin_customer_actions')

async def update_customer_card(update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: int, new_count: int):
    """Обновляет карточку пользователя после изменения счетчика"""
    # Получаем обновленные данные
    cursor = db.conn.cursor()
    cursor.execute('SELECT username, first_name, last_name, phone, purchases_count FROM users WHERE user_id = ?', (customer_id,))
    user_info = cursor.fetchone()
    
    if not user_info:
        await update.callback_query.edit_message_text("❌ Пользователь не найден")
        return
    
    username, first_name, last_name, phone, purchases = user_info
    
    # Формируем информацию о пользователе
    user_info_parts = []
    
    # Имя
    clean_last_name = last_name if last_name and last_name != "None" else ""
    full_name = f"{first_name or ''} {clean_last_name}".strip()
    if full_name:
        user_info_parts.append(f"👤 {full_name}")
    
    # @username
    if username and username != "Не указан":
        user_info_parts.append(f"📱 @{username}")
    
    # Телефон
    if phone:
        user_info_parts.append(f"📞 {phone}")
    
    # ID
    user_info_parts.append(f"🆔 {customer_id}")
    
    user_display = "\n".join(user_info_parts)
    
    # Получаем прогресс
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7
    
    # Создаем прогресс-бар
    progress_bar = get_coffee_progress(purchases, required)
    
    # Формируем сообщение
    text = f"""
{user_display}

{progress_bar}
{purchases}/{required}

Выберите действие:
"""
    
    # Обновляем inline-клавиатуру
    inline_keyboard = [
        [
            InlineKeyboardButton("➕ Начислить", callback_data=f"admin_add_{customer_id}"),
            InlineKeyboardButton("➖ Отменить", callback_data=f"admin_remove_{customer_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"admin_delete_{customer_id}")
        ]
    ]
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard)
    )
    
    # Если была 7-я покупка (подарок), уведомляем
    if purchases == 0 and new_count == 0:  # Сброс после подарка
        await notify_customer(context.bot, customer_id, purchases, required)

async def handle_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: int):
    """Удаляет пользователя с подтверждением"""
    # Получаем данные пользователя для отображения
    cursor = db.conn.cursor()
    cursor.execute('SELECT username, first_name, last_name FROM users WHERE user_id = ?', (customer_id,))
    user_info = cursor.fetchone()
    
    if not user_info:
        await update.callback_query.edit_message_text("❌ Пользователь не найден")
        return
    
    username, first_name, last_name = user_info
    
    # Формируем имя для отображения
    clean_last_name = last_name if last_name and last_name != "None" else ""
    full_name = f"{first_name or ''} {clean_last_name}".strip()
    if not full_name:
        full_name = f"@{username}" if username and username != "Не указан" else f"Пользователь {customer_id}"
    
    # Создаем клавиатуру подтверждения
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{customer_id}"),
            InlineKeyboardButton("❌ Нет, отменить", callback_data=f"cancel_delete_{customer_id}")
        ]
    ]
    
    await update.callback_query.edit_message_text(
        f"⚠️ Вы уверены, что хотите удалить пользователя?\n\n"
        f"{full_name}\n"
        f"ID: {customer_id}\n\n"
        f"Это действие нельзя отменить!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам - ТОЛЬКО для админа"""
    user = update.effective_user
    
    # Проверяем, является ли пользователь админом
    if not is_admin(user.id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам")
        return
    
    # Только админ видит этот текст
    text = """
👑 Команды администратора CoffeeRina:

📋 Основные команды:
/start - Главное меню
/backup - Создать резервную копию БД  
/sticker_id - Получить ID стикера
/help - Эта справка

🎯 Управление через кнопки:
• Баристы - добавить/удалить
• Посетители - просмотр и поиск пользователей
• Рассылка - массовая отправка сообщений
• Опции - настройки системы и переключение режимов

⚙️ В режиме настроек:
• Изменить акции - настройка программы лояльности
• Я гость - переключиться в режим посетителя
• Я бариста - переключиться в режим баристы

💡 Подсказки:
- Резервные копии создаются автоматически каждый день в 04:00
- Для баристы просто отправьте фото QR-кода в чат
- Рассылку можно отправить и потом удалить у всех пользователей
"""
    
    await update.message.reply_text(text)
# ================== ЗАПУСК ==================
def main():
    # Финальная инициализация для продакшена
    application = Application.builder().token(BOT_TOKEN).build()

    # Все обработчики как должно быть в финальной версии
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("backup", cmd_backup))
    application.add_handler(CommandHandler("sticker_id", get_sticker_id))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

    # Простой обработчик ошибок
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"❌ Ошибка: {context.error}")
    
    application.add_error_handler(error_handler)

    # Бэкапы в фоне
    import threading
    def backup_job():
        import schedule
        import time
        schedule.every().day.at("04:00").do(db.backup_db)
        schedule.every().day.at("04:01").do(lambda: db.cleanup_old_backups(7))
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    threading.Thread(target=backup_job, daemon=True).start()

    print("🚀 Бот запускается на продакшене...")
    application.run_polling()

if __name__ == "__main__":
    main()