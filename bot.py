from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram import ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
import datetime
from datetime import datetime, time as dt_time, timedelta
from config import BOT_TOKEN, ADMIN_IDS
from database import Database
from qr_manager import generate_qr_code, parse_qr_data, read_qr_from_image
from keyboards import *
import asyncio
import random
import logging
from logging.handlers import RotatingFileHandler
import os
import traceback
import pytz


# Часовой пояс Владивостока (UTC+10)
VLADIVOSTOK_TZ = pytz.timezone("Asia/Vladivostok")


def get_vladivostok_now():
    """Возвращает текущее datetime во Владивостоке"""
    return datetime.now(VLADIVOSTOK_TZ)


def get_vladivostok_today_str():
    """Возвращает строку сегодняшней даты во Владивостоке"""
    return get_vladivostok_now().strftime("%Y-%m-%d")


# =============================================LOGGING=================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-5s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


file_handler = RotatingFileHandler(
    "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-5s | %(name)-20s | %(message)s")
)
logging.getLogger().addHandler(file_handler)

logger = logging.getLogger(__name__)
logger.info("Логирование инициализировано | уровень: %s", LOG_LEVEL)


async def delete_message_after_delay(message, delay_seconds: int = 1):
    """Удаляет сообщение через указанное количество секунд"""
    await asyncio.sleep(delay_seconds)
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение: {e}")


async def send_hint_message(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_role: str
):
    """Отправляет подсказку для баристов и админов"""
    hint_text = "<i>для поиска отправьте 4 цифры номера или фото QR</i>"

    # Удаляем старую подсказку если была
    old_hint_id = context.user_data.get("hint_message_id")
    if old_hint_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=old_hint_id)
        except Exception:
            pass
        context.user_data.pop("hint_message_id", None)

    # Отправляем новую подсказку
    hint_msg = await context.bot.send_message(
        chat_id=chat_id, text=hint_text, parse_mode="HTML"
    )
    context.user_data["hint_message_id"] = hint_msg.message_id
    logger.info(f"Подсказка отправлена для role={user_role}")


async def delete_hint_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Удаляет подсказку"""
    hint_id = context.user_data.get("hint_message_id")
    if hint_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=hint_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить подсказку: {e}")
        context.user_data.pop("hint_message_id", None)


async def send_temp_message(update: Update, text: str, delay_seconds: int = 2):
    """Отправляет временное сообщение, которое удалится через указанное количество секунд"""
    try:
        msg = await update.message.reply_text(text)
        asyncio.create_task(delete_message_after_delay(msg, delay_seconds))
    except Exception as e:
        logger.debug(f"Не удалось отправить временное сообщение: {e}")


# ===================================================================
db = Database()

from collections import defaultdict
import time

# Для защиты от спама
client_last_message_time = defaultdict(float)  # user_id -> timestamp

logger.info(
    "База данных инициализирована | путь: %s",
    db.conn.execute("PRAGMA database_list").fetchone()[2],
)


def escape_markdown(text: str, version: int = 1) -> str:
    """
    Экранирует специальные символы для Telegram Markdown
    version=1: обычный Markdown
    version=2: MarkdownV2
    """
    if version == 2:
        escape_chars = r"_*[]()~`>#+-=|{}.!"
    else:
        escape_chars = r"_*`["

    return "".join(["\\" + char if char in escape_chars else char for char in text])


def escape_html(text: str) -> str:
    """
    Экранирует спецсимволы для Telegram HTML
    """
    if not text:
        return ""
    escape_chars = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
    }
    for char, escaped in escape_chars.items():
        text = text.replace(char, escaped)
    return text


def get_user_emoji(user_data):
    username = user_data.get("username") if isinstance(user_data, dict) else user_data
    if isinstance(username, str) and username and username != "Не указан":
        return "▪️"
    else:
        return "▫️"


def get_coffee_progress(current, total, style=None):
    if total <= 0:
        return "❌ Ошибка акции"

    if current >= total:
        return style["filled"] * total

    filled = current
    empty = total - 1 - filled
    progress = style["filled"] * filled
    progress += style["empty"] * empty
    progress += style["gift"]
    return progress


async def notify_customer(bot, customer_id, new_count, required):
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT username, first_name, last_name, phone FROM users WHERE user_id = ?",
        (customer_id,),
    )
    user_info = cursor.fetchone()

    if not user_info:
        logger.error(f"Пользователь {customer_id} не найден в notify_customer")
        return

    username = user_info[0] if user_info[0] else "Не указан"
    first_name = user_info[1] if user_info[1] else ""
    last_name = user_info[2] if user_info[2] else ""
    phone = user_info[3] if user_info[3] else ""  # <--- ДОБАВЛЕНО

    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = (
            f"@{username}" if username and username != "Не указан" else "Гость"
        )

    was_seventh_purchase = new_count == 0

    user_saved_style_index = db.get_user_style(customer_id)
    all_styles = [
        {"filled": "☕", "empty": "▫", "gift": "🎁"},
        {"filled": "☕", "empty": "🔳", "gift": "🔲"},
        {"filled": "☕", "empty": "⚪", "gift": "🟤"},
        {"filled": "🥤", "empty": "⚪", "gift": "🔴"},
        {"filled": "🧋", "empty": "🧊", "gift": "🧊"},
        {"filled": "🍜", "empty": "◾", "gift": "🈹"},
        {"filled": "🍪", "empty": "◻", "gift": "🉑"},
        {"filled": "🟣", "empty": "⚪", "gift": "⬛"},
        {"filled": "🧋", "empty": "⚪", "gift": "🟠"},
    ]

    saved_style = (
        all_styles[user_saved_style_index]
        if user_saved_style_index is not None
        else all_styles[0]
    )

    # Удаляем предыдущее сообщение
    if "user_contexts" not in db.__dict__:
        db.user_contexts = {}
    if customer_id not in db.user_contexts:
        db.user_contexts[customer_id] = {}

    last_new_msg_id = db.user_contexts[customer_id].get("last_new_message_id")
    if last_new_msg_id:
        try:
            await bot.delete_message(chat_id=customer_id, message_id=last_new_msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить предыдущее сообщение: {e}")

    # Формируем прогресс-бар
    if was_seventh_purchase:
        progress_bar = get_coffee_progress(required, required, saved_style)
    else:
        progress_bar = get_coffee_progress(new_count, required, saved_style)

    # ========== ОСНОВНОЕ УВЕДОМЛЕНИЕ (всегда через прогресс-бар) ==========
    try:
        if was_seventh_purchase:
            # Подарок
            message = (
                f"🎁 <b>НАПИТОК В ПОДАРОК!</b>\n\n{progress_bar}\n\nСпасибо за покупки!"
            )
            gift_msg = await bot.send_message(customer_id, message, parse_mode="HTML")
            db.user_contexts[customer_id]["last_new_message_id"] = gift_msg.message_id

            # Показываем сброшенный прогресс
            await asyncio.sleep(1.5)
            reset_progress_bar = get_coffee_progress(0, required, saved_style)

            # Формируем карточку пользователя (одна строка через " | ")
            info_parts = [user_display_name]
            if phone:
                phone_display = phone if phone else ""
                info_parts.append(phone_display)
            header_line = " | ".join(info_parts)
            card_text = f"{header_line}\n\n{reset_progress_bar}"

            card_msg = await bot.send_message(customer_id, card_text)

            # Удаляем карточку через 5 секунд
            async def delete_card():
                await asyncio.sleep(5)
                try:
                    await card_msg.delete()
                except Exception:
                    pass

            asyncio.create_task(delete_card())

        else:
            # Обычная покупка
            remaining = required - new_count - 1
            if remaining == 0:
                status = "🎁 <b>Следующий напиток в подарок!</b>"
            elif remaining > 0:
                status = f"Осталось {remaining} покупок до подарка 🎁"
            else:
                status = ""

            message = f"{progress_bar}\n\n{status}"
            new_msg = await bot.send_message(customer_id, message, parse_mode="HTML")
            db.user_contexts[customer_id]["last_new_message_id"] = new_msg.message_id

    except Exception as e:
        logger.error(f"Ошибка отправки прогресс-бара клиенту {customer_id}: {e}")
        # Фолбэк: отправляем простой текст
        try:
            if was_seventh_purchase:
                fallback_msg = await bot.send_message(
                    customer_id,
                    f"🎁 Напиток в подарок!\n\nСчетчик обнулен. Спасибо за покупку!",
                )
            else:
                fallback_msg = await bot.send_message(
                    customer_id, f"✅ +1 покупка! Теперь у вас: {new_count}/{required}"
                )
            db.user_contexts[customer_id]["last_new_message_id"] = (
                fallback_msg.message_id
            )
        except Exception as e2:
            logger.error(f"Не удалось отправить даже фолбэк-сообщение: {e2}")

    # ========== ОПЦИОНАЛЬНЫЙ СТИКЕР (если отправится - хорошо, нет - не страшно) ==========
    STICKER_ID = (
        "CAACAgIAAxkBAAIZ42l5spbFuIyf1pkH87s4arTiQ5A3AAKgkwACe69JSOkCZJA4kAhVOAQ"
    )
    try:
        sticker_msg = await bot.send_sticker(customer_id, STICKER_ID)

        async def delete_sticker_later():
            await asyncio.sleep(4)
            try:
                await sticker_msg.delete()
            except Exception:
                pass

        asyncio.create_task(delete_sticker_later())
    except Exception as e:
        logger.debug(f"Не удалось отправить стикер (это не критично): {e}")


async def ask_for_review(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Отправляет запрос на отзыв после получения штампа"""
    logger.info(f"📝 ask_for_review для user_id={user_id}")

    # Проверяем, не отключил ли пользователь уведомления навсегда
    if (
        "user_contexts" in context.bot_data
        and user_id in context.bot_data["user_contexts"]
    ):
        if context.bot_data["user_contexts"][user_id].get("never_show_review", False):
            logger.info(
                f"Пользователь {user_id} навсегда отключил уведомления об отзывах, пропускаем"
            )
            return

    # Проверяем, не отправляли ли уже сегодня
    if "user_contexts" not in context.bot_data:
        context.bot_data["user_contexts"] = {}
    if user_id not in context.bot_data["user_contexts"]:
        context.bot_data["user_contexts"][user_id] = {}

    # Если уже отправляли запрос сегодня - пропускаем
    if context.bot_data["user_contexts"][user_id].get("review_asked_today", False):
        logger.info(f"Запрос на отзыв уже отправлен сегодня для {user_id}, пропускаем")
        return

    context.bot_data["user_contexts"][user_id]["review_asked_today"] = True

    # Определяем, нажимал ли пользователь когда-нибудь "Оставить отзыв"
    has_clicked_review = context.bot_data["user_contexts"][user_id].get(
        "review_clicked", False
    )

    if has_clicked_review:
        # Если уже нажимал, показываем кнопки: "Оставить отзыв" + "Не показывать"
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📝 Оставить отзыв", callback_data=f"start_review_{user_id}"
                    ),
                    InlineKeyboardButton(
                        "🚫 Не показывать", callback_data=f"never_show_review_{user_id}"
                    ),
                ]
            ]
        )
        text = "☕️ <b>Поделитесь мнением о посещении кофейни!</b>\n\nВаш отзыв поможет нам стать лучше ✨"
    else:
        # Если первый раз, показываем только "Оставить отзыв"
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📝 Оставить отзыв", callback_data=f"start_review_{user_id}"
                    )
                ]
            ]
        )
        text = "☕️ <b>Поделитесь мнением о посещении кофейни!</b>\n\nВаш отзыв поможет нам стать лучше ✨"

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        logger.info(f"✅ Запрос на отзыв отправлен пользователю {user_id}")
    except Exception as e:
        logger.error(f"❌ Не удалось отправить запрос на отзыв {user_id}: {e}")


async def get_sticker_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправьте мне стикер чтобы получить его ID")


async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sticker = update.message.sticker
    sticker_id = sticker.file_id

    await update.message.reply_text(
        escape_markdown(
            f"📦 ID стикера:\n`{sticker_id}`\n\n"
            f"🎭 Эмодзи: {sticker.emoji or 'нет'}\n"
            f"📏 Набор: {sticker.set_name or 'нет'}",
            version=1,
        ),
        parse_mode="Markdown",
    )


# ================== СИСТЕМА СОСТОЯНИЙ ==================
def set_user_state(context, state):
    context.user_data["state"] = state
    logger.debug(f"Состояние изменено на: {state}")


# Состояния пользователей:
# - main (основное)
# - client_mode (режим клиента)
# - barista_mode (режим бариста)
# - admin_main (админ-панель)
# - admin_users_list (список пользователей)
# - admin_barista (управление баристами)
# - setting_phone (привязка номера)
# - waiting_for_review_text (ожидание текста отзыва)  # <-- НОВОЕ


def get_user_state(context):
    return context.user_data.get("state", "main")


def is_admin(user_id):
    return user_id in ADMIN_IDS


def get_user_role(user_id, username):
    if is_admin(user_id):
        return "admin"
    elif username and db.is_user_barista(username):
        return "barista"
    else:
        return "client"


# ================== ОСНОВНЫЕ КОМАНДЫ ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Игнорируем старые сообщения (кэш)
    if update.message and update.message.date:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        message_age = (now - update.message.date).total_seconds()
        if message_age > 3:
            logger.info(
                f"Игнорируем старое сообщение /start (возраст {message_age} сек)"
            )
            return

    user = update.effective_user
    user_id = user.id
    db.get_or_create_user(user_id, user.username, user.first_name, user.last_name)
    set_user_state(context, "main")

    role = get_user_role(user_id, user.username)
    logger.info(f"START | user_id={user_id}, username=@{user.username}, role={role}")

    remove_keyboard = ReplyKeyboardRemove()

    if role == "admin":
        # Отправляем служебное сообщение, которое удалим через секунду
        temp_msg = await update.message.reply_text(
            "admin panel", reply_markup=remove_keyboard
        )
        asyncio.create_task(delete_message_after_delay(temp_msg, 1))

        # Показываем админ-панель
        await show_admin_main(update, context, force_new=True)

        # Отправляем подсказку
        await send_hint_message(context, update.effective_chat.id, role)

    elif role == "barista":
        # Отправляем служебное сообщение, которое удалим через секунду
        temp_msg = await update.message.reply_text(
            "barista panel", reply_markup=remove_keyboard
        )
        asyncio.create_task(delete_message_after_delay(temp_msg, 1))

        # Отправляем приветственное сообщение бариста
        await update.message.reply_text(
            "🧢 CoffeeRina bot\n\n/help - справка", reply_markup=remove_keyboard
        )

        await show_barista_main(update)

        # Отправляем подсказку
        await send_hint_message(context, update.effective_chat.id, role)

    else:
        # ========== КЛИЕНТ ==========
        # Временное сообщение (исчезает)
        temp_msg = await update.message.reply_text(
            "client panel", reply_markup=remove_keyboard
        )
        asyncio.create_task(delete_message_after_delay(temp_msg, 1))

        await show_client_main(update, context)


async def cmd_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username
    role = get_user_role(user_id, username)

    if role not in ["barista", "admin"]:
        await update.message.reply_text("❌ Эта команда недоступна.")
        return

    # Отправляем временное сообщение, которое удалится через 1 секунду
    temp_msg = await update.message.reply_text(
        "client mode", reply_markup=ReplyKeyboardRemove()
    )
    asyncio.create_task(delete_message_after_delay(temp_msg, 1))

    set_user_state(context, "client_mode")
    await show_client_main(update, context)


# ================== РЕЖИМ КЛИЕНТА ==================
async def show_client_main(update: Update, context: ContextTypes.DEFAULT_TYPE = None):
    user = update.effective_user
    user_id = user.id
    role = get_user_role(user.id, user.username)

    text = "🤎 CoffeeRina bot!\n\n/help - справка"
    keyboard = get_client_keyboard()

    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)

    if role == "client" or (
        role in ["admin", "barista"]
        and context
        and get_user_state(context) == "client_mode"
    ):
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
        set_user_state(context, "setting_phone")
        await update.message.reply_text(
            "🖇 Введите ваш номер телефона (без '8') и имя через пробел\nПример👇\n\n9996664422 Саша"
        )


