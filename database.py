import sqlite3
from datetime import datetime
import shutil, os
from pathlib import Path

class Database:
    def __init__(self, db_name='coffee_bot.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
        self.update_database_schema()

    def create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                purchases_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS baristas (
                username TEXT PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promotions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT DEFAULT 'Каждый 7-й напиток бесплатно',
                required_purchases INTEGER DEFAULT 7,
                description TEXT,
                is_active BOOLEAN DEFAULT 1
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_styles (
                user_id INTEGER PRIMARY KEY,
                style_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')    

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            INSERT OR IGNORE INTO promotions (name, required_purchases, description) 
            VALUES ('Каждый 7-й напиток бесплатно', 7, 'Покажите QR-код при каждой покупке')
        ''')
        
        self.conn.commit()
        print("✅ База данных инициализирована")

    def delete_user(self, user_id: int) -> bool:
        """Удаляет пользователя из базы данных"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"❌ Ошибка при удалении пользователя {user_id}: {e}")
            return False

    def find_user_by_phone_last4(self, last4_digits):
        """Ищет пользователя по последним 4 цифрам номера телефона"""
        cursor = self.conn.cursor()
        
        if not last4_digits.isdigit() or len(last4_digits) != 4:
            return None
        
        cursor.execute('SELECT user_id FROM users WHERE phone LIKE ?', (f'%{last4_digits}',))
        
        results = cursor.fetchall()
        
        if len(results) == 1:
            return results[0][0]
        elif len(results) > 1:
            return [row[0] for row in results]
        
        return None

    def update_user_phone(self, user_id, phone):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET phone = ? WHERE user_id = ?', (phone, user_id))
        self.conn.commit()
        return cursor.rowcount > 0
    
# ================== ПОЛЬЗОВАТЕЛИ (USERS) ==================
    def get_or_create_user(self, user_id, username="", first_name="", last_name=""):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name) 
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            self.conn.commit()
        return user_id

    def get_user_stats(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT purchases_count FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0

    def update_user_purchases(self, user_id, change):
        """Изменяет счётчик покупок с авто-обнулением при достижении акции"""
        promo = self.get_promotion()
        required = promo[2] if promo else 7

        cursor = self.conn.cursor()
        cursor.execute('SELECT purchases_count FROM users WHERE user_id = ?', (user_id,))
        current = cursor.fetchone()[0]
    
        new_val = current + change
    
        if change == +1 and new_val >= required:
            new_val = 0
    
        new_val = max(0, new_val)
    
        cursor.execute('UPDATE users SET purchases_count = ? WHERE user_id = ?', (new_val, user_id))
        self.conn.commit()
        return new_val

    def search_user_by_username(self, username):
        """Поиск пользователя по username"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username LIKE ?', (f'%{username}%',))
        return cursor.fetchall()

    def get_user_by_username_exact(self, username: str):
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id, username, first_name, last_name FROM users WHERE username = ? LIMIT 1', (username,))
        return cursor.fetchone()

# ================== БАРИСТЫ (BARISTAS) ==================
    def is_user_barista(self, username):
        if not username:
            return False
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM baristas WHERE username = ? AND is_active = 1', (username,))
        return cursor.fetchone() is not None

    def add_barista(self, username, first_name="", last_name=""):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO baristas (username, first_name, last_name) 
            VALUES (?, ?, ?)
        ''', (username, first_name, last_name))
        self.conn.commit()
        return True

    def remove_barista(self, username):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE baristas SET is_active = 0 WHERE username = ?', (username,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_all_baristas(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM baristas WHERE is_active = 1')
        return cursor.fetchall()
    
    def clean_invalid_baristas(self):
        """Удаляет некорректные записи бариста"""
        cursor = self.conn.cursor()
        invalid_usernames = ['Список', 'Удалить', 'Добавить', 'Назад', '📋 Список', '➖ Удалить', '➕ Добавить', '🔙 Назад']
        for username in invalid_usernames:
            cursor.execute('UPDATE baristas SET is_active = 0 WHERE username = ?', (username,))
        self.conn.commit()
        return True

# ================== АКЦИИ (PROMOTIONS) ==================
    def get_promotion(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM promotions WHERE is_active = 1 LIMIT 1')
        return cursor.fetchone()

    def update_promotion(self, required_purchases=None, description=None, name=None):
        cursor = self.conn.cursor()
        if required_purchases:
            cursor.execute('UPDATE promotions SET required_purchases = ? WHERE is_active = 1', (required_purchases,))
        if description:
            cursor.execute('UPDATE promotions SET description = ? WHERE is_active = 1', (description,))
        if name:
            cursor.execute('UPDATE promotions SET name = ? WHERE is_active = 1', (name,))
        self.conn.commit()

# ================== АДМИНЫ (ADMINS) ==================
    def add_admin(self, user_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO admins (user_id, is_active) VALUES (?, 1)', (user_id,))
        self.conn.commit()
        return True

    def remove_admin(self, user_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute('UPDATE admins SET is_active = 0 WHERE user_id = ?', (user_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def is_user_admin_db(self, user_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute('SELECT 1 FROM admins WHERE user_id = ? AND is_active = 1', (user_id,))
        return cursor.fetchone() is not None

    def get_all_admins(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id FROM admins WHERE is_active = 1')
        return [row[0] for row in cursor.fetchall()]
    
# ================== БЭКАП (BACKUP) ==================
    def backup_db(self) -> str:
        """Создаёт копию БД и возвращает путь до файла"""
        os.makedirs('backup', exist_ok=True)
        date_str = datetime.now().strftime('%Y-%m-%d_%H-%M')
        backup_path = f'backup/coffee_bot_{date_str}.db'
        main_db_path = self.conn.cursor().execute('PRAGMA database_list').fetchone()[2]
        shutil.copyfile(main_db_path, backup_path)
        return backup_path
    
    def cleanup_old_backups(self, keep=7):
        """Оставляет только keep последних копий"""
        try:
            files = sorted(Path('backup').glob('coffee_bot_*.db'))
            for f in files[:-keep]:
                f.unlink()
        except Exception:
            pass
    
    def get_all_users(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id, username, first_name, last_name, purchases_count, phone FROM users ORDER BY created_at DESC')
        return cursor.fetchall()
    
    def get_all_user_ids(self): 
        """Получить всех пользователей бота (только user_id для рассылки)"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        return [row[0] for row in cursor.fetchall()]
    
    def find_user_by_phone(self, phone_number):
        """Ищет пользователя по номеру телефона"""
        cursor = self.conn.cursor()
        normalized_phone = ''.join(filter(str.isdigit, phone_number))
        cursor.execute('SELECT user_id FROM users WHERE phone = ?', (normalized_phone,))
        result = cursor.fetchone()
        return result[0] if result else None
    
# ================== СТИЛИ ПРОГРЕСС-БАРА (PROGRESS BAR STYLES) ==================
    def save_user_style(self, user_id: int, style_index: int) -> bool:
        """Сохраняет выбранный стиль прогресс-бара для пользователя"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO user_styles (user_id, style_index) 
                VALUES (?, ?)
            ''', (user_id, style_index))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения стиля для {user_id}: {e}")
            return False

    def get_user_style(self, user_id: int) -> int:
        """Возвращает сохраненный стиль прогресс-бара пользователя"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('SELECT style_index FROM user_styles WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            print(f"❌ Ошибка получения стиля для {user_id}: {e}")
            return 0

    def get_user_style_if_exists(self, user_id: int):
        """Возвращает стиль или None если не установлен"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT style_index FROM user_styles WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def update_database_schema(self):
        """Обновляет структуру базы данных если нужно"""
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'phone' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN phone TEXT')
            self.conn.commit()
            print("✅ Добавлено поле phone в таблицу users")

    
