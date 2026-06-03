import sqlite3
from datetime import datetime
import shutil, os
from pathlib import Path
import logging
import pytz

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_name="coffee_bot.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
        self.update_database_schema()
        self.migrate_data()
        self.init_daily_stats_table()
        self.init_reviews_table()
        self.init_review_clicks_table()
        self.user_contexts = {}

    def create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                purchases_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS baristas (
                username TEXT PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promotions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT DEFAULT 'Каждый 7-й напиток бесплатно',
                required_purchases INTEGER DEFAULT 7,
                description TEXT,
                is_active BOOLEAN DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_styles (
                user_id INTEGER PRIMARY KEY,
                style_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            INSERT OR IGNORE INTO promotions (name, required_purchases, description) 
            VALUES ('Каждый 7-й напиток бесплатно', 7, 'Покажите QR-код при каждой покупке')
        """)

        self.conn.commit()

    def update_database_schema(self):
        """Обновляет структуру базы данных, добавляя новые поля"""
        cursor = self.conn.cursor()

        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        new_columns = {
            "free_drinks_given": "INTEGER DEFAULT 0",
            "total_purchases": "INTEGER DEFAULT 0",
            "last_visit": "TIMESTAMP",
        }

        for column_name, column_type in new_columns.items():
            if column_name not in columns:
                cursor.execute(
                    f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"
                )
                logger.info(f"Добавлено поле {column_name} в таблицу users")

        self.conn.commit()

    def migrate_data(self):
        """Переносит существующие данные в новые поля"""
        cursor = self.conn.cursor()

        cursor.execute(
            "UPDATE users SET free_drinks_given = 0 WHERE free_drinks_given IS NULL"
        )

        cursor.execute(
            "UPDATE users SET total_purchases = purchases_count WHERE total_purchases IS NULL"
        )

        cursor.execute(
            "UPDATE users SET last_visit = created_at WHERE last_visit IS NULL"
        )

        self.conn.commit()

    def delete_user(self, user_id: int) -> bool:
        cursor = self.conn.cursor()
        try:
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            self.conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Пользователь {user_id} удалён")
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при удалении пользователя {user_id}: {e}")
            return False

    def find_user_by_phone_last4(self, last4_digits):
        cursor = self.conn.cursor()

        if not last4_digits.isdigit() or len(last4_digits) != 4:
            return None

        cursor.execute(
            "SELECT user_id FROM users WHERE phone LIKE ?", (f"%{last4_digits}",)
        )

        results = cursor.fetchall()

        if len(results) == 1:
            return results[0][0]
        elif len(results) > 1:
            return [row[0] for row in results]

        return None

    def update_user_phone(self, user_id, phone):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_or_create_user(self, user_id, username="", first_name="", last_name=""):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

        if not user:
            cursor.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name) 
                VALUES (?, ?, ?, ?)
            """,
                (user_id, username, first_name, last_name),
            )
            self.conn.commit()
            logger.debug(f"Создан новый пользователь: user_id={user_id}")
        return user_id

    def get_user_stats(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT purchases_count FROM users WHERE user_id = ?", (user_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else 0

    def update_user_purchases(self, user_id, change):
        promo = self.get_promotion()
        required = promo[2] if promo else 7

        cursor = self.conn.cursor()

        cursor.execute(
            "SELECT purchases_count, total_purchases, free_drinks_given FROM users WHERE user_id = ?",
            (user_id,),
        )
        result = cursor.fetchone()

        if not result:
            return 0, False

        current = result[0]
        total = result[1] or 0
        free_given = result[2] or 0

        new_val = current + change

        was_gift = False

        if change == +1:
            total += 1
            if new_val >= required:
                new_val = 0
                free_given += 1
                was_gift = True

        new_val = max(0, new_val)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            UPDATE users 
            SET purchases_count = ?, 
                total_purchases = ?, 
                free_drinks_given = ?,
                last_visit = ?
            WHERE user_id = ?
        """,
            (new_val, total, free_given, now, user_id),
        )

        self.conn.commit()

        if was_gift:
            logger.info(f"Выдан подарок пользователю {user_id}")

        return new_val, was_gift

    def search_user_by_username(self, username):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username LIKE ?", (f"%{username}%",))
        return cursor.fetchall()

    def get_user_by_username_exact(self, username: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT user_id, username, first_name, last_name FROM users WHERE username = ? LIMIT 1",
            (username,),
        )
        return cursor.fetchone()

    def is_user_barista(self, username):
        if not username:
            return False
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM baristas WHERE username = ? AND is_active = 1", (username,)
        )
        return cursor.fetchone() is not None

    def add_barista(self, username, first_name="", last_name=""):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO baristas (username, first_name, last_name) 
            VALUES (?, ?, ?)
        """,
            (username, first_name, last_name),
        )
        self.conn.commit()
        logger.info(f"Добавлен бариста @{username}")
        return True

    def remove_barista(self, username):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE baristas SET is_active = 0 WHERE username = ?", (username,)
        )
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Удалён бариста @{username}")
        return cursor.rowcount > 0

    def get_all_baristas(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM baristas WHERE is_active = 1")
        return cursor.fetchall()

    def clean_invalid_baristas(self):
        cursor = self.conn.cursor()
        invalid_usernames = [
            "Список",
            "Удалить",
            "Добавить",
            "Назад",
            "📋 Список",
            "➖ Удалить",
            "➕ Добавить",
            "🔙 Назад",
        ]
        for username in invalid_usernames:
            cursor.execute(
                "UPDATE baristas SET is_active = 0 WHERE username = ?", (username,)
            )
        self.conn.commit()
        return True

    def get_promotion(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM promotions WHERE is_active = 1 LIMIT 1")
        return cursor.fetchone()

    def update_promotion(self, required_purchases=None, description=None, name=None):
        cursor = self.conn.cursor()
        if required_purchases:
            cursor.execute(
                "UPDATE promotions SET required_purchases = ? WHERE is_active = 1",
                (required_purchases,),
            )
            logger.info(f"Обновлено условие акции: {required_purchases} покупок")
        if description:
            cursor.execute(
                "UPDATE promotions SET description = ? WHERE is_active = 1",
                (description,),
            )
            logger.info(f"Обновлено описание акции")
        if name:
            cursor.execute(
                "UPDATE promotions SET name = ? WHERE is_active = 1", (name,)
            )
            logger.info(f"Обновлено название акции: {name}")
        self.conn.commit()

    def add_admin(self, user_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO admins (user_id, is_active) VALUES (?, 1)",
            (user_id,),
        )
        self.conn.commit()
        logger.info(f"Добавлен администратор {user_id}")
        return True

    def remove_admin(self, user_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("UPDATE admins SET is_active = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Удалён администратор {user_id}")
        return cursor.rowcount > 0

    def is_user_admin_db(self, user_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM admins WHERE user_id = ? AND is_active = 1", (user_id,)
        )
        return cursor.fetchone() is not None

    def get_all_admins(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT user_id FROM admins WHERE is_active = 1")
        return [row[0] for row in cursor.fetchall()]

    def backup_db(self) -> str:
        os.makedirs("backup", exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
        backup_path = f"backup/coffee_bot_{date_str}.db"
        main_db_path = self.conn.cursor().execute("PRAGMA database_list").fetchone()[2]
        shutil.copyfile(main_db_path, backup_path)
        logger.info(f"Создана резервная копия: {backup_path}")
        return backup_path

    def cleanup_old_backups(self, keep=7):
        try:
            files = sorted(Path("backup").glob("coffee_bot_*.db"))
            deleted = 0
            for f in files[:-keep]:
                f.unlink()
                deleted += 1
            if deleted:
                logger.info(f"Удалено {deleted} старых резервных копий")
        except Exception as e:
            logger.warning(f"Ошибка при очистке бэкапов: {e}")

    def get_all_users(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                user_id, 
                username, 
                first_name, 
                last_name, 
                purchases_count, 
                phone,
                free_drinks_given,
                total_purchases,
                last_visit,
                created_at
            FROM users 
            ORDER BY created_at DESC
        """)
        return cursor.fetchall()

    def get_all_user_ids(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in cursor.fetchall()]

    def find_user_by_phone(self, phone_number):
        cursor = self.conn.cursor()
        normalized_phone = "".join(filter(str.isdigit, phone_number))
        cursor.execute("SELECT user_id FROM users WHERE phone = ?", (normalized_phone,))
        result = cursor.fetchone()
        return result[0] if result else None

    def save_user_style(self, user_id: int, style_index: int) -> bool:
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO user_styles (user_id, style_index) 
                VALUES (?, ?)
            """,
                (user_id, style_index),
            )
            self.conn.commit()
            logger.debug(f"Сохранён стиль {style_index} для пользователя {user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения стиля для {user_id}: {e}")
            return False

    def get_user_style(self, user_id: int) -> int:
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT style_index FROM user_styles WHERE user_id = ?", (user_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Ошибка получения стиля для {user_id}: {e}")
            return 0

    def get_user_style_if_exists(self, user_id: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT style_index FROM user_styles WHERE user_id = ?", (user_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def init_daily_stats_table(self):
        """Создаёт таблицу для ежедневной статистики"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                barista_username TEXT NOT NULL,
                stamps INTEGER DEFAULT 0,
                gifts INTEGER DEFAULT 0,
                UNIQUE(date, barista_username)
            )
        """)
        self.conn.commit()
        logger.debug("Таблица daily_stats инициализирована")

    def add_daily_stamp(self, barista_username: str, date: str = None):
        """Увеличивает счётчик штампов для баристы за сегодня (по Владивостоку)"""
        if date is None:
            import pytz

            vlad_tz = pytz.timezone("Asia/Vladivostok")
            date = datetime.now(vlad_tz).strftime("%Y-%m-%d")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO daily_stats (date, barista_username, stamps, gifts)
            VALUES (?, ?, 1, 0)
            ON CONFLICT(date, barista_username) DO UPDATE SET
            stamps = stamps + 1
        """,
            (date, barista_username),
        )
        self.conn.commit()
        logger.debug(f"Добавлен штамп для @{barista_username} за {date}")

    def add_daily_gift(self, barista_username: str, date: str = None):
        """Увеличивает счётчик подарков для баристы за сегодня (по Владивостоку)"""
        if date is None:
            import pytz

            vlad_tz = pytz.timezone("Asia/Vladivostok")
            date = datetime.now(vlad_tz).strftime("%Y-%m-%d")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO daily_stats (date, barista_username, stamps, gifts)
            VALUES (?, ?, 0, 1)
            ON CONFLICT(date, barista_username) DO UPDATE SET
            gifts = gifts + 1
        """,
            (date, barista_username),
        )
        self.conn.commit()
        logger.debug(f"Добавлен подарок для @{barista_username} за {date}")

    def remove_daily_stamp(self, barista_username: str, date: str = None):
        """Уменьшает счётчик штампов для баристы (при отмене) - по Владивостоку"""
        if date is None:
            import pytz

            vlad_tz = pytz.timezone("Asia/Vladivostok")
            date = datetime.now(vlad_tz).strftime("%Y-%m-%d")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE daily_stats 
            SET stamps = stamps - 1 
            WHERE date = ? AND barista_username = ?
        """,
            (date, barista_username),
        )
        self.conn.commit()
        logger.debug(f"Удалён штамп для @{barista_username} за {date}")

    def get_daily_stats(self, date: str = None):
        """Возвращает статистику за день по всем баристам (по Владивостоку)"""
        if date is None:
            import pytz

            vlad_tz = pytz.timezone("Asia/Vladivostok")
            date = datetime.now(vlad_tz).strftime("%Y-%m-%d")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT barista_username, stamps, gifts 
            FROM daily_stats 
            WHERE date = ?
        """,
            (date,),
        )
        return cursor.fetchall()

    def get_total_daily_stats(self, date: str = None):
        """Возвращает общую статистику за день (суммарно по всем баристам) - по Владивостоку"""
        if date is None:
            import pytz

            vlad_tz = pytz.timezone("Asia/Vladivostok")
            date = datetime.now(vlad_tz).strftime("%Y-%m-%d")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT SUM(stamps), SUM(gifts) 
            FROM daily_stats 
            WHERE date = ?
        """,
            (date,),
        )
        result = cursor.fetchone()
        total_stamps = result[0] or 0
        total_gifts = result[1] or 0
        logger.debug(
            f"Статистика за {date}: штампов={total_stamps}, подарков={total_gifts}"
        )
        return total_stamps, total_gifts

    # Добавьте этот метод в класс Database в database.py

    def init_reviews_table(self):
        """Создаёт таблицу для отзывов"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                review_text TEXT NOT NULL,
                is_anonymous INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()
        logger.debug("Таблица reviews инициализирована")

    def save_review(
        self, user_id: int, review_text: str, is_anonymous: bool = False
    ) -> bool:
        """Сохраняет отзыв пользователя"""
        cursor = self.conn.cursor()

        # Получаем данные пользователя
        cursor.execute(
            "SELECT username, first_name, last_name, phone FROM users WHERE user_id = ?",
            (user_id,),
        )
        user_info = cursor.fetchone()

        username = user_info[0] if user_info else None
        first_name = user_info[1] if user_info else None
        last_name = user_info[2] if user_info else None
        phone = user_info[3] if user_info else None

        cursor.execute(
            """
            INSERT INTO reviews (user_id, username, first_name, last_name, phone, review_text, is_anonymous)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                user_id,
                username,
                first_name,
                last_name,
                phone,
                review_text,
                1 if is_anonymous else 0,
            ),
        )

        self.conn.commit()
        logger.info(f"Сохранён отзыв от user_id={user_id}, anonymous={is_anonymous}")
        return True

    def has_user_reviewed_recently(self, user_id: int, days: int = 30) -> bool:
        """Проверяет, оставлял ли пользователь отзыв за последние N дней"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM reviews 
            WHERE user_id = ? 
            AND created_at >= DATE('now', ?)
            LIMIT 1
        """,
            (user_id, f"-{days} days"),
        )
        result = cursor.fetchone()
        return result is not None

    def get_last_review_date(self, user_id: int):
        """Возвращает дату последнего отзыва пользователя"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT created_at FROM reviews 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 1
        """,
            (user_id,),
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def get_all_reviews_for_staff(self, limit: int = 50):
        """Получает последние отзывы для персонала"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, user_id, username, first_name, last_name, phone, review_text, is_anonymous, created_at
            FROM reviews 
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (limit,),
        )
        return cursor.fetchall()

    def init_review_clicks_table(self):
        """Создаёт таблицу для отслеживания нажатий на кнопки отзывов"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS review_clicks (
                user_id INTEGER PRIMARY KEY,
                yandex_clicked INTEGER DEFAULT 0,
                gis_clicked INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()
        logger.debug("Таблица review_clicks инициализирована")

    def save_review_click(self, user_id: int, platform: str) -> bool:
        """Сохраняет факт нажатия на кнопку отзыва (yandex или gis)"""
        cursor = self.conn.cursor()

        if platform == "yandex":
            cursor.execute(
                """
                INSERT INTO review_clicks (user_id, yandex_clicked, updated_at)
                VALUES (?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                yandex_clicked = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
                (user_id,),
            )
        elif platform == "gis":
            cursor.execute(
                """
                INSERT INTO review_clicks (user_id, gis_clicked, updated_at)
                VALUES (?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                gis_clicked = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
                (user_id,),
            )
        else:
            return False

        self.conn.commit()
        logger.info(f"Сохранён клик на {platform} для user_id={user_id}")
        return True

    def get_review_clicks(self, user_id: int):
        """Возвращает статус нажатий на кнопки для пользователя"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT yandex_clicked, gis_clicked 
            FROM review_clicks 
            WHERE user_id = ?
        """,
            (user_id,),
        )
        result = cursor.fetchone()
        if result:
            return {"yandex": result[0] == 1, "gis": result[1] == 1}
        return {"yandex": False, "gis": False}

    def has_user_completed_all_reviews(self, user_id: int) -> bool:
        """Проверяет, нажал ли пользователь на все кнопки отзывов"""
        clicks = self.get_review_clicks(user_id)
        return clicks["yandex"] and clicks["gis"]

    def should_show_review_prompt(self, user_id: int) -> bool:
        """
        Определяет, нужно ли показывать пользователю предложение оставить отзыв.
        Показываем, если не нажаты обе кнопки.
        """
        clicks = self.get_review_clicks(user_id)
        return not (clicks["yandex"] and clicks["gis"])

    def get_missing_review_buttons(self, user_id: int) -> list:
        """Возвращает список кнопок, которые пользователь ещё не нажал"""
        clicks = self.get_review_clicks(user_id)
        missing = []
        if not clicks["yandex"]:
            missing.append("yandex")
        if not clicks["gis"]:
            missing.append("gis")
        return missing