# ================== РЕЖИМ БАРИСТЫ ==================
async def show_barista_main(update: Update):
    # Защита от дублирования
    if hasattr(show_barista_main, "_last_call"):
        if time.time() - show_barista_main._last_call < 2:
            logger.info("Игнорируем дублирующий вызов show_barista_main")
            return
    show_barista_main._last_call = time.time()

    # НЕ отправляем сообщение "barista panel" — оно уже отправлено в start()
    # Просто убираем клавиатуру, если она есть
    if update.callback_query:
        await update.callback_query.edit_message_text("barista panel")
    # Для message-вызова — ничего не отправляем, так как start уже отправил


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    state = get_user_state(context)
    if state == "broadcast_waiting_input":
        # Перенаправляем в обработчик рассылки
        await handle_broadcast_message(update, context)
        return

    user_id = update.effective_user.id
    username = update.effective_user.username
    role = get_user_role(user_id, username)

    # Разрешаем админам и баристам
    if role not in ["barista", "admin"]:
        await update.message.reply_text("❌ Эта функция доступна только баристам")
        return

    try:
        processing_msg = await update.message.reply_text("🔍 Обрабатываю QR-код...")
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

        await update.message.delete()
        await processing_msg.delete()
        await send_temp_message(update, "✅ Найден клиент по QR-коду")
        await asyncio.sleep(0.5)
        await process_customer_scan(update, context, customer_id)

    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await update.message.reply_text(f"❌ Ошибка обработки: {str(e)}")


async def process_customer_scan(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    customer_id: int,
    show_delete_button: bool = False,
    show_erase_button: bool = False,
):
    user_id = update.effective_user.id
    role = get_user_role(user_id, update.effective_user.username)

    logger.info(
        f"📋 process_customer_scan | customer_id={customer_id} | show_delete_button={show_delete_button} | show_erase_button={show_erase_button} | state={get_user_state(context)}"
    )

    # Сбрасываем флаги для ПРЕДЫДУЩЕГО клиента
    if "user_contexts" not in context.bot_data:
        context.bot_data["user_contexts"] = {}
    if user_id not in context.bot_data["user_contexts"]:
        context.bot_data["user_contexts"][user_id] = {}

    # Удаляем старые счётчики штампов для предыдущего клиента
    for key in list(context.bot_data["user_contexts"][user_id].keys()):
        if key.startswith("stamp_counter_"):
            del context.bot_data["user_contexts"][user_id][key]
    # Удаляем все флаги stamp_used_* для предыдущего клиента
    for key in list(context.bot_data["user_contexts"][user_id].keys()):
        if key.startswith("stamp_used_"):
            del context.bot_data["user_contexts"][user_id][key]

    # Сохраняем флаги В context.user_data (а не только в context.user_data)
    context.user_data["show_delete_button"] = show_delete_button
    context.user_data["show_erase_button"] = show_erase_button

    # ДОПОЛНИТЕЛЬНО: сохраняем в bot_data для надёжности
    context.bot_data["user_contexts"][user_id]["show_delete_button"] = (
        show_delete_button
    )
    context.bot_data["user_contexts"][user_id]["show_erase_button"] = show_erase_button

    logger.info(
        f"✅ Флаги сохранены: show_delete_button={context.user_data.get('show_delete_button')}, show_erase_button={context.user_data.get('show_erase_button')}"
    )

    styles = [
        {"filled": "☕", "empty": "▫", "gift": "🎁"},
        {"filled": "☕", "empty": "🔳", "gift": "🔲"},
        {"filled": "☕", "empty": "⚪", "gift": "🟤"},
        {"filled": "🥤", "empty": "⚪", "gift": "🔴"},
        {"filled": "🧋", "empty": "🧊", "gift": "🧊"},
        {"filled": "🍜", "empty": "◾", "gift": "🈹"},
        {"filled": "🍪", "empty": "◻", "gift": "🉑"},
        {"filled": "🟣", "empty": "⚪", "gift": "⬛"},
        {"filled": "🧋", "empty": "⚪", "gift": "🟠"},
    ]

    user_saved_style_index = db.get_user_style(customer_id)
    if user_saved_style_index is not None:
        style_index = user_saved_style_index
    else:
        style_index = random.randint(0, len(styles) - 1)
        db.save_user_style(customer_id, style_index)

    context.user_data["customer_style"] = styles[style_index]
    context.user_data["customer_style_index"] = style_index

    context.bot_data["user_contexts"][user_id]["current_customer"] = customer_id
    context.user_data["current_customer"] = customer_id

    await send_or_update_customer_card(user_id, context, customer_id)

    # Устанавливаем состояние в зависимости от роли
    if role in ["barista", "admin"]:
        set_user_state(context, "barista_mode")
        logger.info(f"Режим бариста активирован для user_id={user_id}")


# ================== АДМИН - ИНЛАЙН МЕНЮ ==================
async def show_admin_main(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE = None,
    edit_mode: bool = False,
    force_new: bool = False,
):
    logger.info(f"show_admin_main вызван | force_new={force_new}")

    text = "Админ-панель\n\n"
    keyboard = [
        [InlineKeyboardButton("📒 Пользователи", callback_data="admin_users_list")],
        [InlineKeyboardButton("📙 Бариста", callback_data="admin_baristas")],
        [InlineKeyboardButton("📣 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Акции", callback_data="admin_settings")],
    ]

    # Если есть сохранённый ID сообщения и не force_new — редактируем
    admin_msg_id = context.user_data.get("admin_main_message_id")
    if admin_msg_id and not force_new:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=admin_msg_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            logger.info("Админ-панель обновлена (edit_mode=True)")
            set_user_state(context, "admin_main")
            return
        except Exception as e:
            if "Message is not modified" in str(e):
                logger.info("Сообщение уже актуально")
                set_user_state(context, "admin_main")
                return
            logger.error(f"Ошибка обновления: {e}")
            # Если не удалось обновить - удаляем старый ID и создаём новое

    # Создаём новое сообщение (при первом запуске или force_new)
    if update.callback_query:
        try:
            await update.callback_query.message.delete()
        except Exception as e:
            logger.debug(f"Не удалось удалить callback сообщение: {e}")
        msg = await update.callback_query.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif update.message:
        msg = await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        return

    context.user_data["admin_main_message_id"] = msg.message_id
    logger.info(f"Новое сообщение админ-панели создано: {msg.message_id}")

    set_user_state(context, "admin_main")


async def show_users_list_inline_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    page: int = 0,
    send_hint: bool = True,
):
    """Показывает список пользователей, заменяя сообщение админ-панели"""
    logger.info(f"show_users_list_inline_edit вызван, page={page}")

    users = db.get_all_users()
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    admin_msg_id = context.user_data.get("admin_main_message_id")

    if not users:
        text = "📂 Пользователей пока нет."
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin_main")]]
        )
        if admin_msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=admin_msg_id,
                    text=text,
                    reply_markup=keyboard,
                )
            except Exception as e:
                logger.error(f"Ошибка: {e}")
        set_user_state(context, "admin_users_list")
        return

    PER_PAGE = 20
    total_pages = (len(users) + PER_PAGE - 1) // PER_PAGE

    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1

    start_idx = page * PER_PAGE
    end_idx = min(start_idx + PER_PAGE, len(users))
    page_users = users[start_idx:end_idx]

    text = f"📖 Всего {len(users)} пользователей\n\n"

    for idx, u in enumerate(page_users, start=start_idx + 1):
        (
            user_id,
            username,
            first_name,
            last_name,
            purchases,
            phone,
            free_given,
            total_purchases,
            last_visit,
            created_at,
        ) = u

        clean_last_name = last_name if last_name and last_name != "None" else ""
        full_name = f"{first_name or ''} {clean_last_name}".strip()

        phone_part = ""
        if phone:
            phone_last4 = phone[-4:] if len(phone) >= 4 else phone
            phone_part = f"{phone_last4}"

        name_part = ""
        if full_name:
            name_part = full_name
        elif username and username != "Не указан":
            name_part = username if username.startswith("@") else f"@{username}"
        else:
            name_part = f"ID:{user_id}"

        username_part = ""
        if username and username != "Не указан":
            if not full_name or (full_name != username and full_name != f"@{username}"):
                username_part = f" | @{username}"

        progress = f"[{purchases}/{required}]"

        if phone_part:
            text += f"{phone_part} | {name_part}{username_part} | {progress}\n"
        else:
            text += f"{name_part}{username_part} | {progress}\n"

    keyboard_buttons = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("◀", callback_data=f"users_page_edit_{page - 1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton("▶", callback_data=f"users_page_edit_{page + 1}")
        )

    if nav_buttons:
        keyboard_buttons.append(nav_buttons)

    keyboard_buttons.append(
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin_main")]
    )

    keyboard = InlineKeyboardMarkup(keyboard_buttons)

    if admin_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=admin_msg_id,
                text=text,
                reply_markup=keyboard,
            )
            logger.info(f"Список пользователей, страница {page + 1}")
        except Exception as e:
            if "Message is not modified" in str(e):
                logger.info("Сообщение уже является списком пользователей")
            else:
                logger.error(f"Ошибка редактирования: {e}")
    else:
        logger.error("Не найден ID сообщения админ-панели")

    # ========== ОТПРАВЛЯЕМ ПОДСКАЗКУ ТОЛЬКО ЕСЛИ НУЖНО ==========
    if send_hint:
        # Удаляем старую подсказку если была
        old_hint = context.user_data.get("users_hint_message_id")
        if old_hint:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=old_hint
                )
            except Exception:
                pass
            context.user_data.pop("users_hint_message_id", None)

        # Отправляем новую подсказку
        hint_text = "<i>поиск отсюда добавляет возможность удаления профиля. чтобы найти отправьте 4 цифры или фото QR</i>"
        hint_msg = await update.effective_chat.send_message(
            hint_text, parse_mode="HTML"
        )
        context.user_data["users_hint_message_id"] = hint_msg.message_id
    # =============================================================

    set_user_state(context, "admin_users_list")


async def show_barista_management_inline(
    update: Update, context: ContextTypes.DEFAULT_TYPE, edit_mode: bool = False
):
    """Показывает список баристов, заменяя сообщение админ-панели"""
    logger.info(f"show_barista_management_inline вызван")

    baristas = db.get_all_baristas()
    admin_msg_id = context.user_data.get("admin_main_message_id")

    # Основное сообщение со списком баристов
    if baristas:
        text = "📜 Список барист\n\n"
        for barista in baristas:
            text += f"• @{barista[0]}\n"
        text += "\n-------------------"
    else:
        text = "📜 Список пуст\n\n-------------------"

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin_main")]]
    )

    if admin_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=admin_msg_id,
                text=text,
                reply_markup=keyboard,
            )
            logger.info(f"Сообщение заменено на список барист")
        except Exception as e:
            if "Message is not modified" in str(e):
                logger.info("Сообщение уже является списком барист")
            else:
                logger.error(f"Ошибка: {e}")
    else:
        logger.error("Не найден ID сообщения админ-панели")

    # ========== ОТПРАВЛЯЕМ ВТОРОЕ СООБЩЕНИЕ С ПОДСКАЗКОЙ ==========
    hint_text = (
        "<i>чтобы добавить отправьте @username</i>\n"
        "<i>чтобы удалить -@username (с минусом)</i>"
    )

    hint_msg = await update.effective_chat.send_message(hint_text, parse_mode="HTML")
    context.user_data["barista_hint_message_id"] = hint_msg.message_id
    # ===============================================================

    set_user_state(context, "admin_barista")


async def send_new_barista_message(update, context, text, keyboard):
    """Отправляет новое сообщение со списком баристов (только если не удалось отредактировать)"""
    if update.callback_query:
        msg = await update.callback_query.message.reply_text(
            text, reply_markup=keyboard
        )
    else:
        msg = await update.message.reply_text(text, reply_markup=keyboard)
    context.user_data["barista_list_msg_id"] = msg.message_id
    logger.info(
        f"Новое сообщение со списком баристов создано (аварийно), ID={msg.message_id}"
    )


async def handle_barista_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовый ввод для добавления/удаления баристов"""
    logger.info("handle_barista_text вызван")

    # ========== УДАЛЯЕМ ПОДСКАЗКУ ==========
    hint_msg_id = context.user_data.get("barista_hint_message_id")
    if hint_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id, message_id=hint_msg_id
            )
            context.user_data.pop("barista_hint_message_id", None)
        except Exception as e:
            logger.debug(f"Не удалось удалить подсказку: {e}")
    # =======================================

    text = update.message.text.strip()
    user_id = update.effective_user.id

    if not is_admin(user_id):
        logger.warning(f"Не админ {user_id} пытался изменить баристов")
        return

    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")

    result_text = ""

    # Удаление баристы
    if text.startswith("-"):
        username = text[1:].replace("@", "").strip()
        if username:
            if db.remove_barista(username):
                result_text = f"✅ Бариста @{username} удален!"
                logger.info(f"Бариста @{username} удален админом {user_id}")
            else:
                result_text = f"❌ Бариста @{username} не найден"
        else:
            result_text = "❌ Неверный формат. Пример: -@john_doe"

    # Добавление баристы
    elif text.startswith("@"):
        username = text[1:].strip()
        if username:
            if db.add_barista(username, "Бариста", ""):
                result_text = f"✅ Бариста @{username} добавлен!"
                logger.info(f"Бариста @{username} добавлен админом {user_id}")
            else:
                result_text = f"❌ Ошибка при добавлении @{username}"
        else:
            result_text = "❌ Неверный формат. Пример: @john_doe"
    else:
        result_text = (
            "❌ Неверный формат\n\nДля добавления: @username\nДля удаления: -@username"
        )

    # Показываем временное уведомление
    try:
        temp_msg = await update.effective_chat.send_message(result_text)
        await asyncio.sleep(2)
        await temp_msg.delete()
    except Exception as e:
        logger.debug(f"Не удалось отправить/удалить уведомление: {e}")

    # Обновляем список баристов (редактируем то же сообщение)
    await show_barista_management_inline(update, context, edit_mode=True)


async def show_admin_settings_inline(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    logger.info("show_admin_settings_inline вызван")
    promotion = db.get_promotion()
    text = f"""
⚙️ Опции

Текущая акция: {promotion[1] if promotion else "Не настроена"}
Условие: каждые {promotion[2] if promotion else 7} покупок
Описание: {promotion[3] if promotion and promotion[3] else "Нет описания"}

Выберите действие:
"""
    keyboard = [
        [InlineKeyboardButton("📝 Изменить акции", callback_data="settings_promotion")],
        [
            InlineKeyboardButton(
                "🔙 Назад", callback_data="back_to_admin_main_from_settings"
            )
        ],
    ]

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    set_user_state(context, "admin_settings")


async def show_promotion_management_inline(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    logger.info("show_promotion_management_inline вызван")
    promotion = db.get_promotion()
    text = f"""
📝 Управление акциями

Текущая акция: {promotion[1] if promotion else "Не настроена"}
Условие: каждые {promotion[2] if promotion else 7} покупок
Описание: {promotion[3] if promotion and promotion[3] else "Нет описания"}

