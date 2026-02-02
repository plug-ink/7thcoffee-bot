from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import datetime
from config import BOT_TOKEN, ADMIN_IDS
from database import Database
from qr_manager import generate_qr_code, parse_qr_data, read_qr_from_image
from keyboards import *
import asyncio

import random

db = Database()

def escape_markdown(text: str, version: int = 1) -> str:
    """
    Экранирует специальные символы для Telegram Markdown
    version=1: обычный Markdown
    version=2: MarkdownV2
    """
    if version == 2:
        # Для MarkdownV2
        escape_chars = r'_*[]()~`>#+-=|{}.!'
    else:
        # Для обычного Markdown
        escape_chars = r'_*`['
    
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

def get_user_emoji(user_data):
    """
    Возвращает эмодзи для пользователя:
    ▪️ - если есть username (клиент с QR)
    ▫️ - если нет username (клиент добавлен по номеру)
    """
    username = user_data.get('username') if isinstance(user_data, dict) else user_data
    
    # Если передали строку с username
    if isinstance(username, str) and username and username != "Не указан":
        return "▪️"
    else:
        return "▫️"

def get_coffee_progress(current, total, style=None):
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

    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = f"@{username}" if username and username != "Не указан" else "Гость"
    
    # Проверяем, была ли это 7-я покупка (подарок)
    was_seventh_purchase = (new_count == 0)  # сброс после 7-й покупки
    
    # Получаем СОХРАНЕННЫЙ стиль клиента из базы
    user_saved_style_index = db.get_user_style(customer_id)
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
    
    # Используем сохраненный стиль ИЛИ первый по умолчанию
    saved_style = all_styles[user_saved_style_index] if user_saved_style_index is not None else all_styles[0]
    
    # Прогресс-бар после начисления (с СОХРАНЕННЫМ стилем)
    # Для 7-й покупки показываем полный прогресс-бар
    if was_seventh_purchase:
        progress_bar = get_coffee_progress(required, required, saved_style)  # 7 из 7
    else:
        progress_bar = get_coffee_progress(new_count, required, saved_style)
    
    try:
        # 1. СНАЧАЛА отправляем стикер
        sticker_msg = await bot.send_sticker(customer_id, "CAACAgIAAxkDAAJCWml4E2UZ3o5bF8T6JKPkXSD0KzUoAAKgkwACe69JSNZ_88TxnRpuOAQ")
        
        # 2. Если это 7-я покупка (подарок) - отправляем 3 отдельных сообщения
        if was_seventh_purchase:
            # Сообщение 1: "Напиток в подарок 🎁" (сразу после стикера)
            await asyncio.sleep(0.5)  # небольшая задержка после стикера
            gift_msg = await bot.send_message(customer_id, "Напиток в подарок 🎁")
            
            # Сообщение 2: Только прогресс-бар (полный, 7 эмодзи)
            await asyncio.sleep(0.5)
            progress_msg = await bot.send_message(customer_id, progress_bar)
            
            # Сообщение 3: Карточка клиента с новым счетчиком (0/7)
            await asyncio.sleep(3)  # прогресс-бар висит 3 секунды
            
            # Удаляем сообщение с прогресс-баром
            try:
                await progress_msg.delete()
            except Exception:
                pass
            
            # Отправляем обновленную карточку
            # Определяем эмодзи: ▪️ если есть username (клиент с QR), ▫️ если нет
            user_emoji = "▪️" if username and username != "Не указан" and username != "None" else "▫️"
            
            # Получаем телефон для отображения
            cursor.execute('SELECT phone FROM users WHERE user_id = ?', (customer_id,))
            phone_result = cursor.fetchone()
            phone_display = f"📞 {phone_result[0]}" if phone_result and phone_result[0] else ""
            
            # Создаем прогресс-бар для обнуленного состояния (0/7)
            reset_progress_bar = get_coffee_progress(0, required, saved_style)
            
            # Формируем текст карточки
            card_text = f"{user_emoji} {user_display_name}\n{phone_display}\n\n{reset_progress_bar}"
            
            await bot.send_message(customer_id, card_text)
            
            # Удаляем стикер через 4 секунды от начала
            async def delete_sticker_later():
                await asyncio.sleep(4)
                try:
                    await sticker_msg.delete()
                except Exception:
                    pass
            
            asyncio.create_task(delete_sticker_later())
            
        else:
            # Если НЕ 7-я покупка - оставляем старый формат (для 1-6 покупок)
            # Проверяем, была ли это 6-я покупка (перед подарком)
            was_sixth_purchase = (new_count == required - 1)  # 6 покупок при required=7
            
            if was_sixth_purchase:
                message = f"{user_display_name}\n\n{progress_bar}            ☑ new    \n\nСледующий 🎁"
            else:
                # Добавляем цифру оставшихся покупок
                remaining = required - new_count - 1
                if remaining > 0:
                    message = f"{user_display_name}\n\n{progress_bar}            ☑ new    \n\n{remaining}"
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
        print(f"❌ Не удалось отправить уведомление клиенту {customer_id}: {e}")
        # Fallback: отправляем простое сообщение при ошибке
        try:
            if was_seventh_purchase:
                fallback_msg = "Напиток в подарок 🎁\n\nСчетчик обнулен. Спасибо за покупку!"
                await bot.send_message(customer_id, fallback_msg)
            else:
                await bot.send_message(customer_id, f"+1 покупка! Теперь у вас: {new_count}/{required}")
        except Exception:
            pass
        