Выберите что изменить:
"""
    keyboard = [
        [InlineKeyboardButton("📝 Название", callback_data="promotion_name")],
        [InlineKeyboardButton("7️⃣ Условие", callback_data="promotion_condition")],
        [InlineKeyboardButton("📖 Описание", callback_data="promotion_description")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin_settings")],
    ]

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    set_user_state(context, "promotion_management")


async def show_barista_list_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("show_barista_list_inline вызван")
    baristas = db.get_all_baristas()
    text = "📜 Список бариста\n\n"
    if baristas:
        for barista in baristas:
            text += f"• @{barista[0]}\n"
    else:
        text += "Бариста не добавлены"

    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_barista_menu")]
    ]

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_users_list_inline(
    update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0
):
    logger.info(f"show_users_list_inline вызван, page={page}")
    users = db.get_all_users()
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    if not users:
        text = "📂 Пользователей пока нет."
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_users_menu")]
        ]
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    PER_PAGE = 20
    total_pages = (len(users) + PER_PAGE - 1) // PER_PAGE

    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1

    start_idx = page * PER_PAGE
    end_idx = min(start_idx + PER_PAGE, len(users))
    page_users = users[start_idx:end_idx]

    text = (
        f"📖 Страница {page + 1}/{total_pages} | Всего: {len(users)} пользователей\n\n"
    )

    for idx, u in enumerate(page_users, start=start_idx + 1):
        (
            user_id,
            username,
            first_name,
            last_name,
            purchases,
            phone,
            free_given,
            total_purchases,
            last_visit,
            created_at,
        ) = u

        user_parts = []
        clean_last_name = last_name if last_name and last_name != "None" else ""
        full_name = f"{first_name or ''} {clean_last_name}".strip()
        if full_name:
            user_parts.append(full_name)
        if username and username != "Не указан":
            user_parts.append(f"@{username}")
        if phone:
            masked_phone = f"---{phone[-4:]}" if len(phone) >= 4 else "---"
            user_parts.append(masked_phone)
        if not user_parts:
            user_parts.append(f"ID:{user_id}")

        user_str = " • ".join(user_parts)

        if purchases >= required:
            progress = f"{purchases}/{required} 🎉"
        elif purchases == required - 1:
            progress = f"{purchases}/{required} ⭐"
        else:
            progress = f"{purchases}/{required}"

        text += f"{idx}. 👤 {user_str} — {progress}\n"

    keyboard = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("◀", callback_data=f"users_page_{page - 1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton("▶", callback_data=f"users_page_{page + 1}")
        )

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append(
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_users_menu")]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

    set_user_state(context, "admin_users_list")


async def show_customer_card_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: int
):
    logger.info(f"show_customer_card_admin вызван для customer_id={customer_id}")

    # Удаляем подсказку пользователей
    hint_msg_id = context.user_data.get("users_hint_message_id")
    if hint_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id, message_id=hint_msg_id
            )
            context.user_data.pop("users_hint_message_id", None)
        except Exception as e:
            logger.debug(f"Не удалось удалить подсказку: {e}")

    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT username, first_name, last_name, phone, purchases_count FROM users WHERE user_id = ?",
        (customer_id,),
    )
    user_info = cursor.fetchone()

    if not user_info:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ Пользователь не найден")
        else:
            await update.message.reply_text("❌ Пользователь не найден")
        return

    username, first_name, last_name, phone, purchases = user_info

    # ========== ФОРМАТ: одна строка ==========
    info_parts = []

    # Имя
    clean_last_name = last_name if last_name and last_name != "None" else ""
    full_name = f"{first_name or ''} {clean_last_name}".strip()
    if full_name:
        info_parts.append(f"👤 {full_name}")

    # Username
    if username and username != "Не указан":
        info_parts.append(f"▪️ @{username}")

    # Телефон
    if phone:
        info_parts.append(f"{phone}")

    # ID
    info_parts.append(f"🆔 {customer_id}")

    user_display = " | ".join(info_parts)
    # =========================================

    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    style_index = db.get_user_style(customer_id)
    all_styles = [
        {"filled": "☕", "empty": "▫", "gift": "🎁"},
        {"filled": "☕", "empty": "🔳", "gift": "🔲"},
        {"filled": "☕", "empty": "⚪", "gift": "🟤"},
        {"filled": "🥤", "empty": "⚪", "gift": "🔴"},
        {"filled": "🧋", "empty": "🧊", "gift": "🧊"},
        {"filled": "🍜", "empty": "◾", "gift": "🈹"},
        {"filled": "🍪", "empty": "◻", "gift": "🉑"},
        {"filled": "🟣", "empty": "⚪", "gift": "⬛"},
        {"filled": "🧋", "empty": "⚪", "gift": "🟠"},
    ]
    style = all_styles[style_index] if style_index is not None else all_styles[0]

    progress_bar = get_coffee_progress(purchases, required, style)

    text = f"""{user_display}

{progress_bar}
{purchases}/{required}

Выберите действие:"""

    inline_keyboard = [
        [
            InlineKeyboardButton(
                "➕ Начислить", callback_data=f"admin_add_{customer_id}"
            ),
            InlineKeyboardButton(
                "➖ Отменить", callback_data=f"admin_remove_{customer_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "🗑️ Удалить пользователя", callback_data=f"admin_delete_{customer_id}"
            )
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_users_menu")],
    ]

    context.user_data["current_customer"] = customer_id

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(inline_keyboard)
        )
    else:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(inline_keyboard)
        )


# ================== ОБРАБОТКА CALLBACK QUERIES ==================


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка инлайн-колбэков админа"""
    query = update.callback_query
    data = query.data
    logger.info(f"🔵 handle_admin_callback: data={data}")
    await query.answer()

    # ========== УДАЛЯЕМ ПОДСКАЗКУ ПРИ ЛЮБОМ ДЕЙСТВИИ (КРОМЕ ВОЗВРАТА В ГЛАВНОЕ МЕНЮ) ==========
    if data != "back_to_admin_main":
        await delete_hint_message(context, update.effective_chat.id)
    # =====================================================================================

    # ГЛАВНОЕ МЕНЮ
    if data == "admin_users_list":
        await show_users_list_inline_edit(update, context, 0, send_hint=True)
        return
    elif data == "admin_baristas":
        await show_barista_management_inline(update, context, edit_mode=False)
        return

    elif data == "admin_broadcast":
        set_user_state(context, "broadcast_waiting_input")

        # Редактируем ЕДИНСТВЕННОЕ сообщение админ-панели
        admin_msg_id = context.user_data.get("admin_main_message_id")
        if admin_msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=admin_msg_id,
                    text="✍ Введите текст для рассылки:",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🔙 Назад",
                                    callback_data="back_to_admin_main_from_broadcast",
                                )
                            ]
                        ]
                    ),
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования админ-панели: {e}")

        # Отправляем новое сообщение №2 с подсказкой
        info_text = """!c <i>- только клиентам</i>
!b <i>- только баристам</i>
без префикса <i>- всем пользователям</i>"""

        info_msg = await update.effective_chat.send_message(
            info_text, parse_mode="HTML"
        )
        context.user_data["broadcast_info_msg_id"] = info_msg.message_id

        return
    elif data == "admin_settings":
        await show_admin_settings_inline(update, context)
        return

    elif data == "back_to_admin_main":
        # Сбрасываем флаг удаления
        context.user_data.pop("show_delete_button", None)

        # Удаляем подсказку баристов
        hint_msg_id = context.user_data.get("barista_hint_message_id")
        if hint_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=hint_msg_id
                )
                context.user_data.pop("barista_hint_message_id", None)
            except Exception as e:
                logger.debug(f"Не удалось удалить подсказку баристов: {e}")

        # Удаляем подсказку пользователей
        users_hint_msg_id = context.user_data.get("users_hint_message_id")
        if users_hint_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=users_hint_msg_id
                )
                context.user_data.pop("users_hint_message_id", None)
            except Exception as e:
                logger.debug(f"Не удалось удалить подсказку пользователей: {e}")

        await show_admin_main(update, context, edit_mode=True)

        # ========== ВОССТАНАВЛИВАЕМ ПОДСКАЗКУ ==========
        await send_hint_message(context, update.effective_chat.id, "admin")
        # ===============================================
        return

    elif data == "back_to_admin_main_from_broadcast":
        # Удаляем сообщение №2 (подсказку)
        info_msg_id = context.user_data.get("broadcast_info_msg_id")
        if info_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=info_msg_id
                )
            except Exception:
                pass
        context.user_data.pop("broadcast_info_msg_id", None)
        # Восстанавливаем админ-панель
        await show_admin_main(update, context, force_new=True)
        return
    elif data == "back_to_admin_main_from_settings":
        await show_admin_main(update, context, edit_mode=True)
        return
    elif data == "back_to_admin_settings":
        await show_admin_settings_inline(update, context)
        return
    elif data == "back_to_users_menu":
        # Возвращаемся к списку пользователей с новой подсказкой
        await show_users_list_inline_edit(update, context, 0, send_hint=False)
        return
    elif data == "back_to_users_menu_from_card":
        user_id = update.effective_user.id

        # Удаляем сообщение с карточкой
        if (
            "user_contexts" in context.bot_data
            and user_id in context.bot_data["user_contexts"]
        ):
            card_msg_id = context.bot_data["user_contexts"][user_id].get(
                "card_message_id"
            )
            if card_msg_id:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id, message_id=card_msg_id
                    )
                except Exception as e:
                    logger.debug(f"Не удалось удалить карточку: {e}")

            # Очищаем данные
            context.bot_data["user_contexts"][user_id].pop("card_message_id", None)
            context.bot_data["user_contexts"][user_id].pop("current_customer", None)

        # Возвращаемся к списку пользователей БЕЗ подсказки
        await show_users_list_inline_edit(update, context, 0, send_hint=False)

        return

    # ПОИСК ПОЛЬЗОВАТЕЛЯ
    elif data == "users_search":
        set_user_state(context, "finding_customer")
        await query.edit_message_text(
            "🔍 Введите для поиска:\n\n"
            "• Номер телефона (10 цифр)\n"
            "• Последние 4 цифры номера\n"
            "• @username пользователя\n\n"
            "Примеры:\n9996664422\n4422\n@username",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin_main")]]
            ),
        )
        return

    # ПАГИНАЦИЯ
    elif data.startswith("users_page_edit_"):
        page = int(data.replace("users_page_edit_", ""))
        await show_users_list_inline_edit(update, context, page, send_hint=False)
        return

    # УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЕМ
    elif data.startswith("admin_add_"):
        customer_id = int(data.replace("admin_add_", ""))
        db.update_user_purchases(customer_id, 1)
        await show_customer_card_admin(update, context, customer_id)
        return
    elif data.startswith("admin_remove_"):
        customer_id = int(data.replace("admin_remove_", ""))
        db.update_user_purchases(customer_id, -1)
        await show_customer_card_admin(update, context, customer_id)
        return
    elif data.startswith("admin_delete_"):
        customer_id = int(data.replace("admin_delete_", ""))
        await handle_delete_user_admin(update, context, customer_id)
        return

    # ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ
    elif data.startswith("confirm_delete_"):
        customer_id = int(data.replace("confirm_delete_", ""))
        if db.delete_user(customer_id):
            # ========== ИСПРАВЛЕНИЕ: удаляем сообщение с подтверждением ==========
            try:
                # Редактируем сообщение, показывая что удаление выполнено
                await query.edit_message_text("✅ Пользователь удалён")
                # Ждём 2 секунды и удаляем это сообщение
                await asyncio.sleep(2)
                await query.message.delete()
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение подтверждения: {e}")
            # ===================================================================

            # Возвращаемся к списку пользователей БЕЗ подсказки
            await show_users_list_inline_edit(update, context, 0, send_hint=False)
        else:
            await query.edit_message_text("❌ Ошибка при удалении")
            await asyncio.sleep(2)
            try:
                await query.message.delete()
            except Exception:
                pass
        return
    elif data.startswith("cancel_delete_"):
        customer_id = int(data.replace("cancel_delete_", ""))
        # Возвращаемся к карточке пользователя
        await show_customer_card_admin(update, context, customer_id)
        return

    # УПРАВЛЕНИЕ АКЦИЯМИ
    elif data == "settings_promotion":
        await show_promotion_management_inline(update, context)
        return
    elif data == "promotion_name":
        set_user_state(context, "changing_promotion_name")
        await query.edit_message_text(
            "📝 Введите новое название акции:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Назад", callback_data="back_to_admin_settings"
                        )
                    ]
                ]
            ),
        )
        return
    elif data == "promotion_condition":
        set_user_state(context, "changing_promotion_condition")
        await query.edit_message_text(
            "7️⃣ Введите новое количество покупок для акции (например: 7):",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Назад", callback_data="back_to_admin_settings"
                        )
                    ]
                ]
            ),
        )
        return
    elif data == "promotion_description":
        set_user_state(context, "changing_promotion_description")
        await query.edit_message_text(
            "📖 Введите новое описание акции:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Назад", callback_data="back_to_admin_settings"
                        )
                    ]
                ]
            ),
        )
        return

    # Обработка начала отзыва


async def handle_delete_user_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: int
):
    logger.info(f"handle_delete_user_admin для customer_id={customer_id}")
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT username, first_name, last_name FROM users WHERE user_id = ?",
        (customer_id,),
    )
    user_info = cursor.fetchone()

    if not user_info:
        await update.callback_query.edit_message_text("❌ Пользователь не найден")
        return

    username, first_name, last_name = user_info
    clean_last_name = last_name if last_name and last_name != "None" else ""
    full_name = f"{first_name or ''} {clean_last_name}".strip()
    if not full_name:
        full_name = (
            f"@{username}"
            if username and username != "Не указан"
            else f"Пользователь {customer_id}"
        )

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Да, удалить", callback_data=f"confirm_delete_{customer_id}"
            ),
            InlineKeyboardButton(
                "❌ Нет, отменить", callback_data=f"cancel_delete_{customer_id}"
            ),
        ],
    ]

    await update.callback_query.edit_message_text(
        f"⚠️ Вы уверены, что хотите удалить пользователя?\n\n{full_name}\nID: {customer_id}\n\nЭто действие нельзя отменить!",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ================== ФУНКЦИИ ДЛЯ РАССЫЛКИ ==================
async def send_broadcast_to_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    broadcast_text = context.user_data.get("broadcast_text", "")
    broadcast_photo = context.user_data.get("broadcast_photo")
    target_audience = context.user_data.get("broadcast_target", "all")
    target_display = context.user_data.get(
        "broadcast_target_display", "всем пользователям"
    )

    # Просто отвечаем на callback, чтобы убрать "часики"
    await query.answer()

    # Отправляем новое сообщение о начале рассылки
    await query.message.reply_text(
        f"🔄 Отправка рассылки...\n\n🎯 Аудитория: {target_display}"
    )

    all_user_ids = db.get_all_user_ids()
    sent_count = 0
    sent_messages = []

    for customer_id in all_user_ids:
        cursor = db.conn.cursor()
        cursor.execute("SELECT username FROM users WHERE user_id = ?", (customer_id,))
        user_info = cursor.fetchone()
        username = user_info[0] if user_info else None
        user_role = get_user_role(customer_id, username)

        if target_audience == "baristas" and user_role != "barista":
            continue
        elif target_audience == "clients" and user_role != "client":
            continue

        try:
            if broadcast_photo:
                sent_msg = await context.bot.send_photo(
                    chat_id=customer_id,
                    photo=broadcast_photo,
                    caption=broadcast_text if broadcast_text else None,
                )
            else:
                sent_msg = await context.bot.send_message(
                    chat_id=customer_id, text=broadcast_text
                )
            sent_count += 1
            sent_messages.append((customer_id, sent_msg.message_id))
        except Exception as e:
            logger.error(f"Не удалось отправить {customer_id}: {e}")
        await asyncio.sleep(0.1)

    result_text = f"✅ Рассылка отправлена!\n\n🎯 Аудитория: {target_display}\n📤 Отправлено: {sent_count}"

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🗑️ Удалить у всех", callback_data="broadcast_delete")]]
    )

    await query.message.reply_text(result_text, reply_markup=keyboard)

    context.user_data["last_broadcast"] = {
        "messages": sent_messages,
        "text": broadcast_text,
        "photo": broadcast_photo,
        "target": target_audience,
    }

    # Очистка
    context.user_data.pop("broadcast_target", None)
    context.user_data.pop("broadcast_target_display", None)
    context.user_data.pop("broadcast_text", None)
    context.user_data.pop("broadcast_photo", None)
    context.user_data.pop("broadcast_info_msg_id", None)

    set_user_state(context, "main")


async def delete_broadcast_from_users(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    broadcast_data = context.user_data.get("last_broadcast")
    if not broadcast_data:
        await query.edit_message_text("❌ Нет данных о последней рассылке")
        return

    await query.edit_message_text("🔄 Удаление сообщений у пользователей...")

    deleted_count = 0
    for user_id, message_id in broadcast_data["messages"]:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=message_id)
            deleted_count += 1
        except Exception as e:
            logger.error(f"Не удалось удалить у {user_id}: {e}")
        await asyncio.sleep(0.1)

    await query.edit_message_text(f"🗑️ Удалено {deleted_count} сообщений рассылки")
    context.user_data.pop("last_broadcast", None)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех остальных callback запросов"""
    query = update.callback_query
    data = query.data
    logger.info(f"🟢 handle_callback_query: data={data}")
    await query.answer()

    # ========== НОВЫЙ ОБРАБОТЧИК: ПОДСКАЗКА ПО НОМЕРУ ==========
    if data == "show_phone_hint":
        await query.answer()  # Убираем "часики"
        await query.edit_message_text(
            "📞 <b>Как привязать или изменить номер телефона</b>\n\n"
            "Просто отправьте в чат 10 цифр вашего номера без 7/8.\n\n"
            "<b>Примеры:</b>\n"
            "• <code>9992221122</code> — только номер (имя из Telegram)\n"
            "• <code>9992221133 Алексей</code> — номер и имя\n\n"
            "<i>Номер появится в вашей карточке и у баристов при поиске</i>",
            parse_mode="HTML",
        )
        return
    # ===========================================================
    # ========== ОБРАБОТКА КНОПОК РАССЫЛКИ ==========
    if data == "broadcast_send":
        logger.info("📢 Обработка broadcast_send")
        await send_broadcast_to_users(update, context)
        return

    if data == "broadcast_cancel":
        logger.info("❌ Обработка broadcast_cancel")

        # РЕДАКТИРУЕМ сообщение №2 в "Отменено"
        try:
            await query.edit_message_text("❌ Рассылка отменена", reply_markup=None)
        except Exception as e:
            logger.debug(f"Не удалось отредактировать сообщение: {e}")

        # Очищаем данные рассылки
        context.user_data.pop("broadcast_target", None)
        context.user_data.pop("broadcast_target_display", None)
        context.user_data.pop("broadcast_text", None)
        context.user_data.pop("broadcast_info_msg_id", None)

        # Сбрасываем состояние
        set_user_state(context, "main")

        # Восстанавливаем админ-панель (сообщение №1)
        await show_admin_main(update, context, force_new=True)
        return
    # ========== УДАЛЕНИЕ РАССЫЛКИ ==========
    if data == "broadcast_delete":
        logger.info("🗑️ Обработка broadcast_delete")
        await delete_broadcast_from_users(update, context)
        return
    # ========================================
    # ========== ОТЗЫВЫ ==========
    # Обработка первого нажатия "Оставить отзыв" - показываем ссылки и запоминаем
    if data.startswith("start_review_"):
        logger.info(f"📝 Обработка start_review_: {data}")
        user_id = int(data.replace("start_review_", ""))
        if update.effective_user.id != user_id:
            await query.answer("❌ Это не ваш запрос", show_alert=True)
            return

        # Запоминаем, что пользователь нажал "Оставить отзыв"
        if "user_contexts" not in context.bot_data:
            context.bot_data["user_contexts"] = {}
        if user_id not in context.bot_data["user_contexts"]:
            context.bot_data["user_contexts"][user_id] = {}
        context.bot_data["user_contexts"][user_id]["review_clicked"] = True
        logger.info(f"✅ Запомнили нажатие на отзыв для user_id={user_id}")

        # Создаём кнопки-ссылки
        YANDEX_URL = "https://yandex.ru/maps/org/coffeerina/146032988967/reviews/?ll=132.354037%2C43.110843&tab=reviews&z=16.75"
        GIS_URL = "https://2gis.ru/bolshoj-kamen/firm/70000001105333719"

        keyboard_buttons = [
            [
                InlineKeyboardButton("📍 Яндекс.Карты", url=YANDEX_URL),
                InlineKeyboardButton("📍 2ГИС", url=GIS_URL),
            ]
        ]
        keyboard = InlineKeyboardMarkup(keyboard_buttons)

        await query.edit_message_text(
            "💫 <b>Как впечатления?</b>\n\n<i>Платформы для отзывов</i>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    # Обработка нажатия "Не показывать"
    if data.startswith("never_show_review_"):
        logger.info(f"🚫 Обработка never_show_review_: {data}")
        user_id = int(data.replace("never_show_review_", ""))
        if update.effective_user.id != user_id:
            await query.answer("❌ Это не ваш запрос", show_alert=True)
            return

        # Устанавливаем флаг, что больше не показываем
        if "user_contexts" not in context.bot_data:
            context.bot_data["user_contexts"] = {}
        if user_id not in context.bot_data["user_contexts"]:
            context.bot_data["user_contexts"][user_id] = {}
        context.bot_data["user_contexts"][user_id]["never_show_review"] = True
        logger.info(
            f"✅ Пользователь {user_id} отключил уведомления об отзывах навсегда"
        )

        await query.edit_message_text(
            "✅ <i>Уведомления об отзывах больше не будут вас беспокоить.</i>\n\nДо скорого!",
            parse_mode="HTML",
        )
        return
    # Обработка клика по Яндекс.Картам
    if data.startswith("review_click_yandex_"):
        user_id = int(data.replace("review_click_yandex_", ""))
        if update.effective_user.id != user_id:
            await query.answer("❌ Это не ваш запрос", show_alert=True)
            return

        # Сохраняем в БД факт клика
        db.save_review_click(user_id, "yandex")

        # Показываем уведомление о благодарности
        await query.answer("🙏 Спасибо за отзыв на Яндекс.Картах!", show_alert=True)

        # Если нажаты обе кнопки, больше не показываем запрос
        if db.has_user_completed_all_reviews(user_id):
            await query.edit_message_text(
                "✅ <i>Спасибо за ваши отзывы! Мы стали лучше благодаря вам.</i>\n\nДо скорой встречи!",
                parse_mode="HTML",
            )
        else:
            # Просто закрываем сообщение
            try:
                await query.message.delete()
            except Exception:
                pass
        return

    # Обработка клика по 2ГИС
    if data.startswith("review_click_gis_"):
        user_id = int(data.replace("review_click_gis_", ""))
        if update.effective_user.id != user_id:
            await query.answer("❌ Это не ваш запрос", show_alert=True)
            return

        # Сохраняем в БД факт клика
        db.save_review_click(user_id, "gis")

        # Показываем уведомление о благодарности
        await query.answer("🙏 Спасибо за отзыв в 2ГИС!", show_alert=True)

        # Если нажаты обе кнопки, больше не показываем запрос
        if db.has_user_completed_all_reviews(user_id):
            await query.edit_message_text(
                "✅ <i>Спасибо за ваши отзывы! Мы стали лучше благодаря вам.</i>\n\nДо скорой встречи!",
                parse_mode="HTML",
            )
        else:
            # Просто закрываем сообщение
            try:
                await query.message.delete()
            except Exception:
                pass
        return

    # ========== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ==========

    # Штамп (начисление)
    if data.startswith("stamp_"):
        await handle_stamp(update, context)
        return

    # Стереть (отмена)
    if data.startswith("erase_"):
        await handle_erase(update, context)
        return

    # Приступаю
    if data.startswith("accept_order_"):
        await handle_start_order(update, context)
        return

    # Готово
    if data.startswith("finish_order_"):
        await handle_finish_order(update, context)
        return

    # Стили прогресс-бара
    if data.startswith("style_"):
        parts = data.split("_")
        if len(parts) >= 3:
            action = parts[1]
            user_id = int(parts[2])
            current_style_index = db.get_user_style(user_id)

            all_styles = [
                {"filled": "☕", "empty": "▫", "gift": "🎁"},
                {"filled": "☕", "empty": "🔳", "gift": "🔲"},
                {"filled": "☕", "empty": "⚪", "gift": "🟤"},
                {"filled": "🥤", "empty": "⚪", "gift": "🔴"},
                {"filled": "🧋", "empty": "🧊", "gift": "🧊"},
                {"filled": "🍜", "empty": "◾", "gift": "🈹"},
                {"filled": "🍪", "empty": "◻", "gift": "🉑"},
                {"filled": "🟣", "empty": "⚪", "gift": "⬛"},
                {"filled": "🧋", "empty": "⚪", "gift": "🟠"},
            ]

            if action == "prev":
                new_style_index = (current_style_index - 1) % len(all_styles)
            elif action == "next":
                new_style_index = (current_style_index + 1) % len(all_styles)
            else:
                return

            db.save_user_style(user_id, new_style_index)
            await show_progress_with_choice(
                update, context, user_id, from_promotion=False
            )
        return

    # Привязка номера
    if data.startswith("bind_phone_"):
        user_id = int(data.replace("bind_phone_", ""))
        set_user_state(context, "setting_phone_from_callback")
        context.user_data["phone_user_id"] = user_id
        await query.message.reply_text(
            "🖇 Введите ваш номер телефона без 7/8 и имя через пробел\n\n"
            "Пример:\n9996664422 Саша\n\n"
            "Или нажмите /start для отмены"
        )
        return

    # Статистика клиента
    if data.startswith("client_stats_"):
        await show_promotion_info_with_context(update, context)
        return

    if data == "noop":
        return

    logger.warning(f"⚠️ Необработанный callback: {data}")


# ================== РАССЫЛКА ==================
async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user_state(context) != "broadcast_waiting_input":
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Доступ запрещён")
        set_user_state(context, "main")
        await show_admin_main(update, context)
        return

    # Получаем текст (caption для фото или просто текст)
    text = update.message.caption or update.message.text or ""

    # Проверяем наличие фото
    photo_file_id = None
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id

    if not text and not photo_file_id:
        await update.message.reply_text(
            "❌ Введите текст или отправьте фото с подписью"
        )
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    # Определяем аудиторию по префиксу
    # Определяем аудиторию по префиксу (из подписи к фото или из текста)
    target_audience = "all"
    broadcast_text = text
    target_display = "всем пользователям"

    # Проверяем префикс в тексте (для фото — это caption)
    if text.startswith("!c "):
        target_audience = "clients"
        broadcast_text = text[3:].strip()
        target_display = "только клиентам"
    elif text.startswith("!b "):
        target_audience = "baristas"
        broadcast_text = text[3:].strip()
        target_display = "только баристам"
    # Также проверяем префикс в caption (для фото без подписи префикс не сработает, это нормально)

    # Сохраняем в user_data
    context.user_data["broadcast_target"] = target_audience
    context.user_data["broadcast_target_display"] = target_display
    context.user_data["broadcast_text"] = broadcast_text
    context.user_data["broadcast_photo"] = photo_file_id

    # Редактируем админ-панель
    admin_msg_id = context.user_data.get("admin_main_message_id")
    if admin_msg_id:
        try:
            preview_text = f"📣 Предпросмотр ({target_display}):"
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=admin_msg_id,
                text=preview_text,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 Назад",
                                callback_data="back_to_admin_main_from_broadcast",
                            )
                        ]
                    ]
                ),
            )
        except Exception as e:
            logger.error(f"Ошибка: {e}")

    # Отправляем предпросмотр в сообщении №2
    info_msg_id = context.user_data.get("broadcast_info_msg_id")
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Отправить", callback_data="broadcast_send"),
                InlineKeyboardButton("❌ Отменить", callback_data="broadcast_cancel"),
            ]
        ]
    )

    if info_msg_id:
        try:
            if photo_file_id:
                await context.bot.edit_message_caption(
                    chat_id=update.effective_chat.id,
                    message_id=info_msg_id,
                    caption=broadcast_text or None,
                    reply_markup=keyboard,
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=info_msg_id,
                    text=broadcast_text,
                    reply_markup=keyboard,
                )
        except Exception as e:
            logger.error(f"Ошибка редактирования: {e}")
            # Если не удалось отредактировать — создаём новое
            if photo_file_id:
                new_msg = await update.effective_chat.send_photo(
                    photo=photo_file_id,
                    caption=broadcast_text or None,
                    reply_markup=keyboard,
                )
            else:
                new_msg = await update.effective_chat.send_message(
                    text=broadcast_text, reply_markup=keyboard
                )
            context.user_data["broadcast_info_msg_id"] = new_msg.message_id
    else:
        # Если нет info_msg_id, создаём новое
        if photo_file_id:
            msg = await update.effective_chat.send_photo(
                photo=photo_file_id,
                caption=broadcast_text or None,
                reply_markup=keyboard,
            )
        else:
            msg = await update.effective_chat.send_message(
                text=broadcast_text, reply_markup=keyboard
            )
        context.user_data["broadcast_info_msg_id"] = msg.message_id

    try:
        await update.message.delete()
    except Exception:
        pass

    set_user_state(context, "broadcast_preview")


async def handle_broadcast_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return

    if data == "broadcast_send":
        await send_broadcast_to_users(update, context)
    elif data == "broadcast_cancel":
        # Удаляем сообщение №2 (подсказку/текст)
        info_msg_id = context.user_data.get("broadcast_info_msg_id")
        if info_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=info_msg_id
                )
            except Exception:
                pass

        # Очищаем данные рассылки
        context.user_data.pop("broadcast_target", None)
        context.user_data.pop("broadcast_target_display", None)
        context.user_data.pop("broadcast_text", None)
        context.user_data.pop("broadcast_info_msg_id", None)

        # Сбрасываем состояние
        set_user_state(context, "main")

        # Восстанавливаем админ-панель
        await show_admin_main(update, context, force_new=True)


# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
async def send_qr_code(update: Update, user_id: int, with_buttons: bool = True):
    qr_image = generate_qr_code(user_id)
    caption = "◾️ Покажите QR-код баристе при заказе"

    if with_buttons:
        keyboard = [
            [
                InlineKeyboardButton(
                    "🪪 Прогресс-бар", callback_data=f"client_stats_{user_id}"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_photo(
            photo=qr_image, caption=caption, reply_markup=reply_markup
        )
    else:
        await update.message.reply_photo(photo=qr_image, caption=caption)


async def show_progress_with_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    from_promotion=False,
):
    if update.callback_query and not from_promotion:
        query = update.callback_query
        chat_id = query.message.chat_id
        edit_method = query.edit_message_text
        send_new = False
    else:
        if update.callback_query:
            chat_id = update.callback_query.message.chat_id
        elif update.message:
            chat_id = update.message.chat_id
        else:
            logger.error("Нет сообщения или callback для ответа")
            return
        edit_method = None
        send_new = True

    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT purchases_count, first_name, last_name, phone, username FROM users WHERE user_id = ?",
        (user_id,),
    )
    user_info = cursor.fetchone()

    if not user_info:
        logger.error(f"Пользователь {user_id} не найден")
        return

    purchases, first_name, last_name, phone, username = user_info

    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    all_styles = [
        {"filled": "☕", "empty": "▫", "gift": "🎁"},
        {"filled": "☕", "empty": "🔳", "gift": "🔲"},
        {"filled": "☕", "empty": "⚪", "gift": "🟤"},
        {"filled": "🥤", "empty": "⚪", "gift": "🔴"},
        {"filled": "🧋", "empty": "🧊", "gift": "🧊"},
        {"filled": "🍜", "empty": "◾", "gift": "🈹"},
        {"filled": "🍪", "empty": "◻", "gift": "🉑"},
        {"filled": "🟣", "empty": "⚪", "gift": "⬛"},
        {"filled": "🧋", "empty": "⚪", "gift": "🟠"},
    ]

    style_index = db.get_user_style(user_id)
    style = all_styles[style_index]
    progress_bar = get_coffee_progress(purchases, required, style)

    # ========== ИСПРАВЛЕНИЕ: убираем эмодзи ==========
    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = f"@{username}" if username else "Гость"

    info_parts = [user_display_name]  # без эмодзи
    if phone:
        info_parts.append(f"{phone}")

    header_line = " | ".join(info_parts)
    # ================================================

    if purchases >= required:
        status_line = "🎉 Бесплатный напиток доступен!"
    else:
        remaining = required - purchases - 1
        if remaining == 0:
            status_line = "Следующий 🎁"
        else:
            status_line = f"{remaining}"

    text = f"{header_line}\n\n{progress_bar}\n\n{status_line}"

    keyboard_buttons = [
        [
            InlineKeyboardButton("<", callback_data=f"style_prev_{user_id}"),
            InlineKeyboardButton(
                f"{style_index + 1}/{len(all_styles)}", callback_data="noop"
            ),
            InlineKeyboardButton(">", callback_data=f"style_next_{user_id}"),
        ],
        [
            InlineKeyboardButton(
                "📞 Изменить номер" if phone else "📞 Привязать номер",
                callback_data="show_phone_hint",  # <-- ИЗМЕНЕНО: просто показываем подсказку
            )
        ],
    ]
    # =======================================
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    try:
        if not send_new and edit_method:
            await edit_method(text, reply_markup=reply_markup)
        else:
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка при показе прогресс-бара: {e}")


async def show_promotion_info_with_context(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    user_id = user.id

    if update.message:
        chat_id = update.message.chat_id
        reply_method = update.message.reply_text
    elif update.callback_query:
        query = update.callback_query
        chat_id = query.message.chat_id
        reply_method = query.message.reply_text
        await query.answer()
    else:
        logger.error("Не могу определить источник вызова")
        return

    promotion = db.get_promotion()
    promotion_text = (
        f"🎁 {promotion[1]}\n\n{promotion[3] if promotion and promotion[3] else 'Покажите QR-код при каждой покупке'}"
        if promotion
        else "Акция ещё не настроена"
    )

    try:
        promotion_msg = await reply_method(promotion_text)
        message_id = promotion_msg.message_id
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        try:
            promotion_msg = await context.bot.send_message(chat_id, promotion_text)
            message_id = promotion_msg.message_id
        except Exception as e2:
            logger.error(f"Ошибка при прямом отправлении: {e2}")
            return

    await asyncio.sleep(2)
    await show_progress_with_choice(update, context, user_id, from_promotion=True)

    async def delete_promotion_message():
        await asyncio.sleep(5)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    asyncio.create_task(delete_promotion_message())


async def send_or_update_customer_card(
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    customer_id: int,
    message_id: int = None,
    stamp_status: int = None,  # сколько штампов за эту сессию (положительные) или крестиков (отрицательные)
):
    logger.info(
        f"📇 send_or_update_customer_card | user_id={user_id} | customer_id={customer_id} | message_id={message_id} | stamp_status={stamp_status}"
    )

    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT username, first_name, last_name, phone FROM users WHERE user_id = ?",
        (customer_id,),
    )
    user_info = cursor.fetchone()

    if not user_info:
        if message_id:
            await context.bot.edit_message_text(
                chat_id=user_id, message_id=message_id, text="❌ Клиент не найден"
            )
        else:
            await context.bot.send_message(chat_id=user_id, text="❌ Клиент не найден")
        return

    customer_username, first_name, last_name, phone = user_info

    user_emoji = (
        "▪️"
        if customer_username
        and customer_username != "Не указан"
        and customer_username != "None"
        else "▫️"
    )

    clean_last_name = last_name if last_name and last_name != "None" else ""
    user_display_name = f"{first_name} {clean_last_name}".strip()
    if not user_display_name:
        user_display_name = (
            f"@{customer_username}"
            if customer_username and customer_username != "Не указан"
            else "Гость"
        )

    info_parts = [f"{user_emoji} {user_display_name}"]
    if phone:
        info_parts.append(f"{phone}")

    header_line = " | ".join(info_parts)

    purchases = db.get_user_stats(customer_id)
    promotion = db.get_promotion()
    required = promotion[2] if promotion else 7

    user_saved_style_index = db.get_user_style(customer_id)
    all_styles = [
        {"filled": "☕", "empty": "▫", "gift": "🎁"},
        {"filled": "☕", "empty": "🔳", "gift": "🔲"},
        {"filled": "☕", "empty": "⚪", "gift": "🟤"},
        {"filled": "🥤", "empty": "⚪", "gift": "🔴"},
        {"filled": "🧋", "empty": "🧊", "gift": "🧊"},
        {"filled": "🍜", "empty": "◾", "gift": "🈹"},
        {"filled": "🍪", "empty": "◻", "gift": "🉑"},
        {"filled": "🟣", "empty": "⚪", "gift": "⬛"},
        {"filled": "🧋", "empty": "⚪", "gift": "🟠"},
    ]

    saved_style = (
        all_styles[user_saved_style_index]
        if user_saved_style_index is not None
        else all_styles[0]
    )
    progress_bar = get_coffee_progress(purchases, required, saved_style)

    # Формируем строку статуса
    status_text = ""

    # Логика для штампов (✅) и крестиков (❌)
    if stamp_status is not None and stamp_status > 0:
        status_text = "✅" * stamp_status + " Stamped"
    elif stamp_status is not None and stamp_status < 0:
        status_text = "❌" * abs(stamp_status) + " Erased"
    else:
        # stamp_status == 0 или None - показываем обычный остаток
        if purchases >= required:
            status_text = "🎉 Бесплатный напиток!"
        else:
            remaining = required - purchases - 1
            if remaining == 0:
                status_text = "<i>(след 🎁)</i>"
            else:
                status_text = f"<i>(ост {remaining})</i>"

    text = f"{header_line}\n\n{progress_bar}\n\n{status_text}"

    if "user_contexts" not in context.bot_data:
        context.bot_data["user_contexts"] = {}
    if user_id not in context.bot_data["user_contexts"]:
        context.bot_data["user_contexts"][user_id] = {}

    # ========== ИСПРАВЛЕННАЯ ЛОГИКА ПОЛУЧЕНИЯ ФЛАГОВ ==========
    show_delete_button = context.user_data.get("show_delete_button", False)
    if not show_delete_button:
        show_delete_button = context.bot_data["user_contexts"][user_id].get(
            "show_delete_button", False
        )

    show_erase_button = context.user_data.get("show_erase_button", False)
    if not show_erase_button:
        show_erase_button = context.bot_data["user_contexts"][user_id].get(
            "show_erase_button", False
        )

    # Проверяем, был ли штамп в этой сессии
    stamp_used_in_session = context.bot_data["user_contexts"][user_id].get(
        f"stamp_used_{customer_id}", False
    )

    logger.info(
        f"🔘 КНОПКИ | show_delete={show_delete_button} | show_erase={show_erase_button} | stamp_used={stamp_used_in_session}"
    )
    # =========================================================

    buttons = []

    # Кнопка "Штамп" всегда есть
    buttons.append(
        InlineKeyboardButton(
            f"{saved_style['filled']} Штамп", callback_data=f"stamp_{customer_id}"
        )
    )

    # Показываем "Стереть" если:
    if show_erase_button or stamp_used_in_session:
        buttons.append(
            InlineKeyboardButton("🧽 Стереть", callback_data=f"erase_{customer_id}")
        )

    # Кнопка "Удалить" только в режиме удаления
    if show_delete_button:
        buttons.append(
            InlineKeyboardButton(
                "🗑️ Удалить профиль", callback_data=f"admin_delete_{customer_id}"
            )
        )

    if show_delete_button:
        buttons.append(
            InlineKeyboardButton(
                "🔙 Назад", callback_data="back_to_users_menu_from_card"
            )
        )

    keyboard = InlineKeyboardMarkup([buttons])

    if message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            logger.info(f"✅ Карточка обновлена (edit) для customer_id={customer_id}")
        except Exception as e:
            logger.error(f"Ошибка обновления карточки: {e}")
            msg = await context.bot.send_message(
                chat_id=user_id, text=text, parse_mode="HTML", reply_markup=keyboard
            )
            context.bot_data["user_contexts"][user_id]["card_message_id"] = (
                msg.message_id
            )
            context.bot_data["user_contexts"][user_id]["current_customer"] = customer_id
            logger.info(f"✅ Карточка создана (send) для customer_id={customer_id}")
    else:
        msg = await context.bot.send_message(
            chat_id=user_id, text=text, parse_mode="HTML", reply_markup=keyboard
        )
        context.bot_data["user_contexts"][user_id]["card_message_id"] = msg.message_id
        context.bot_data["user_contexts"][user_id]["current_customer"] = customer_id
        logger.info(f"✅ Карточка создана (new) для customer_id={customer_id}")


async def handle_stamp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("stamp_"):
        customer_id = int(data.replace("stamp_", ""))
        staff_user = update.effective_user

        staff_username = staff_user.username or str(staff_user.id)

        promotion = db.get_promotion()
        required = promotion[2] if promotion else 7

        new_count, was_gift = db.update_user_purchases(customer_id, 1)

        if was_gift:
            db.add_daily_gift(staff_username)
        db.add_daily_stamp(staff_username)

        # Устанавливаем флаг, что в этой сессии был штамп
        if "user_contexts" not in context.bot_data:
            context.bot_data["user_contexts"] = {}
        if staff_user.id not in context.bot_data["user_contexts"]:
            context.bot_data["user_contexts"][staff_user.id] = {}

        # Увеличиваем счётчик штампов для этого клиента в сессии
        stamp_key = f"stamp_counter_{customer_id}"
        current_stamps = context.bot_data["user_contexts"][staff_user.id].get(
            stamp_key, 0
        )

        # Новая логика: если были отрицательные - сбрасываем до 1
        if current_stamps < 0:
            context.bot_data["user_contexts"][staff_user.id][stamp_key] = 1
        else:
            context.bot_data["user_contexts"][staff_user.id][stamp_key] = (
                current_stamps + 1
            )

        context.bot_data["user_contexts"][staff_user.id][
            f"stamp_used_{customer_id}"
        ] = True

        if was_gift:
            try:
                await context.bot.send_sticker(
                    chat_id=staff_user.id,
                    sticker="CAACAgIAAxkDAAJSuWmL2fU7xlayXeVa4qhmvU1fDeWmAAKgkwACe69JSNZ_88TxnRpuOgQ",
                )
            except Exception:
                pass

        user_id = staff_user.id
        message_id = query.message.message_id

        if "user_contexts" not in context.bot_data:
            context.bot_data["user_contexts"] = {}
        if user_id not in context.bot_data["user_contexts"]:
            context.bot_data["user_contexts"][user_id] = {}
        context.bot_data["user_contexts"][user_id]["current_customer"] = customer_id

        # Получаем текущий счётчик штампов для отображения
        stamp_counter = context.bot_data["user_contexts"][user_id].get(stamp_key, 0)

        # Отправляем обновлённую карточку со статусом штампов
        await send_or_update_customer_card(
            user_id, context, customer_id, message_id, stamp_counter
        )
        await notify_customer(context.bot, customer_id, new_count, required)

        # ЗАПРОС НА ОТЗЫВ С ЗАДЕРЖКОЙ 15 МИНУТ
        if staff_user.id != customer_id:
            delay_seconds = 900

            async def delayed_review():
                logger.info(
                    f"⏰ Задержка {delay_seconds} секунд перед отправкой отзыва для user_id={customer_id}"
                )
                await asyncio.sleep(delay_seconds)
                if db.should_show_review_prompt(customer_id):
                    await ask_for_review(update, context, customer_id)
                else:
                    logger.info(
                        f"Пользователь {customer_id} уже нажал все кнопки отзывов, пропускаем"
                    )

            asyncio.create_task(delayed_review())


async def handle_erase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("erase_"):
        customer_id = int(data.replace("erase_", ""))
        staff_user = update.effective_user

        staff_username = staff_user.username or str(staff_user.id)

        new_count, was_gift = db.update_user_purchases(customer_id, -1)

        db.remove_daily_stamp(staff_username)

        user_id = staff_user.id
        message_id = query.message.message_id

        # Работаем со счётчиком штампов
        stamp_key = f"stamp_counter_{customer_id}"
        if "user_contexts" not in context.bot_data:
            context.bot_data["user_contexts"] = {}
        if user_id not in context.bot_data["user_contexts"]:
            context.bot_data["user_contexts"][user_id] = {}

        current_stamps = context.bot_data["user_contexts"][user_id].get(stamp_key, 0)

        # Логика для erase:
        if current_stamps > 0:
            # Если есть галочки - просто убираем одну
            new_stamp_counter = current_stamps - 1
            context.bot_data["user_contexts"][user_id][stamp_key] = new_stamp_counter
        else:
            # Если галочек нет - уходим в отрицательные (показываем крестики)
            new_stamp_counter = (current_stamps - 1) if current_stamps < 0 else -1
            context.bot_data["user_contexts"][user_id][stamp_key] = new_stamp_counter

        await send_or_update_customer_card(
            user_id, context, customer_id, message_id, new_stamp_counter
        )


async def forward_message_to_staff(
    bot, message_text: str, from_user, chat_id: int, context: ContextTypes.DEFAULT_TYPE
):
    baristas = db.get_all_baristas()
    admin_ids = ADMIN_IDS
    recipients = set(admin_ids)

    for barista in baristas:
        username = barista[0]
        cursor = db.conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        if result:
            recipients.add(result[0])

    role = get_user_role(from_user.id, from_user.username)

    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT first_name, last_name, username, phone FROM users WHERE user_id = ?",
        (from_user.id,),
    )
    user_info = cursor.fetchone()

    if user_info:
        first_name, last_name, username, phone = user_info
        clean_last_name = last_name if last_name and last_name != "None" else ""
        display_name = f"{first_name or ''} {clean_last_name}".strip()
        if not display_name:
            display_name = f"@{username}" if username else f"ID:{from_user.id}"
    else:
        display_name = (
            f"@{from_user.username}" if from_user.username else f"ID:{from_user.id}"
        )
        username = from_user.username
        phone = None

    if role == "client":
        header = "🆕 <b>Новый заказ</b>"
        safe_display_name = escape_html(display_name)
        safe_username = (
            escape_html(username)
            if username and username != "Не указан" and username != "None"
            else ""
        )
        safe_phone = escape_html(phone) if phone else ""
        safe_message = escape_html(message_text)

        client_info = [f"<b>{safe_display_name}</b>"]
        if safe_username:
            client_info.append(f"@{safe_username}")
        if safe_phone:
            client_info.append(f"<code>{safe_phone}</code>")
        client_info_line = " | ".join(client_info)

        forward_text = f"""{header}