async def get_sticker_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения ID любого стикера"""
    await update.message.reply_text("Отправьте мне стикер чтобы получить его ID")

# И обработчик для стикеров будет использовать ту же логику
async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для получения ID стикера"""
    sticker = update.message.sticker
    sticker_id = sticker.file_id
    
    await update.message.reply_text(
        escape_markdown(f"📦 ID стикера:\n`{sticker_id}`\n\n"
        f"🎭 Эмодзи: {sticker.emoji or 'нет'}\n"
        f"📏 Набор: {sticker.set_name or 'нет'}", version=1),
        parse_mode='Markdown'
    )

# ================== СИСТЕМА СОСТОЯНИЙ (STATE MANAGEMENT) ==================
def set_user_state(context, state):
    context.user_data['state'] = state

def get_user_state(context):
    return context.user_data.get('state', 'main')

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_user_role(user_id, username):
    """Определяет роль пользователя"""
    if is_admin(user_id):
        return 'admin'
    elif username and db.is_user_barista(username):
        return 'barista'
    else:
        return 'client'

# ================== ОСНОВНЫЕ КОМАНДЫ (MAIN COMMANDS) ==================
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
        await show_client_main(update, context)
    print(f"🔍 user_id={user_id}, username=@{user.username}")
    print(f"📨 роль={get_user_role(user_id, user.username)}")

# ================== РЕЖИМ КЛИЕНТА (CLIENT MODE) ==================
async def show_client_main(update: Update, context: ContextTypes.DEFAULT_TYPE = None):
    user = update.effective_user
    user_id = user.id
    role = get_user_role(user.id, user.username)

    print(f"🔧 show_client_main: role={role}, state={get_user_state(context)}")

    text = """
🤎 Добро пожаловать в CoffeeRina (bot)!
    """

    keyboard = get_client_keyboard_with_back() if role == 'admin' else get_client_keyboard()
    
    print(f"🔧 Клавиатура: {keyboard}")

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
    
    if text == "◾️QR-код":
        await send_qr_code(update, user_id)
    elif text == "🎁 Акции":
        await show_promotion_info_with_context(update, context)
    elif text == "📞 Привязать номер":
        set_user_state(context, 'setting_phone')
        await update.message.reply_text("🖇 Введите ваш номер телефона (без '8') и имя через пробел\nПример👇\n\n9996664422 Саша")
    elif text == "🔙 Назад" and is_admin(user_id):
        set_user_state(context, 'main')
        await show_admin_main(update)