{safe_message}

{client_info_line}
---
🔄 <i>Нажмите кнопку ниже, чтобы подтвердить начало приготовления</i>"""

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Приступаю", callback_data=f"accept_order_{from_user.id}"
                    )
                ]
            ]
        )

        # Сохраняем ID отправленных сообщений для этого заказа
        order_key = f"order_{from_user.id}_{int(time.time())}"
        context.bot_data[order_key] = {
            "customer_id": from_user.id,
            "customer_name": display_name,
            "customer_username": username,
            "customer_phone": phone,
            "message_text": safe_message,
            "messages": [],  # список (recipient_id, message_id)
        }

        for recipient_id in recipients:
            if recipient_id != from_user.id:
                try:
                    sent_msg = await bot.send_message(
                        chat_id=recipient_id,
                        text=forward_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                    context.bot_data[order_key]["messages"].append(
                        (recipient_id, sent_msg.message_id)
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить заказ {recipient_id}: {e}")

        # Сохраняем ключ заказа в user_data для клиента
        if "user_contexts" not in context.bot_data:
            context.bot_data["user_contexts"] = {}
        if from_user.id not in context.bot_data["user_contexts"]:
            context.bot_data["user_contexts"][from_user.id] = {}
        context.bot_data["user_contexts"][from_user.id]["current_order_key"] = order_key

        try:
            confirmation_msg = await bot.send_message(
                chat_id=from_user.id,
                text="✉️ <b>Заказ отправлен!</b>\n\n<i>Возможно мы с вами свяжемся, чтобы уточнить детали</i>.",
                parse_mode="HTML",
            )
            context.bot_data["user_contexts"][from_user.id]["confirmation_msg_id"] = (
                confirmation_msg.message_id
            )
        except Exception as e:
            logger.error(
                f"Не удалось отправить подтверждение клиенту {from_user.id}: {e}"
            )

    else:
        safe_display_name = escape_html(display_name)
        safe_message = escape_html(message_text)

        forward_text = f"🧢 {safe_display_name} barista\n\n{safe_message}"

        for recipient_id in recipients:
            if recipient_id != from_user.id:
                try:
                    await bot.send_message(
                        chat_id=recipient_id, text=forward_text, parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(
                        f"Не удалось отправить сообщение {recipient_id}: {e}"
                    )


async def forward_review_to_staff(
    bot,
    user_id: int,
    review_text: str,
    is_anonymous: bool,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Отправляет отзыв всем админам и баристам"""

    # Получаем данные пользователя
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT username, first_name, last_name, phone FROM users WHERE user_id = ?",
        (user_id,),
    )
    user_info = cursor.fetchone()

    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    # Формируем отображение имени
    if is_anonymous:
        display_name = "Анонимно"
    else:
        if user_info:
            username, first_name, last_name, phone = user_info
            clean_last_name = last_name if last_name and last_name != "None" else ""
            full_name = f"{first_name or ''} {clean_last_name}".strip()
            if full_name:
                display_name = full_name
            elif username and username != "Не указан":
                display_name = f"@{username}"
            else:
                display_name = f"Клиент {user_id}"

            # Добавляем телефон если есть
            if phone:
                display_name += f" ({phone})"
        else:
            display_name = f"Клиент {user_id}"

    # Формируем текст отзыва
    review_header = f"<b>📝 Отзыв</b> {now}\n"
    review_header += f"{display_name}\n\n"

    review_message = review_header + review_text

    # Собираем получателей: все админы + все баристы
    recipients = set(ADMIN_IDS)

    baristas = db.get_all_baristas()
    for barista in baristas:
        username = barista[0]
        cursor = db.conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        if result:
            recipients.add(result[0])

    # Отправляем всем
    for recipient_id in recipients:
        try:
            await bot.send_message(
                chat_id=recipient_id, text=review_message, parse_mode="HTML"
            )
            logger.info(f"Отзыв отправлен сотруднику {recipient_id}")
        except Exception as e:
            logger.error(f"Не удалось отправить отзыв {recipient_id}: {e}")


async def handle_start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("accept_order_"):
        customer_id = int(data.replace("accept_order_", ""))
        staff_user = update.effective_user

        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT first_name FROM users WHERE user_id = ?", (staff_user.id,)
        )
        staff_info = cursor.fetchone()
        staff_first_name = (
            staff_info[0]
            if staff_info and staff_info[0]
            else staff_user.first_name or "Персонал"
        )

        cursor.execute(
            "SELECT first_name, last_name, username, phone FROM users WHERE user_id = ?",
            (customer_id,),
        )
        user_info = cursor.fetchone()

        if user_info:
            first_name, last_name, username, phone = user_info
            clean_last_name = last_name if last_name and last_name != "None" else ""
            display_name = f"{first_name or ''} {clean_last_name}".strip()
            if not display_name:
                display_name = f"@{username}" if username else f"Клиент"
            phone_display = f"<code>{phone}</code>" if phone else ""
        else:
            display_name = "Клиент"
            username = None
            phone_display = ""

        # Удаляем предыдущее сообщение подтверждения у клиента
        if "user_contexts" in context.bot_data and customer_id in context.bot_data.get(
            "user_contexts", {}
        ):
            prev_msg_id = context.bot_data["user_contexts"][customer_id].get(
                "confirmation_msg_id"
            )
            if prev_msg_id:
                try:
                    await context.bot.delete_message(
                        chat_id=customer_id, message_id=prev_msg_id
                    )
                    if customer_id in context.bot_data["user_contexts"]:
                        context.bot_data["user_contexts"][customer_id].pop(
                            "confirmation_msg_id", None
                        )
                except Exception as e:
                    logger.warning(
                        f"Не удалось удалить предыдущее сообщение у клиента {customer_id}: {e}"
                    )

        # Уведомляем клиента
        try:
            await context.bot.send_message(
                chat_id=customer_id,
                text=f"✅ <b>Заказ принят!</b>\n\n<i>{staff_first_name} приступает к приготовлению.</i>\n\nОжидаем вас!",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить клиента {customer_id}: {e}")

        # Получаем сохранённый ключ заказа
        order_key = None
        if (
            "user_contexts" in context.bot_data
            and customer_id in context.bot_data["user_contexts"]
        ):
            order_key = context.bot_data["user_contexts"][customer_id].get(
                "current_order_key"
            )

        # Формируем обновлённый текст (без "☑️ Готов" внизу)
        staff_display = (
            f"@{staff_user.username}" if staff_user.username else staff_first_name
        )

        original_message_text = ""
        client_info_line = ""

        if order_key and order_key in context.bot_data:
            original_message_text = context.bot_data[order_key].get("message_text", "")
            client_parts = [display_name]
            if username and username != "Не указан" and username != "None":
                client_parts.append(f"@{username}")
            if phone_display:
                client_parts.append(phone_display)
            client_info_line = " | ".join(client_parts)
        else:
            current_text = query.message.text
            lines = current_text.split("\n")

            message_text = ""
            header_found = False
            empty_line_after_header = False

            for i, line in enumerate(lines):
                if "Новый заказ" in line:
                    header_found = True
                    continue
                if header_found and not empty_line_after_header and line.strip() == "":
                    empty_line_after_header = True
                    continue
                if empty_line_after_header:
                    if line.strip().startswith("---") or line.strip().startswith("🔄"):
                        break
                    if ("@" in line or "<code>" in line) and not message_text:
                        client_info_line = line.strip()
                        break
                    if message_text:
                        message_text += line + "\n"
                    else:
                        message_text = line + "\n"

            original_message_text = message_text.strip()
            if not client_info_line:
                client_parts = [display_name]
                if username and username != "Не указан" and username != "None":
                    client_parts.append(f"@{username}")
                if phone_display:
                    client_parts.append(phone_display)
                client_info_line = " | ".join(client_parts)

        # Обновлённый текст: иконка ▶️ меняется на ☑️, убираем "Готов"
        updated_text = f"""☑️ <b>Заказ</b>

{original_message_text}

{client_info_line}
---
✅ <b>Принял:</b> {staff_display}"""

        new_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "☑️ Готово", callback_data=f"finish_order_{customer_id}"
                    )
                ]
            ]
        )

        # Редактируем сообщение у всех получателей
        if order_key and order_key in context.bot_data:
            for recipient_id, msg_id in context.bot_data[order_key]["messages"]:
                try:
                    await context.bot.edit_message_text(
                        chat_id=recipient_id,
                        message_id=msg_id,
                        text=updated_text,
                        parse_mode="HTML",
                        reply_markup=new_keyboard,
                    )
                except Exception as e:
                    logger.warning(
                        f"Не удалось обновить сообщение у {recipient_id}: {e}"
                    )
            context.bot_data[order_key]["stage"] = "accepted"
            context.bot_data[order_key]["staff_name"] = staff_first_name
            context.bot_data[order_key]["staff_username"] = staff_user.username
        else:
            await query.edit_message_text(
                text=updated_text, parse_mode="HTML", reply_markup=new_keyboard
            )


async def handle_finish_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("finish_order_"):
        customer_id = int(data.replace("finish_order_", ""))
        staff_user = update.effective_user

        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT first_name FROM users WHERE user_id = ?", (staff_user.id,)
        )
        staff_info = cursor.fetchone()
        staff_first_name = (
            staff_info[0]
            if staff_info and staff_info[0]
            else staff_user.first_name or "Персонал"
        )

        # Уведомляем клиента
        try:
            check_msg = await context.bot.send_message(chat_id=customer_id, text="☑️")

            async def delete_check_later():
                await asyncio.sleep(600)
                try:
                    await check_msg.delete()
                except Exception:
                    pass

            asyncio.create_task(delete_check_later())
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление клиенту {customer_id}: {e}")

        # Получаем сохранённый ключ заказа
        order_key = None
        if (
            "user_contexts" in context.bot_data
            and customer_id in context.bot_data["user_contexts"]
        ):
            order_key = context.bot_data["user_contexts"][customer_id].get(
                "current_order_key"
            )

        # Получаем данные заказа
        original_message_text = ""
        client_info_line = ""
        accepted_by = ""

        if order_key and order_key in context.bot_data:
            original_message_text = context.bot_data[order_key].get("message_text", "")
            accepted_by = context.bot_data[order_key].get(
                "staff_name", staff_first_name
            )

            # Собираем информацию о клиенте
            cursor.execute(
                "SELECT first_name, last_name, username, phone FROM users WHERE user_id = ?",
                (customer_id,),
            )
            user_info = cursor.fetchone()
            if user_info:
                first_name, last_name, username, phone = user_info
                clean_last_name = last_name if last_name and last_name != "None" else ""
                display_name = f"{first_name or ''} {clean_last_name}".strip()
                if not display_name:
                    display_name = f"@{username}" if username else f"Клиент"
                phone_display = f"<code>{phone}</code>" if phone else ""
                client_parts = [display_name]
                if username and username != "Не указан" and username != "None":
                    client_parts.append(f"@{username}")
                if phone_display:
                    client_parts.append(phone_display)
                client_info_line = " | ".join(client_parts)
        else:
            # fallback: парсим текущее сообщение
            current_text = query.message.text
            # Просто меняем иконку с ▶️ на ☑️, убираем кнопку
            updated_text = current_text.replace("▶️ <b>Заказ</b>", "☑️ <b>Заказ</b>")
            # Убираем строку "☑️ Готов" если она есть
            updated_text = updated_text.replace("\n☑️ <b>Готов</b>", "")
            await query.edit_message_text(
                text=updated_text, parse_mode="HTML", reply_markup=None
            )
            await show_customer_profile(staff_user.id, context, customer_id)
            return

        # ФИНАЛЬНЫЙ ТЕКСТ: иконка ☑️, НЕТ строки "Готов" внизу
        finished_text = f"""☑️ <b>Заказ</b>

{original_message_text}

{client_info_line}
---
✅ <b>Принял:</b> {accepted_by}"""
        # Убрали "☑️ Готов" — теперь только иконка в начале говорит о готовности

        # Редактируем сообщение у всех получателей
        if order_key and order_key in context.bot_data:
            for recipient_id, msg_id in context.bot_data[order_key]["messages"]:
                try:
                    await context.bot.edit_message_text(
                        chat_id=recipient_id,
                        message_id=msg_id,
                        text=finished_text,
                        parse_mode="HTML",
                        reply_markup=None,  # Убираем кнопки
                    )
                except Exception as e:
                    logger.warning(
                        f"Не удалось обновить сообщение у {recipient_id}: {e}"
                    )

        # Показываем профиль клиента
        await show_customer_profile(staff_user.id, context, customer_id)


async def show_customer_profile(
    user_id: int, context: ContextTypes.DEFAULT_TYPE, customer_id: int
):
    await send_or_update_customer_card(user_id, context, customer_id)


def staff_role_emoji(role):
    return {"admin": "🧢", "barista": "🧢"}.get(role, "👤")


def check_spam(user_id: int, cooldown_seconds: int = 30) -> tuple:
    current_time = time.time()
    last_time = client_last_message_time.get(user_id, 0)

    if current_time - last_time < cooldown_seconds:
        seconds_left = int(cooldown_seconds - (current_time - last_time))
        return False, seconds_left

    client_last_message_time[user_id] = current_time
    return True, 0