# ================== РЕЖИМ БАРИСТЫ (BARISTA MODE) ==================
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
    # Для баристы: используем сохраненный стиль клиента ИЛИ создаем новый если его нет
    user_saved_style_index = db.get_user_style(customer_id)
    if user_saved_style_index is not None:
        # Используем сохраненный стиль клиента
        style_index = user_saved_style_index
        style = styles[style_index]
    else:
        # Создаем случайный стиль и сохраняем его
        style_index = random.randint(0, len(styles) - 1)
        style = styles[style_index]
        db.save_user_style(customer_id, style_index)

    # Получаем данные клиента ОДИН РАЗ
    cursor = db.conn.cursor()
    cursor.execute('SELECT username, first_name, last_name, phone FROM users WHERE user_id = ?', (customer_id,))
    user_info = cursor.fetchone()
    
    if not user_info:
        await update.message.reply_text("❌ Клиент не найден в базе данных.")
        return
    
    # Извлекаем данные клиента
    customer_username = user_info[0] if user_info[0] else "Не указан"
    first_name = user_info[1] if user_info[1] else ""
    last_name = user_info[2] if user_info[2] else ""
    phone = user_info[3] if user_info[3] else None
    
    # ПРАВИЛЬНОЕ определение эмодзи: ▪️ если есть username (клиент с QR), ▫️ если нет
    if customer_username and customer_username != "Не указан" and customer_username != "None":
        user_emoji = "▪️"  # Клиент с QR
    else:
        user_emoji = "▫️"  # Клиент без QR (добавлен по номеру)

    # Сохраняем в context для текущей сессии
    context.user_data['customer_style'] = style
    context.user_data['customer_style_index'] = style_index
    
    style = context.user_data['customer_style']
    
    # Получаем количество покупок
    purchases = db.get_user_stats(customer_id)
    
    # Формируем имя для отображения
    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = f"@{customer_username}" if customer_username and customer_username != "Не указан" else "Гость"
    
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    # Создаем визуальный прогресс-бар
    progress_bar = get_coffee_progress(purchases, required, style)

    # Формируем текст карточки с номером телефона (если он есть)
    if phone:
        phone_display = f"📞 {phone}"
    else:
        phone_display = "📞"

    if purchases >= required:
        text = f"{user_emoji} {user_display_name}\n{phone_display}\n\n{progress_bar}\n\n🎉 Бесплатный напиток!"
    else:
        remaining = required - purchases - 1
        if remaining == 0:
            status_text = "Следующий 🎁"
        else:
            status_text = f"{remaining}"

        text = f"""
{user_emoji} {user_display_name}
{phone_display}

{progress_bar}

{status_text}
"""
    
    # Сохраняем ID клиента для возможного повторного начисления через ✔ Начислить
    context.user_data['current_customer'] = customer_id
    
    # ✅ АВТОМАТИЧЕСКИ ОБНОВЛЯЕМ КЛАВИАТУРУ
    keyboard = [
        [KeyboardButton("✔ Начислить")],
        [KeyboardButton("📲 Добавить номер")]
    ]
    
    if role == 'admin':
        keyboard.append([KeyboardButton("🔙 Назад")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем сообщение с информацией о клиенте и ОБНОВЛЕННОЙ клавиатурой
    await update.message.reply_text(
        text,
        reply_markup=reply_markup
    )
    # Бариста теперь может нажать ✔ Начислить для начисления покупки

    # Устанавливаем состояние для баристы или админа
    user_id = update.effective_user.id
    username = update.effective_user.username
    role = get_user_role(user_id, username)
    
    if role == 'barista':
        set_user_state(context, 'barista_mode')
    elif role == 'admin':
        set_user_state(context, 'barista_mode')  # админ в режиме баристы

async def process_coffee_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: int):
    """Обработка начисления покупки по кнопке ✔ Начислить"""
    
    # Получаем ВСЕ данные клиента ОДИН РАЗ
    cursor = db.conn.cursor()
    cursor.execute('SELECT username, first_name, last_name FROM users WHERE user_id = ?', (customer_id,))
    user_info = cursor.fetchone()
    
    if not user_info:
        await update.message.reply_text("❌ Клиент не найден")
        return
    
    username = user_info[0] if user_info[0] else None
    first_name = user_info[1] if user_info[1] else ""
    last_name = user_info[2] if user_info[2] else ""
    
    # Определяем эмодзи: ▪️ если есть username (клиент с QR), ▫️ если нет
    if username and username != "Не указан" and username != "None":
        user_emoji = "▪️"  # Клиент с QR
    else:
        user_emoji = "▫️"  # Клиент без QR (добавлен по номеру)
    
    # Формируем имя для отображения
    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = f"@{username}" if username and username != "Не указан" else "Гость"
    
    # Получаем текущее количество покупок ДО начисления
    current_purchases = db.get_user_stats(customer_id)
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    # Начисляем покупку
    new_count = db.update_user_purchases(customer_id, 1)

    # Надпись показываем когда было 5 покупок (стало 6)
    show_gift_message = (current_purchases == required - 2)  # 5 покупок при required=7
    
    # Анимация подарка когда было 6 покупок (стало 0) - 7-я покупка
    show_gift_animation = (current_purchases == required - 1)  # 6 покупок при required=7

    # Прогресс-бар
    user_saved_style_index = db.get_user_style(customer_id)

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

    # Используем сохраненный стиль ИЛИ текущий из context
    if user_saved_style_index is not None:
        saved_style = all_styles[user_saved_style_index]
    else:
        # Если стиль не сохранен, используем случайный и сохраняем
        style_index = random.randint(0, len(all_styles) - 1)
        db.save_user_style(customer_id, style_index)
        saved_style = all_styles[style_index]

    # Прогресс-бар с сохраненным стилем
    progress_bar = get_coffee_progress(new_count, required, saved_style)
    
    # Формируем сообщение для баристы
# Формируем сообщение для баристы
    if show_gift_message:
        text = f"{user_emoji} {user_display_name}\n\n{progress_bar}            ☑ new    \n\nСледующий 🎁"
    else:
        # Добавляем цифру оставшихся покупок
        remaining = required - new_count - 1
        if remaining > 0:
            text = f"{user_emoji} {user_display_name}\n\n{progress_bar}            ☑ new    \n\n{remaining}"
        else:
            text = f"{user_emoji} {user_display_name}\n\n{progress_bar}            ☑ new    "

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

async def show_admin_main(update: Update):
    text = """
👑 Панель админа
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
        await show_all_customers(update, context)
    elif text == "📣 Рассылка":
        set_user_state(context, 'broadcast_message')
        await update.message.reply_text(
            "✍ Введите текст для рассылки:\n\n"
            "!c - только клиентам\n"
            "!b - только баристам\n"
            "без префикса - всем пользователям"
        )
    elif text == "⚙️ Опции":
        set_user_state(context, 'admin_settings')
        await show_admin_settings(update)

# ================== РАССЫЛКА (BROADCAST) ==================
async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текста рассылки"""
    
    if get_user_state(context) != 'broadcast_message':
        return
    
    text = update.message.text
    
    # ЕСЛИ это кнопка - выходим из состояния рассылки
    if text in ["📙 Баристы", "📒 Посетители", "📣 Рассылка", "⚙️ Опции", "🔙 Назад"]:
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
    
    try:
        preview_msg = await update.message.reply_text(
            preview_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        return
    
    context.user_data['preview_msg_id'] = preview_msg.message_id
    set_user_state(context, 'broadcast_preview')


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
            username = barista[0]
            text += f"@{username}\n"
    else:
        text += "Баристы не добавлены"

    text += "\nВыберите действие:"

    await update.message.reply_text(text, reply_markup=get_admin_barista_keyboard())

async def show_customer_management(update: Update):
    text = "📒 Посетители\n\nИспользуйте кнопки ниже для поиска и управления клиентами"
    await update.message.reply_text(text, reply_markup=get_admin_customers_keyboard())

async def show_all_customers(update: Update, context: ContextTypes.DEFAULT_TYPE = None, page: int = 0):
    """Показывает список пользователей с пагинацией"""   
    if context:
        set_user_state(context, 'admin_customers')
        # Сохраняем текущую страницу
        context.user_data['customers_page'] = page
    
    users = db.get_all_users()
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    if not users:
        text = "📂 Клиентов пока нет."
        await update.message.reply_text(text, reply_markup=get_admin_customers_keyboard_after_list())
        return
    
    # Настройки пагинации
    PER_PAGE = 20
    total_pages = (len(users) + PER_PAGE - 1) // PER_PAGE  # Округление вверх
    
    # Проверяем границы
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    
    # Получаем пользователей для текущей страницы
    start_idx = page * PER_PAGE
    end_idx = min(start_idx + PER_PAGE, len(users))
    page_users = users[start_idx:end_idx]
    
    # Формируем текст
    text = f"📖 Страница {page + 1}/{total_pages} | Всего: {len(users)} пользователей\n\n"
    
    for idx, u in enumerate(page_users, start=start_idx + 1):
        user_id, username, first_name, last_name, purchases, phone = u
        
        # Формируем строку пользователя
        user_parts = []
        
        # Имя
        clean_last_name = last_name if last_name and last_name != "None" else ""
        full_name = f"{first_name or ''} {clean_last_name}".strip()
        if full_name:
            user_parts.append(f"{full_name}")
        
        # @username
        if username and username != "Не указан":
            user_parts.append(f"@{username}")
        
        # Номер (скрытый)
        if phone:
            masked_phone = f"---{phone[-4:]}" if len(phone) >= 4 else "---"
            user_parts.append(masked_phone)
        
        # Если ничего нет - ID
        if not user_parts:
            user_parts.append(f"ID:{user_id}")
        
        # Собираем строку
        user_str = " • ".join(user_parts)
        
        # Добавляем прогресс со статусом
        if purchases >= required:
            progress = f"{purchases}/{required} 🎉"
        elif purchases == required - 1:
            progress = f"{purchases}/{required} ⭐"
        else:
            progress = f"{purchases}/{required}"
        
        text += f"{idx}. 👤 {user_str} — {progress}\n"
    
    # Инлайн-кнопки для пагинации
    keyboard = []
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("<", callback_data=f"cust_page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(">", callback_data=f"cust_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка поиска
    keyboard.append([InlineKeyboardButton("🔍 Поиск пользователя", callback_data="cust_search")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем или редактируем сообщение
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

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
    
    # Всегда обрабатываем "Назад"
    if text == "🔙 Назад":
        set_user_state(context, 'main')
        await show_admin_main(update)
        return
    
    # ВСЕ остальные сообщения в этом состоянии - поисковые запросы
    await handle_admin_customer_search(update, context, text)

async def handle_admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
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

    # --- новое простое условие ---
    if "Условие" in text:
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

# ================== ПОИСК КЛИЕНТА (CUSTOMER SEARCH) ==================
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
                status_text = f"{remaining}"
    
            text = f"""
{user_emoji} {user_display_name}

{progress_bar}

{status_text}
"""
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
    
    elif data.startswith('client_stats_'):
        customer_id = int(data.replace('client_stats_', ''))
        # Вызываем тот же функционал, что и для кнопки "Акции"
        await show_promotion_info_with_context(update, context)
        return
    
    if data.startswith('broadcast_'):
        await handle_broadcast_buttons(update, context)
        return
    
    elif data.startswith('style_'):
        # Формат: style_prev_X или style_next_X (X = user_id)
        action, user_id_str = data.split('_')[1], data.split('_')[2]
        user_id = int(user_id_str)

        # Получаем ТЕКУЩИЙ сохраненный стиль из базы
        current_style_index = db.get_user_style(user_id)

        # Список всех стилей
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
            new_style_index = (current_style_index - 1) % len(all_styles)
        elif action == 'next':
            new_style_index = (current_style_index + 1) % len(all_styles)

        # СОХРАНЯЕМ В БАЗУ НАВСЕГДА
        db.save_user_style(user_id, new_style_index)

        # Показываем обновленный прогресс-бар
        await show_progress_with_choice(update, context, user_id, from_promotion=False)
        return
    
    elif data.startswith('bind_phone_'):
        user_id = int(data.replace('bind_phone_', ''))
        
        # Устанавливаем состояние для привязки номера
        set_user_state(context, 'setting_phone_from_callback')
        context.user_data['phone_user_id'] = user_id
        
        # Отвечаем на callback (убираем часики)
        await query.answer()
        
        # Отправляем инструкцию
        await query.message.reply_text(
            "🖇 Введите ваш номер телефона (без '8') и имя через пробел\n\n"
            "Пример:\n9996664422 Саша\n\n"
            "Или нажмите /start для отмены"
        )
        return
    
    elif data.startswith('cust_page_'):
        page = int(data.replace('cust_page_', ''))
        await show_all_customers(update, context, page)
        return
    
    elif data == 'cust_search':
        await query.answer("Используйте поле ввода для поиска")
        # Можно показать подсказку
        await query.edit_message_text(
            "🔍 Для поиска отправьте в чат:\n"
            "• Номер телефона (10 цифр)\n"
            "• Последние 4 цифры номера\n"
            "• @username пользователя\n\n"
            "Примеры:\n9996664422\n4422\n@username",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 К списку", callback_data="cust_page_0")]
            ])
        )
        return
    
    elif data == 'noop':
        await query.answer()
        return

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

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (HELPER FUNCTIONS) ==================
async def send_qr_code(update: Update, user_id: int, with_buttons: bool = True):
    """Генерирует и отправляет QR-код с инлайн-кнопками"""
    qr_image = generate_qr_code(user_id)
    caption = "📱 Ваш персональный QR-код\n\nПокажите его баристе при заказе"
    
    if with_buttons:
        # Создаем инлайн-кнопки (ИЗМЕНИЛИ "Профиль" на "Статус")
        keyboard = [
            [InlineKeyboardButton("🪪 Прогресс-бар", callback_data=f"client_stats_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_photo(
            photo=qr_image, 
            caption=caption,
            reply_markup=reply_markup
        )
    else:
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
            status_text = f"{remaining}"
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

async def show_progress_with_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, from_promotion=False):
    """Показывает прогресс-бар с кнопками выбора стиля
    from_promotion: True если вызов из акции (нужно новое сообщение), False если редактирование"""
    
    if update.callback_query and not from_promotion:
        # Вызов из инлайн-кнопки (редактируем существующее)
        query = update.callback_query
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        edit_method = query.edit_message_text
        send_new = False
    else:
        # Вызов из акции или обычного сообщения (отправляем новое)
        if update.callback_query:
            query = update.callback_query
            chat_id = query.message.chat_id
        elif update.message:
            chat_id = update.message.chat_id
        else:
            print("❌ Ошибка: нет сообщения или callback для ответа")
            return
        edit_method = None
        send_new = True
    
    # Получаем данные пользователя
    cursor = db.conn.cursor()
    cursor.execute('SELECT purchases_count, first_name, last_name, phone, username FROM users WHERE user_id = ?', (user_id,))
    user_info = cursor.fetchone()
    
    if not user_info:
        print(f"❌ Пользователь {user_id} не найден")
        return
    
    purchases = user_info[0] if user_info else 0
    first_name = user_info[1] if user_info else ""
    last_name = user_info[2] if user_info else ""
    phone = user_info[3] if user_info else None
    username = user_info[4] if user_info else None
    
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

    # Получаем СОХРАНЕННЫЙ стиль из базы данных
    style_index = db.get_user_style(user_id)
    style = all_styles[style_index]
    
    # Создаем прогресс-бар с ВЫБРАННЫМ стилем
    progress_bar = get_coffee_progress(purchases, required, style)
    
    # Формируем имя для отображения
    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = f"@{username}" if username else "Гость"
    
    # Определяем эмодзи: ▪️ если есть username (клиент с QR), ▫️ если нет (добавлен по номеру)
    if username and username != "Не указан" and username != "None":
        user_emoji = "▪️"  # Клиент с QR
    else:
        user_emoji = "▫️"  # Клиент без QR (добавлен по номеру)
    
    # Форматируем номер телефона (если есть)
    if phone:
        # Форматируем номер: первые 6 цифр + [последние 4] в скрытом формате
        phone_display = f"📞 {phone}"
    else:
        phone_display = "📞"
    
    # Текст с прогресс-баром
    if purchases >= required:
        text = f"{user_emoji} {user_display_name}\n{phone_display}\n\n{progress_bar}\n\n🎉 Бесплатный напиток доступен!"
    else:
        remaining = required - purchases - 1
        if remaining == 0:
            status_text = "Следующий 🎁"
        else:
            status_text = f"{remaining}"
        text = f"{user_emoji} {user_display_name}\n{phone_display}\n\n{progress_bar}\n\n{status_text}"
    
    # Инлайн-кнопки для переключения стилей и привязки номера
    keyboard_buttons = []
    
    # Строка 1: Кнопки стилей
    keyboard_buttons.append([
        InlineKeyboardButton("<", callback_data=f"style_prev_{user_id}"),
        InlineKeyboardButton(f"{style_index + 1}/{len(all_styles)}", callback_data="noop"),
        InlineKeyboardButton(">", callback_data=f"style_next_{user_id}")
    ])
    
    # Строка 2: Кнопка привязки/изменения номера
    if phone:
        phone_button_text = "📞 Изменить номер"
    else:
        phone_button_text = "📞 Привязать номер"
    
    keyboard_buttons.append([
        InlineKeyboardButton(phone_button_text, callback_data=f"bind_phone_{user_id}")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    
    # Отправляем или редактируем сообщение
    try:
        if not send_new and edit_method:
            # Редактируем существующее сообщение (callback смены стиля)
            await edit_method(
                text,
                reply_markup=reply_markup
            )
        else:
            # Отправляем новое сообщение (вызов из акции или обычный)
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup
            )

    except Exception as e:
        print(f"❌ Ошибка при показе прогресс-бара: {e}")
        # Пробуем отправить без форматирования
        try:
            if not send_new and edit_method:
                await edit_method(text, reply_markup=reply_markup)
            else:
                await context.bot.send_message(chat_id, text, reply_markup=reply_markup)
        except Exception as e2:
            print(f"❌ Критическая ошибка: {e2}")

async def show_promotion_info_with_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает акцию и прогресс-бар с выбором стиля (с context)"""
    
    user = update.effective_user
    user_id = user.id
    
    # Определяем, откуда пришел вызов: из сообщения или callback
    if update.message:
        # Вызов из обычного сообщения
        chat_id = update.message.chat_id
        reply_method = update.message.reply_text
        is_callback = False
    elif update.callback_query:
        # Вызов из инлайн-кнопки
        query = update.callback_query
        chat_id = query.message.chat_id
        reply_method = query.message.reply_text
        is_callback = True
        # Отвечаем на callback, чтобы убрать "часики" на кнопке
        await query.answer()
    else:
        print("❌ Ошибка: не могу определить источник вызова")
        return
    
    # Отправляем описание акции
    promotion = db.get_promotion()
    if promotion:
        promotion_text = (
            f"🎁 {promotion[1]}\n\n"
            f"{promotion[3] if promotion[3] else 'Покажите QR-код при каждой покупке'}"
        )
    else:
        promotion_text = "Акция ещё не настроена"
    
    try:
        # Используем правильный метод для отправки
        promotion_msg = await reply_method(promotion_text)
        message_id = promotion_msg.message_id
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения: {e}")
        # Если не получилось через reply_method, попробуем напрямую
        try:
            promotion_msg = await context.bot.send_message(chat_id, promotion_text)
            message_id = promotion_msg.message_id
        except Exception as e2:
            print(f"❌ Ошибка при прямом отправлении: {e2}")
            return
    
    # Ждем 2 секунды
    await asyncio.sleep(2)
    
    # Теперь показываем прогресс-бар с кнопками
    # Передаем информацию о том, что это вызов из акции (нужно новое сообщение)
    await show_progress_with_choice(update, context, user_id, from_promotion=True)
    
    # Удаляем сообщение об акции через 5 секунд
    async def delete_promotion_message():
        await asyncio.sleep(5)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass  # Игнорируем ошибки удаления
    
    asyncio.create_task(delete_promotion_message())

# ================== ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ (MAIN MESSAGE HANDLER) ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = get_user_state(context)
    text = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username
        
    role = get_user_role(user_id, username)

    # ✅ ПЕРЕМЕСТИ ЭТУ ПРОВЕРКУ СЮДА - САМОЕ ПЕРВОЕ!
    if state == 'broadcast_message':
        await handle_broadcast_message(update, context)
        return

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
        elif text in ["📲 Добавить номер", "✔ Начислить"]:
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

                user_id = update.effective_user.id
                username = update.effective_user.username
                role = get_user_role(user_id, username)
                
                if role == 'barista':
                    set_user_state(context, 'barista_mode')
                elif role == 'admin':
                    set_user_state(context, 'barista_mode')
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
        elif text == "📲 Добавить номер":
            # Игнорируем повторное нажатие той же кнопки
            return
        
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
        if text == "✔ Начислить":
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                await process_coffee_purchase(update, context, customer_id)
            else:
                await update.message.reply_text("❌ Сначала найдите клиента по QR или номеру")
            return
        
        elif text == "📲 Добавить номер":
            set_user_state(context, 'adding_customer')
            await update.message.reply_text("💬 Для добавления отправь\nНОМЕР ИМЯ\nв формате как это:\n\n9996664422 Саша")
            return
            
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
                    
                    set_user_state(context, 'barista_mode')
                    
                else:
                    await update.message.reply_text("❌ Номер должен быть 10 цифр")
                    
            except (ValueError, IndexError):
                await update.message.reply_text("❌ Формат: номер имя\nПример: 9996664422 Саша")
            return
        
        elif text.isdigit() and len(text) == 10:
            customer_id = db.find_user_by_phone(text)
            if customer_id:
                await update.message.reply_text("✅ Найден клиент по номеру")
                await asyncio.sleep(0.5)
                await process_customer_scan(update, context, customer_id)
            else:
                await update.message.reply_text(f"❌ Клиент с номером {text} не найден\n\nИспользуйте формат: 9996664422 Саша")
            return
        
        else:
            await update.message.reply_text("📸 Отправьте фото QR или введите номер имя\nПример: 9996664422 Саша")
            return


    elif state == 'barista_action':
        if text == "✔ Засчитать покупку":
    
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                new_count = db.update_user_purchases(customer_id, 1)
                promotion = db.get_promotion()
                required = promotion[2] if promotion else 7

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
                    remaining_for_free = max(0, required - new_count - 1)
                    text = f"{user_display_name}\t\t☑️ + 1\n\n{progress_bar}\n\nДо бесплатного напитка: {remaining_for_free}"
            
                customer_card_message_id = context.user_data.get('customer_card_message_id')
                if customer_card_message_id:
                    try:
                        await context.bot.delete_message(
                            chat_id=update.effective_chat.id,
                            message_id=customer_card_message_id
                        )
                    except Exception:
                        pass  # Игнорируем ошибки удаления

                keyboard = [
                    [KeyboardButton("✔ Засчитать покупку")],
                    [KeyboardButton("🔙 Назад")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
                new_message = await update.message.reply_text(text, reply_markup=reply_markup)
                context.user_data['customer_card_message_id'] = new_message.message_id
            
                # Уведомляем клиента
                await notify_customer(context.bot, customer_id, new_count, required)
    
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
        customer_id = context.user_data.get('current_customer')

        promotion = db.get_promotion()
        required = promotion[2] if promotion else 7

        if text.startswith("➕"):
            new_count = db.update_user_purchases(customer_id, 1)
        elif text.startswith("➖"):
            new_count = db.update_user_purchases(customer_id, -1)
        elif text.startswith("🔙"):
            set_user_state(context, 'admin_customers')
            await show_customer_management(update)
            return
        else:
            return

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
    # Обработка кнопки "Назад" в разных режимах
    if text == "🔙 Назад":
        if state == 'barista_mode':
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
            if text == "Найти пользователя":
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
    if state == 'main':
        if role == 'admin' and state != 'barista_mode':
            if text == "📙 Баристы":
                set_user_state(context, 'admin_barista')
                await show_barista_management(update)
                return
            
            elif text == "📣 Рассылка":
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

        elif role == 'client':
            if text == "◾️QR-код":
                await send_qr_code(update, user_id)
                return
    
    elif state == 'client_mode':
        await handle_client_mode(update, context)

    elif state == 'setting_phone' or state == 'setting_phone_from_callback':
        if text == "🔙 Назад":
            if state == 'setting_phone_from_callback':
                # Возвращаемся к карточке клиента
                user_id = context.user_data.get('phone_user_id')
                if user_id:
                    await show_progress_with_choice(update, context, user_id, from_promotion=True)
                else:
                    set_user_state(context, 'client_mode')
                    await show_client_main(update, context)
            else:
                set_user_state(context, 'client_mode')
                await show_client_main(update, context)
            return
        elif text == "◾️QR-код":
            set_user_state(context, 'client_mode')
            await send_qr_code(update, user_id)
            return
        
        if " " in text:
            try:
                parts = text.split(" ", 1)
                phone = parts[0].strip()
                name = parts[1].strip()
            
                if phone.isdigit() and len(phone) == 10:
                    # Получаем user_id - либо из контекста, либо из текущего пользователя
                    if state == 'setting_phone_from_callback':
                        target_user_id = context.user_data.get('phone_user_id', user_id)
                    else:
                        target_user_id = user_id
                
                    # Обновляем имя и номер
                    cursor = db.conn.cursor()
                    cursor.execute('UPDATE users SET first_name = ?, phone = ? WHERE user_id = ?', 
                                 (name, phone, target_user_id))
                    db.conn.commit()
                
                    await update.message.reply_text(
                        f"✅ Ваш профиль обновлен: {name} ({phone})\n"
                        f"Теперь вы можете назвать номер баристе при заказе"
                    )
                    
                    if state == 'setting_phone_from_callback':
                        await show_progress_with_choice(update, context, target_user_id, from_promotion=True)
                    else:
                        set_user_state(context, 'client_mode')
                        await show_client_main(update, context)
                        
                else:
                    await update.message.reply_text("❌ Номер должен быть 10 цифр")
                
            except (ValueError, IndexError):
                await update.message.reply_text("❌ Формат: номер имя\nПример: 9996664422 Саша")
        else:
            await update.message.reply_text(
                "❌ Введите номер и имя через пробел\nПример: 9996664422 Саша\n\n"
                "Или нажмите '🔙 Назад' для отмены"
            )
        return

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
        # Обрабатываем кнопки которые попали сюда
        if text == "✔ Начислить" and state == 'barista_mode':
            customer_id = context.user_data.get('current_customer')
            if customer_id:
                await process_coffee_purchase(update, context, customer_id)
            else:
                await update.message.reply_text("❌ Сначала найдите клиента по QR или номеру")

        elif text == "📲 Добавить номер" and (state == 'barista_mode' or (state == 'main' and role == 'barista')):
            set_user_state(context, 'adding_customer')
            await update.message.reply_text("💬 Для добавления отправь\nНОМЕР ИМЯ\nв формате как это:\n\n9996664422 Саша")
        # Вместо перезапуска показываем текущее меню
        # elif state == 'barista_mode':
        #     await show_barista_main(update)
        elif state == 'client_mode':
            await show_client_main(update, context)
        elif state == 'main' and role == 'admin':
            await show_admin_main(update)
        elif state == 'main' and role == 'barista':
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
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith('cancel_'):
        # возвращаем баристу в главное меню
        await show_barista_main(update)
        # редактируем сообщение, чтобы кнопки исчезли
        await query.edit_message_text("🔄 Возвращаюсь в меню баристы...")
async def handle_customer_by_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода @username после нажатия кнопки 'Найти пользователя'"""
    username_input = update.message.text.strip().lstrip('@').lstrip('‘').lstrip('’').lstrip('"').lstrip("'")

    if not username_input:
        await update.message.reply_text("❌ Введите корректный @username")
        set_user_state(context, 'admin_customers')
        return

    user_data = db.get_user_by_username_exact(username_input)

    if user_data:
        customer_id, username, first_name, last_name = user_data
        purchases = db.get_user_stats(customer_id)
        promotion = db.get_promotion()
        required = promotion[2] if promotion else 7

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
                status_text = f"{remaining}"
    
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
        await update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

        context.user_data['current_customer'] = customer_id
        context.user_data['current_username'] = username or f"{first_name} {last_name}".strip() or "Гость"
        set_user_state(context, 'admin_customer_actions')
        return

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
        user_info_parts.append(f"◾️ @{username}")
    
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
        [KeyboardButton("✏️ Изменить данные (откл)")],
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
        user_info_parts.append(f"◾️ @{username}")
    
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
    """Справка по командам - РАЗНАЯ для каждой роли"""
    user = update.effective_user
    user_id = user.id
    username = user.username
    
    # Определяем роль пользователя
    role = get_user_role(user_id, username)
    
    if role == 'admin':
        # Помощь для админа
        text = """
👑 Команды админа:

📋 Основные команды:
/start - Главное меню
/backup - Создать резервную копию БД  
/sticker_id - Получить ID стикера
/help - Эта справка

🎯 Управление через кнопки:
• Баристы - добавить/удалить
• Посетители - просмотр и поиск пользователей
• Рассылка - массовая отправка сообщений
• Опции - Переключение режимов

⚙️ В Опциях:
• Изменить акции - изменение программы лояльности
• Я гость - переключиться на панель посетителя
• Я бариста - переключиться на панель баристы

💡 Подсказки:
- Резервные копии создаются автоматически каждый день в 04:00
- Для баристы просто отправьте фото QR-кода или номер в чат
- Рассылку можно отправить и потом удалить у всех пользователей
"""
    
    elif role == 'barista':
        # Помощь для баристы
        text = """
🐾 Инструкция для баристы CoffeeRina:

Акция 🎁 7-й напиток в подарок

Начисляем +1 за покупку напитка
1 чек = 1 '✔ Начислить'

📋 Основные команды:
/start - Главное меню
/help - Эта инструкция

🔍 Как найти клиента:

📸 По QR-коду:
1. Клиент показывает QR-код
2. Сфотографируйте QR-код
3. Отправьте фото в этот чат
4. Появится карточка клиента
5. Нажмите '✔ Начислить' для начисления покупки

📞 По номеру телефона:
1. Клиент называет номер (10 цифр или 4 последних)
2. Отправьте номер в чат: 9998887766 или 7766
3. Если клиент найден - появится карточка
4. Если нет - используйте формат: 9996664422 Имя

➕ Как добавить нового клиента:
1. Нажмите '📲 Добавить номер'
2. Отправьте: 9996664422 Имя
3. Клиент создан, появится карточка
4. Нажмите '✔ Начислить' для первой покупки

💡 Подсказки:
- Клиенты с QR-кодом: ▪️ черный квадратик
- Клиенты без QR-кода: ▫️ белый квадратик
- На 6-й покупке будет надпись "Следующий 🎁"
- На 7-й покупке счетчик обнуляется (подарок)
"""
    
    else:  # role == 'client'
        # Помощь для клиента
        text = """
🤎 Информация для посетителя CoffeeRina:

🎁 Акция: Каждый 7-й напиток в подарок!

📋 Основные команды:
/start - Главное меню  
/help - Эта информация

📱 Ваш QR-код:
• Нажмите кнопку "◾️QR-код" чтобы получить свой QR-код
• Показывайте QR-код при каждой покупке
• Бариста отсканирует его и начислит покупку

📞 Привязка номера телефона:
• Нажмите "📞 Привязать номер"
• Введите: 9996664422 ВашеИмя
• После этого можете называть только номер телефона или последние 4 цифры

📊 Отслеживание прогресса:
• Нажмите на кнопку "🪪 Прогресс-бар" под QR-кодом
• Увидите свой прогресс (сколько покупок из 7)
• Можете менять стиль прогресс-бара (< >)

💡 Как это работает:
1. Скачайте QR-код или привяжите номер телефона
2. При каждой покупке показывайте QR или называйте номер (4 цифры)
3. Бариста начислит покупку
4. 7-й напиток в подарок

❓ По вопросам обращайтесь к баристе
"""
    
    await update.message.reply_text(text)
# ================== ЗАПУСК БОТА (BOT STARTUP) ==================
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