# ================== ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ==================


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = get_user_state(context)
    text = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username
    role = get_user_role(user_id, username)

    logger.info(
        f"📨 handle_message | user_id={user_id} | role={role} | state={state} | text='{text[:50]}'"
    )

    # ========== НОВАЯ ПРОВЕРКА: ОБРАБОТКА НОМЕРА ТЕЛЕФОНА ДЛЯ КЛИЕНТОВ ==========
    # Только для клиентов (не для админов/баристов в режиме поиска)
    is_phone_input = False
    parts = text.split(" ", 1)
    phone_part = parts[0].strip()
    if phone_part.isdigit() and len(phone_part) == 10:
        is_phone_input = True

    # Если это 10 цифр И роль = клиент И не в специальном режиме (который требует другого ввода)
    special_states_for_phone = [
        "setting_phone",
        "setting_phone_from_callback",
        "changing_promotion_name",
        "changing_promotion_condition",
        "changing_promotion_description",
        "broadcast_waiting_input",
        "broadcast_preview",
        "admin_barista",
        "admin_users_list",
        "finding_customer",
        "selecting_customer",
        "selecting_customer_admin",
    ]

    if (
        role == "client"
        and is_phone_input
        and state not in special_states_for_phone
        and not text.startswith("/")
    ):
        # Обрабатываем как ввод номера телефона
        logger.info(
            f"📞 Обнаружен ввод 10 цифр клиентом {user_id}, обрабатываем как номер телефона"
        )
        handled = await handle_phone_number_input(
            update, context, text, user_id, role, state
        )
        if handled:
            return  # Завершаем, номер обработан
    # ========================================================================

    # ========== УДАЛЯЕМ ПОДСКАЗКИ ==========
    # Удаляем подсказку пользователей
    if state == "admin_users_list":
        hint_msg_id = context.user_data.get("users_hint_message_id")
        if hint_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=hint_msg_id
                )
                context.user_data.pop("users_hint_message_id", None)
            except Exception:
                pass

    # Удаляем подсказку баристов
    if state == "admin_barista":
        hint_msg_id = context.user_data.get("barista_hint_message_id")
        if hint_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=hint_msg_id
                )
                context.user_data.pop("barista_hint_message_id", None)
            except Exception:
                pass
    # ======================================
    # ========== ВАЖНО: СНАЧАЛА ПРОВЕРЯЕМ РАССЫЛКУ ==========
    if state == "broadcast_waiting_input":
        await handle_broadcast_message(update, context)
        return
    # =======================================================
    # ========== НОВАЯ ЛОГИКА: forwarding для персонала ==========
    # Определяем, нужно ли пересылать сообщение
    should_forward = False

    # Для клиентов: всегда пересылаем (кроме специальных команд и кнопок)
    if role == "client" and state == "main" and not text.startswith("/"):
        # Список текстов, которые НЕ нужно пересылать (кнопки интерфейса)
        ui_buttons = [
            "◾️QR-код",
            "🎁 Акции",
            "📞 Привязать номер",
            "🔙 Назад",
            "📱 Мой QR",
            "🪪 Прогресс-бар",
        ]

        # Проверяем, является ли текст кнопкой интерфейса
        is_ui_button = text in ui_buttons

        # Проверяем, является ли текст номером телефона (4 или 10 цифр)
        is_phone_number = text.isdigit() and (len(text) == 4 or len(text) == 10)

        # Если не кнопка и не номер телефона - пересылаем
        if not is_ui_button and not is_phone_number:
            should_forward = True

    # ДЛЯ БАРИСТОВ И АДМИНОВ: пересылаем сообщения в общий чат
    # НО ТОЛЬКО если они НЕ в режиме клиента (client_mode)
    if (
        role in ["barista", "admin"]
        and state != "client_mode"
        and not text.startswith("/")
    ):
        # Исключаем ввод номеров и команд
        is_phone_input = False

        # Проверка на ввод номера (4 или 10 цифр)
        if text.isdigit() and (len(text) == 4 or len(text) == 10):
            is_phone_input = True

        # Проверка на ввод "номер имя"
        if " " in text:
            parts = text.split(" ", 1)
            if parts[0].isdigit() and len(parts[0]) == 10:
                is_phone_input = True

        # Исключаем специальные состояния (привязка номера, настройки акций и т.д.)
        special_states = [
            "setting_phone",
            "setting_phone_from_callback",
            "changing_promotion_name",
            "changing_promotion_condition",
            "changing_promotion_description",
            "broadcast_message",
            "finding_customer",
            "selecting_customer",
            "admin_barista",
            "admin_users_list",
            "waiting_for_review_choice",
            "waiting_for_review_text",
        ]

        if not is_phone_input and state not in special_states:
            should_forward = True
    # ============================================================   # ============================================================

    # ========== АДМИН: поиск клиентов ==========
    if role == "admin":
        # ========== УДАЛЯЕМ ПОДСКАЗКУ ПРИ ПОИСКЕ КЛИЕНТА ==========
        await delete_hint_message(context, update.effective_chat.id)
        # ==========================================================

        # Проверка на 4 цифры (поиск по последним 4 цифрам)
        if text.isdigit() and len(text) == 4:
            results = db.find_user_by_phone_last4(text)
            if results is None:
                await update.message.reply_text(f"❌ {text} не найден")
            elif isinstance(results, list) and len(results) > 1:
                context.user_data["multiple_customers"] = results
                keyboard = []
                for cid in results:
                    cursor = db.conn.cursor()
                    cursor.execute(
                        "SELECT first_name, last_name, phone FROM users WHERE user_id = ?",
                        (cid,),
                    )
                    user_info = cursor.fetchone()
                    if user_info:
                        first_name, last_name, phone = user_info
                        name = (
                            f"{first_name or ''} {last_name or ''}".strip()
                            or f"Клиент {cid}"
                        )
                        display_phone = phone[-4:] if phone else "???"
                        keyboard.append(
                            [KeyboardButton(f"📞 {name} ({display_phone})")]
                        )
                keyboard.append([KeyboardButton("🔙 Отменить")])
                await update.message.reply_text(
                    f"🔍 Найдено {len(results)} клиента с окончанием {text}:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
                )
                set_user_state(context, "selecting_customer")
            else:
                customer_id = results if not isinstance(results, list) else results[0]
                await send_temp_message(update, "✅ Найден клиент по номеру")
                await asyncio.sleep(0.5)
                if state == "admin_users_list":
                    logger.info(
                        f"🔍 Поиск в режиме admin_users_list, показываем кнопки удаления"
                    )
                    await process_customer_scan(
                        update,
                        context,
                        customer_id,
                        show_delete_button=True,
                        show_erase_button=True,
                    )
                else:
                    await process_customer_scan(
                        update,
                        context,
                        customer_id,
                        show_delete_button=False,
                        show_erase_button=False,
                    )
            # ======================================================
            return

        # Проверка на 10 цифр (поиск по полному номеру)
        if text.isdigit() and len(text) == 10:
            customer_id = db.find_user_by_phone(text)
            if customer_id:
                await send_temp_message(update, "✅ Найден клиент по номеру")
                await asyncio.sleep(0.5)
                await process_customer_scan(
                    update,
                    context,
                    customer_id,
                    show_delete_button=False,
                    show_erase_button=False,
                )
            else:
                await update.message.reply_text(
                    f"❌ Клиент с номером {text} не найден\n\nИспользуйте формат: 9996664422 Саша"
                )
            return

        # Проверка на формат "номер имя" (создание нового клиента)
        if " " in text:
            parts = text.split(" ", 1)
            phone = parts[0].strip()
            name = parts[1].strip()
            if phone.isdigit() and len(phone) == 10:
                customer_id = db.find_user_by_phone(phone)
                if customer_id:
                    await send_temp_message(update, "✅ Найден клиент")
                    await asyncio.sleep(0.5)
                    await process_customer_scan(
                        update,
                        context,
                        customer_id,
                        show_delete_button=False,
                        show_erase_button=False,
                    )
                else:
                    new_customer_id = random.randint(1000000000, 9999999999)
                    db.get_or_create_user(new_customer_id, "", name, "")
                    db.update_user_phone(new_customer_id, phone)
                    await send_temp_message(
                        update, f"✅ Создан новый клиент: {name} ({phone})"
                    )
                    await asyncio.sleep(0.5)
                    await process_customer_scan(
                        update,
                        context,
                        new_customer_id,
                        show_delete_button=False,
                        show_erase_button=False,
                    )
                set_user_state(context, "barista_mode")
                return

        # Если не подошло ни под одно условие поиска — это обычное сообщение
        # НЕ ВОЗВРАЩАЕМСЯ, а идём дальше к should_forward
        pass

    # =====================================================
    # ========== ЕСЛИ НУЖНО ПЕРЕСЛАТЬ СООБЩЕНИЕ ==========
    if should_forward:
        if len(text) > 500:
            await update.message.reply_text(
                "❌ *Сообщение слишком длинное!*", parse_mode="Markdown"
            )
            return
        can_send, seconds_left = check_spam(user_id, 30)
        if not can_send:
            await update.message.reply_text(
                f"⏳ Подождите {seconds_left} секунд.", parse_mode="Markdown"
            )
            return

        # Отправляем в общий чат персонала
        await forward_message_to_staff(
            context.bot, text, update.effective_user, update.effective_chat.id, context
        )

        # Для баристов/админов показываем подтверждение отправки
        if role in ["barista", "admin"]:
            temp_msg = await update.message.reply_text(
                "📤 _Отправлено чат_", parse_mode="Markdown"
            )
            asyncio.create_task(delete_message_after_delay(temp_msg, 2))

        # Не обрабатываем дальше, так как сообщение уже переслано
        return
    # =================================================

    # ========== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ СОСТОЯНИЙ ==========

    # Обработка добавления/удаления баристов из админ-панели
    if state == "admin_barista" and (text.startswith("@") or text.startswith("-")):
        await handle_barista_text(update, context)
        return

    if state == "finding_customer":
        await handle_customer_search(update, context, text)
        return

    if state == "broadcast_message":
        await handle_broadcast_message(update, context)
        return

    if state == "changing_promotion_condition":
        try:
            new_condition = int(text)
            if 1 <= new_condition <= 20:
                db.update_promotion(required_purchases=new_condition)
                await update.message.reply_text(
                    f"✅ Условие акции изменено на {new_condition} покупок!"
                )
            else:
                await update.message.reply_text("❌ Число должно быть от 1 до 20")
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число")
        set_user_state(context, "admin_settings")
        await show_admin_settings_inline(update, context)
        return

    if state == "changing_promotion_name":
        if text and text not in ["📝 Название", "7️⃣ Условие", "📖 Описание", "🔙 Назад"]:
            db.update_promotion(name=text)
            await update.message.reply_text("✅ Название акции обновлено!")
            set_user_state(context, "admin_settings")
            await show_admin_settings_inline(update, context)
        else:
            await show_admin_settings_inline(update, context)
        return

    if state == "changing_promotion_description":
        if text and text not in ["📝 Название", "7️⃣ Условие", "📖 Описание", "🔙 Назад"]:
            db.update_promotion(description=text)
            await update.message.reply_text("✅ Описание акции успешно обновлено!")
            set_user_state(context, "admin_settings")
            await show_admin_settings_inline(update, context)
        else:
            await show_admin_settings_inline(update, context)
        return

    # Режим баристы (поиск клиента по номеру)
    if state == "barista_mode" or (
        role in ["barista", "admin"] and state in ["main", "admin_users_list"]
    ):
        # ========== УДАЛЯЕМ ПОДСКАЗКУ ПРИ ПОИСКЕ КЛИЕНТА ==========
        await delete_hint_message(context, update.effective_chat.id)
        # ==========================================================

        if text.isdigit() and len(text) == 4:
            results = db.find_user_by_phone_last4(text)
            if results is None:
                await update.message.reply_text(f"❌ {text} не найден")
            elif isinstance(results, list) and len(results) > 1:
                context.user_data["multiple_customers"] = results
                keyboard = []
                for cid in results:
                    cursor = db.conn.cursor()
                    cursor.execute(
                        "SELECT first_name, last_name, phone FROM users WHERE user_id = ?",
                        (cid,),
                    )
                    user_info = cursor.fetchone()
                    if user_info:
                        first_name, last_name, phone = user_info
                        name = (
                            f"{first_name or ''} {last_name or ''}".strip()
                            or f"Клиент {cid}"
                        )
                        display_phone = phone[-4:] if phone else "???"
                        keyboard.append(
                            [KeyboardButton(f"📞 {name} ({display_phone})")]
                        )
                keyboard.append([KeyboardButton("🔙 Отменить")])
                await update.message.reply_text(
                    f"🔍 Найдено {len(results)} клиента с окончанием {text}:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
                )
                set_user_state(context, "selecting_customer")
            else:
                customer_id = results if not isinstance(results, list) else results[0]
                await send_temp_message(update, "✅ Найден клиент по номеру")
                await asyncio.sleep(0.5)
                # ========== ИСПРАВЛЕНИЕ: проверяем состояние ==========
                if state == "admin_users_list":
                    logger.info(
                        f"🔍 Поиск в режиме admin_users_list, показываем кнопки удаления"
                    )
                    await process_customer_scan(
                        update,
                        context,
                        customer_id,
                        show_delete_button=True,
                        show_erase_button=True,  # <-- ВАЖНО: включаем кнопку Стереть
                    )
                else:
                    await process_customer_scan(
                        update,
                        context,
                        customer_id,
                        show_delete_button=False,
                        show_erase_button=False,
                    )
                # ======================================================
            return

        if text.isdigit() and len(text) == 10:
            customer_id = db.find_user_by_phone(text)
            if customer_id:
                await send_temp_message(update, "✅ Найден клиент по номеру")
                await asyncio.sleep(0.5)
                # ========== ИСПРАВЛЕНИЕ: проверяем состояние ==========
                if state == "admin_users_list":
                    logger.info(
                        f"🔍 Поиск в режиме admin_users_list, показываем кнопки удаления"
                    )
                    await process_customer_scan(
                        update,
                        context,
                        customer_id,
                        show_delete_button=True,
                        show_erase_button=True,  # <-- ВАЖНО: включаем кнопку Стереть
                    )
                else:
                    await process_customer_scan(
                        update,
                        context,
                        customer_id,
                        show_delete_button=False,
                        show_erase_button=False,
                    )
                # ======================================================
            else:
                await update.message.reply_text(
                    f"❌ Клиент с номером {text} не найден\n\nИспользуйте формат: 9996664422 Саша"
                )
            return

        if " " in text:
            try:
                parts = text.split(" ", 1)
                phone = parts[0].strip()
                name = parts[1].strip()
                if phone.isdigit() and len(phone) == 10:
                    customer_id = db.find_user_by_phone(phone)
                    if customer_id:
                        await send_temp_message(update, "✅ Найден клиент по номеру")
                        await asyncio.sleep(0.5)
                        # ========== ИСПРАВЛЕНИЕ: проверяем состояние ==========
                        if state == "admin_users_list":
                            logger.info(
                                f"🔍 Поиск в режиме admin_users_list, показываем кнопки удаления"
                            )
                            await process_customer_scan(
                                update,
                                context,
                                customer_id,
                                show_delete_button=True,
                                show_erase_button=True,  # <-- ВАЖНО: включаем кнопку Стереть
                            )
                        else:
                            await process_customer_scan(
                                update,
                                context,
                                customer_id,
                                show_delete_button=False,
                                show_erase_button=False,
                            )
                        # ======================================================
                    else:
                        new_customer_id = random.randint(1000000000, 9999999999)
                        db.get_or_create_user(new_customer_id, "", name, "")
                        db.update_user_phone(new_customer_id, phone)
                        await send_temp_message(
                            update, f"✅ Создан новый клиент: {name} ({phone})"
                        )
                        await asyncio.sleep(0.5)
                        # Для нового клиента тоже проверяем состояние
                        if state == "admin_users_list":
                            await process_customer_scan(
                                update,
                                context,
                                new_customer_id,
                                show_delete_button=True,
                                show_erase_button=True,  # <-- ВАЖНО: включаем кнопку Стереть
                            )
                        else:
                            await process_customer_scan(
                                update,
                                context,
                                new_customer_id,
                                show_delete_button=False,
                                show_erase_button=False,
                            )
                    set_user_state(context, "barista_mode")
                else:
                    await update.message.reply_text("❌ Номер должен быть 10 цифр")
            except (ValueError, IndexError):
                await update.message.reply_text(
                    "❌ Формат: номер имя\nПример: 9996664422 Саша"
                )
            return

        if role == "barista":
            await update.message.reply_text(
                "📸 Отправьте фото QR или введите номер имя\nПример: 9996664422 Саша"
            )
        return

    # Выбор клиента из нескольких
    if state == "selecting_customer":
        if text.startswith("📞 "):
            customer_id = None
            for cid in context.user_data.get("multiple_customers", []):
                cursor = db.conn.cursor()
                cursor.execute(
                    "SELECT first_name, last_name, phone FROM users WHERE user_id = ?",
                    (cid,),
                )
                user_info = cursor.fetchone()
                if user_info:
                    first_name, last_name, phone = user_info
                    name = (
                        f"{first_name or ''} {last_name or ''}".strip()
                        or f"Клиент {cid}"
                    )
                    display_phone = phone[-4:] if phone else "???"
                    if f"📞 {name} ({display_phone})" == text:
                        customer_id = cid
                        break
            if customer_id:
                await process_customer_scan(update, context, customer_id)
                context.user_data.pop("multiple_customers", None)
                set_user_state(context, "barista_mode")
            else:
                await update.message.reply_text("❌ Ошибка выбора клиента")
        elif text == "🔙 Отменить":
            set_user_state(context, "barista_mode")
            await show_barista_main(update)
        return

    # Привязка номера
    if state == "setting_phone" or state == "setting_phone_from_callback":
        if text == "🔙 Назад":
            if state == "setting_phone_from_callback":
                uid = context.user_data.get("phone_user_id")
                if uid:
                    await show_progress_with_choice(
                        update, context, uid, from_promotion=True
                    )
                else:
                    set_user_state(context, "client_mode")
                    await show_client_main(update, context)
            else:
                set_user_state(context, "client_mode")
                await show_client_main(update, context)
            return

        if " " in text:
            try:
                parts = text.split(" ", 1)
                phone = parts[0].strip()
                name = parts[1].strip()
                if phone.isdigit() and len(phone) == 10:
                    target_user_id = (
                        context.user_data.get("phone_user_id", user_id)
                        if state == "setting_phone_from_callback"
                        else user_id
                    )
                    cursor = db.conn.cursor()
                    cursor.execute(
                        "UPDATE users SET first_name = ?, phone = ? WHERE user_id = ?",
                        (name, phone, target_user_id),
                    )
                    db.conn.commit()
                    await send_temp_message(
                        update, f"✅ Ваш профиль обновлен: {name} ({phone})"
                    )
                    if state == "setting_phone_from_callback":
                        await show_progress_with_choice(
                            update, context, target_user_id, from_promotion=True
                        )
                    else:
                        set_user_state(context, "client_mode")
                        await show_client_main(update, context)
                else:
                    await update.message.reply_text("❌ Номер должен быть 10 цифр")
            except (ValueError, IndexError):
                await update.message.reply_text(
                    "❌ Формат: номер имя\nПример: 9996664422 Саша"
                )
        else:
            await update.message.reply_text(
                "❌ Введите номер и имя через пробел\nПример: 9996664422 Саша"
            )
        return

    # ===========================================

    # Главные состояния по ролям
    if role == "admin" and state == "main":
        await show_admin_main(update, context)
        return

    if role == "barista" and state == "main":
        await show_barista_main(update)
        return

    if role == "client" and state == "main":
        if text == "◾️QR-код":
            await send_qr_code(update, user_id)
        elif text == "🎁 Акции":
            await show_promotion_info_with_context(update, context)
        elif text == "📞 Привязать номер":
            set_user_state(context, "setting_phone")
            await update.message.reply_text(
                "🖇 Введите номер (10 цифр) и имя через пробел\nПример: 9996664422 Саша"
            )
        return


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    try:
        path = db.backup_db()
        await update.message.reply_document(
            document=open(path, "rb"),
            caption=f"📦 Резервная копия БД\n📅 {datetime.datetime.now():%d.%m.%Y %H:%M}",
        )
        db.cleanup_old_backups(7)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при создании бэкапа:\n{e}")


async def clear_admin_keyboard(update: Update):
    """Очищает старую reply-клавиатуру у админа"""
    try:
        await update.message.reply_text("✅", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        pass  # Игнорируем ошибки


async def handle_customer_search(
    update: Update, context: ContextTypes.DEFAULT_TYPE, search_query: str
):
    logger.info(f"handle_customer_search: {search_query}")

    if search_query.isdigit() and len(search_query) == 4:
        results = db.find_user_by_phone_last4(search_query)
        if results is None:
            await update.message.reply_text(
                f"❌ Клиент с окончанием {search_query} не найден"
            )
        elif isinstance(results, list) and len(results) > 1:
            context.user_data["multiple_customers"] = results
            keyboard = []
            for cid in results:
                cursor = db.conn.cursor()
                cursor.execute(
                    "SELECT first_name, last_name, phone FROM users WHERE user_id = ?",
                    (cid,),
                )
                user_info = cursor.fetchone()
                if user_info:
                    first_name, last_name, phone = user_info
                    name = (
                        f"{first_name or ''} {last_name or ''}".strip()
                        or f"Клиент {cid}"
                    )
                    display_phone = phone[-4:] if phone else "???"
                    keyboard.append([KeyboardButton(f"📞 {name} ({display_phone})")])
            keyboard.append([KeyboardButton("🔙 Отменить")])
            await update.message.reply_text(
                f"🔍 Найдено {len(results)} клиента с окончанием {search_query}:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            )
            set_user_state(context, "selecting_customer_admin")
        else:
            customer_id = results if not isinstance(results, list) else results[0]
            await show_customer_card_admin(update, context, customer_id)
        return

    if search_query.isdigit() and len(search_query) == 10:
        customer_id = db.find_user_by_phone(search_query)
        if customer_id:
            await show_customer_card_admin(update, context, customer_id)
        else:
            await update.message.reply_text(
                f"❌ Клиент с номером {search_query} не найден"
            )
        return

    if search_query.startswith("@"):
        username_input = search_query[1:].strip()
        user_data = db.get_user_by_username_exact(username_input)
        if user_data:
            await show_customer_card_admin(update, context, user_data[0])
        else:
            await update.message.reply_text(
                f"❌ Пользователь @{username_input} не найден"
            )
        return

    user_data = db.get_user_by_username_exact(search_query)
    if user_data:
        await show_customer_card_admin(update, context, user_data[0])
        return

    await update.message.reply_text("❌ Пользователь не найден.")


async def handle_phone_number_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    user_id: int,
    role: str,
    state: str,
):
    """
    Обрабатывает ввод 10 цифр (с именем или без) для привязки/изменения номера телефона.
    Возвращает True если обработано, False если нет.
    """
    # Проверяем, что это 10 цифр (возможно с пробелом и именем)
    parts = text.split(" ", 1)
    phone_part = parts[0].strip()

    # Должно быть 10 цифр
    if not (phone_part.isdigit() and len(phone_part) == 10):
        return False

    phone = phone_part
    name = parts[1].strip() if len(parts) > 1 else None

    # Получаем текущие данные пользователя
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT first_name, phone FROM users WHERE user_id = ?",
        (user_id,),
    )
    user_data = cursor.fetchone()
    current_name = user_data[0] if user_data else None
    current_phone = user_data[1] if user_data else None

    # Определяем, есть ли уже номер
    has_phone = current_phone is not None and current_phone != ""

    # Формируем ответное сообщение
    if name:
        # Ввели номер + имя
        db.update_user_phone(user_id, phone)
        cursor.execute(
            "UPDATE users SET first_name = ? WHERE user_id = ?",
            (name, user_id),
        )
        db.conn.commit()

        if has_phone:
            response_text = f"✅ <b>Номер и имя обновлены</b>\n\n📞 {phone}\n👤 {name}"
        else:
            response_text = f"✅ <b>Номер и имя добавлены</b>\n\n📞 {phone}\n👤 {name}"
    else:
        # Ввели только номер
        db.update_user_phone(user_id, phone)

        # Если имени нет, берём из Telegram или из базы
        if not current_name or current_name == "":
            telegram_name = update.effective_user.first_name or ""
            if update.effective_user.last_name:
                telegram_name += f" {update.effective_user.last_name}"
            if telegram_name.strip():
                cursor.execute(
                    "UPDATE users SET first_name = ? WHERE user_id = ?",
                    (telegram_name.strip(), user_id),
                )
                db.conn.commit()
                used_name = telegram_name.strip()
            else:
                used_name = current_name or "Гость"
        else:
            used_name = current_name

        if has_phone:
            response_text = f"✅ <b>Номер обновлён</b>\n\n📞 {phone}\n👤 {used_name}"
        else:
            response_text = f"✅ <b>Номер добавлен</b>\n\n📞 {phone}\n👤 {used_name}"

    # Отправляем подтверждение
    await update.message.reply_text(response_text, parse_mode="HTML")

    # Обновляем прогресс-бар у клиента (если он открыт)
    try:
        await show_progress_with_choice(update, context, user_id, from_promotion=True)
    except Exception as e:
        logger.debug(f"Не удалось обновить прогресс-бар после смены номера: {e}")

    return True


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = get_user_role(user.id, user.username)

    if role == "admin":
        text = """
<i>Акция: 7-й напиток в подарок</i>
--------------------------------
<b>Поиск клиента</b>
- Отправьте фото QR-кода клиента
- Последние 4 цифры номера телефона клиента
- 10 цифр номера телефона клиента (все без 7/8)

<b>Добавление нового клиента по номеру</b>
- Отправьте номер без 7/8 пробел Имя
<i>например:</i>
9996664422 Саша

<i>Остальной отправленный текст увидят ваши сотрудники</i>
---------------------------------
<b>Детали</b>
<i>- Клиент не знает о боте если он добавлен вами по номеру (у них эмодзи напротив имени '▫️')</i>
<i>- Если клиент с ботом ('▪️'), он должен сам привязать свой номер телефона, чтобы исключить дублирования</i>
---------------------------------
<b>Команды:</b>
-
/start - админ-панель
-
/client - режим клиента
-
/backup - копия БД
-
/sticker_id - ID стикера
-
/help - эта справка
"""
    elif role == "barista":
        text = """
<i>Акция: 7-й напиток в подарок</i>
--------------------------------
<b>Поиск клиента</b>
- Отправьте фото QR-кода клиента
- Последние 4 цифры номера телефона клиента
- 10 цифр номера телефона клиента (все без 7/8)

<b>Добавление нового клиента по номеру</b>
- Отправьте номер без 7/8 пробел Имя
<i>например:</i>
9996664422 Саша

<i>Остальной отправленный текст увидят ваши сотрудники</i>
---------------------------------
<b>Детали</b>
<i>- Клиент не знает о боте если он добавлен вами по номеру (у них эмодзи напротив имени '▫️')</i>
<i>- Если клиент с ботом ('▪️'), он должен сам привязать свой номер телефона, чтобы исключить дублирования</i>
--------------------------------
<b>Команды:</b>
-
/start - режим бариста
-
/client - режим клиента
-
/help - эта справка
"""
    else:
        text = """
<i>Каждый 7-й напиток в подарок</i>

• кнопка ◾️QR-код - всегда на нижней панели. изображение не обновляется
• 🪪 Прогресс-бар - кратко об акции и привязка номера
• 📞 Привязать номер - привязать/изменить цифры/имя

<b>Заказ заранее</b>
Введите в чат в формате: Название | Объём | Время
<i>например</i>
Капучино 03 с карамелью 15 минут

<i>Мы увидим его как заказ</i>
---------------------------------
<i>Команды:</i>
-
/start - обновить
-
/help - эта справка
"""
    await update.message.reply_text(text, parse_mode="HTML")


async def log_any_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    update_type = "unknown"
    if update.message:
        update_type = "message"
    elif update.callback_query:
        update_type = "callback_query"
    elif update.edited_message:
        update_type = "edited_message"

    user = update.effective_user
    user_str = (
        f"@{user.username}"
        if user and user.username
        else f"id={user.id if user else 'unknown'}"
    )
    logger.debug(f"📡 {update_type} от {user_str}")


async def forward_voice_to_staff(
    update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: int
):
    """Пересылает голосовое сообщение всем баристам и админам"""

    voice = update.message.voice
    file_id = voice.file_id
    duration = voice.duration

    # Получаем получателей (админы + баристы)
    recipients = set(ADMIN_IDS)
    baristas = db.get_all_baristas()
    for barista in baristas:
        cursor = db.conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (barista[0],))
        result = cursor.fetchone()
        if result:
            recipients.add(result[0])

    # Данные клиента
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT first_name, last_name, username, phone FROM users WHERE user_id = ?",
        (customer_id,),
    )
    user_info = cursor.fetchone()

    if user_info:
        first_name, last_name, username, phone = user_info
        clean_last_name = last_name if last_name and last_name != "None" else ""
        display_name = f"{first_name or ''} {clean_last_name}".strip()
        if not display_name:
            display_name = f"@{username}" if username else f"Клиент"
    else:
        display_name = "Клиент"
        username = None
        phone = None

    # Формируем caption (текст над голосовым)
    caption_parts = [display_name]
    if username and username != "Не указан" and username != "None":
        caption_parts.append(f"@{username}")
    if phone:
        caption_parts.append(phone)

    header_line = " | ".join(caption_parts)

    caption = f"🆕 <b>Новый заказ</b>\n\n{header_line}\n---\n🔄 <i>Нажмите кнопку ниже, чтобы подтвердить начало приготовления</i>"

    # Кнопка как у текстового заказа
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Приступаю", callback_data=f"accept_order_{customer_id}"
                )
            ]
        ]
    )

    # Отправляем голосовое с caption и кнопкой
    for recipient_id in recipients:
        try:
            await context.bot.send_voice(
                chat_id=recipient_id,
                voice=file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Не удалось отправить голосовое {recipient_id}: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = get_user_role(user_id, update.effective_user.username)

    if role != "client":
        await update.message.reply_text(
            "❌ Только клиенты могут отправлять голосовые заказы"
        )
        return

    can_send, seconds_left = check_spam(user_id, 30)
    if not can_send:
        await update.message.reply_text(f"⏳ Подождите {seconds_left} сек.")
        return

    await forward_voice_to_staff(update, context, user_id)
    await update.message.reply_text(
        "✉️ <b>Заказ отправлен!</b>\n\n<i>Возможно мы с вами свяжемся, чтобы уточнить детали</i>.",
        parse_mode="HTML",
    )


# ================== ЗАПУСК БОТА ==================
def main():
    logger.info("Запуск main() | BOT_TOKEN присутствует: %s", bool(BOT_TOKEN))

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(90)
        .read_timeout(90)
        .write_timeout(90)
        .pool_timeout(90)
        .build()
    )

    application.add_handler(MessageHandler(filters.ALL, log_any_update), group=-1)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("backup", cmd_backup))
    application.add_handler(CommandHandler("sticker_id", get_sticker_id))
    application.add_handler(CommandHandler("client", cmd_client))

    # ВАЖНО: СНАЧАЛА обработчик админских callback (с паттерном), ПОТОМ общий
    application.add_handler(
        CallbackQueryHandler(
            handle_admin_callback,
            pattern="^(admin_|barista_|users_|back_to_|confirm_delete_|cancel_delete_|settings_|promotion_)",
        )
    )
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(
        CallbackQueryHandler(handle_broadcast_buttons, pattern="^broadcast_")
    )

    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: {context.error}\n{traceback.format_exc()}")

    application.add_error_handler(error_handler)

    # ========== ЕЖЕДНЕВНЫЙ ОТЧЁТ В 21:00 ПО ВЛАДИВОСТОКУ ==========
    from datetime import time as dt_time
    import pytz

    async def daily_report_callback(context: ContextTypes.DEFAULT_TYPE):
        """Отправляет ежедневный отчёт в 21:00 по Владивостоку"""
        vlad_tz = pytz.timezone("Asia/Vladivostok")
        now_vlad = datetime.now(vlad_tz)
        today_vladivostok = now_vlad.strftime("%Y-%m-%d")

        total_stamps, total_gifts = db.get_total_daily_stats(today_vladivostok)
        detailed_stats = db.get_daily_stats(today_vladivostok)

        logger.info(f"Формирование отчёта за {today_vladivostok} (Владивосток)")
        logger.info(f"Штампов: {total_stamps}, Подарков: {total_gifts}")

        report_text = f"Ежедневный отчёт\n{today_vladivostok}\n\n"
        report_text += f"Штампов: {total_stamps}\n"
        report_text += f"Подарков: {total_gifts}\n"

        if detailed_stats:
            report_text += "\n-----------------\n"
            for barista_username, stamps, gifts in detailed_stats:
                report_text += f"@{barista_username}: {stamps} шт, {gifts} под\n"

        recipients = set(ADMIN_IDS)

        baristas = db.get_all_baristas()
        for barista in baristas:
            username = barista[0]
            cursor = db.conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            if result:
                recipients.add(result[0])

        for recipient_id in recipients:
            try:
                await context.bot.send_message(chat_id=recipient_id, text=report_text)
                logger.info(f"Отчёт отправлен пользователю {recipient_id}")
            except Exception as e:
                logger.error(f"Не удалось отправить отчёт {recipient_id}: {e}")

    job_queue = application.job_queue
    if job_queue:
        vlad_tz = pytz.timezone("Asia/Vladivostok")
        now_vlad = datetime.now(vlad_tz)
        target_vlad = vlad_tz.localize(
            datetime(now_vlad.year, now_vlad.month, now_vlad.day, 21, 0, 0)
        )
        target_utc = target_vlad.astimezone(pytz.UTC)

        if target_utc < datetime.now(pytz.UTC):
            target_utc = target_utc + timedelta(days=1)

        job_queue.run_daily(
            daily_report_callback,
            time=dt_time(
                hour=target_utc.hour, minute=target_utc.minute, second=target_utc.second
            ),
            days=tuple(range(7)),
        )
        logger.info(
            f"Ежедневный отчёт настроен на 21:00 Владивосток (UTC {target_utc.hour}:{target_utc.minute})"
        )
    else:
        logger.warning("JobQueue не доступен, ежедневный отчёт не будет работать")
        # ========== БЭКАПЫ В ОТДЕЛЬНОМ ПОТОКЕ ==========
    import threading

    def backup_job():
        import schedule
        import time

        def cleanup_spam_dict():
            current_time = time.time()
            to_delete = [
                uid
                for uid, lt in client_last_message_time.items()
                if current_time - lt > 3600
            ]
            for uid in to_delete:
                del client_last_message_time[uid]
            if to_delete:
                logger.info(f"Очищено {len(to_delete)} записей из спам-словаря")

        schedule.every().day.at("04:00").do(db.backup_db)
        schedule.every().day.at("04:01").do(lambda: db.cleanup_old_backups(7))
        schedule.every().hour.do(cleanup_spam_dict)

        while True:
            schedule.run_pending()
            time.sleep(60)

    threading.Thread(target=backup_job, daemon=True).start()
    # =============================================

    logger.info("Запускаю polling...")
    print("🚀 Бот запускается...")

    application.run_polling(
        timeout=45,
        bootstrap_retries=-1,
        read_timeout=50,
        connect_timeout=50,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
