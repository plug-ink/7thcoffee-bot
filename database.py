import sqlite3
from datetime import datetime
import shutil, os
from pathlib import Path

class Database:
    def __init__(self, db_name='coffee_bot.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Пользователи (клиенты)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                purchases_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Баристы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS baristas (
                username TEXT PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Настройки акции
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promotions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT DEFAULT 'Каждый 7-й напиток бесплатно',
                required_purchases INTEGER DEFAULT 7,
                description TEXT,
                is_active BOOLEAN DEFAULT 1
            )
        ''')

        # Администраторы (дополнительно к .env)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Добавляем акцию по умолчанию
        cursor.execute('''
            INSERT OR IGNORE INTO promotions (name, required_purchases, description) 
            VALUES ('Каждый 7-й напиток бесплатно', 7, 'Покажите QR-код при каждой покупке')
        ''')
        
        self.conn.commit()
        print("✅ База данных инициализирована")

    # === ПОЛЬЗОВАТЕЛИ ===
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
        """Изменяет счётчик покупок (+1 или -1) с авто-обнулением при достижении акции"""
        promo = self.get_promotion()
        required = promo[2] if promo else 7

        cursor = self.conn.cursor()
    # текущее значение
        cursor.execute('SELECT purchases_count FROM users WHERE user_id = ?', (user_id,))
        current = cursor.fetchone()[0]

    # новое значение
        new_val = max(0, current + change)

    # если ДОБАВЛЯЕМ +1 и достигли лимита → обнуляем
        if change == +1 and new_val >= required:
            cursor.execute('UPDATE users SET purchases_count = 0 WHERE user_id = ?', (user_id,))
            self.conn.commit()
            return 0

         # иначе – просто пишем новое число
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

    # === БАРИСТЫ ===
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
        # Удаляем записи с некорректными username
        invalid_usernames = ['Список', 'Удалить', 'Добавить', 'Назад', '📋 Список', '➖ Удалить', '➕ Добавить', '🔙 Назад']
        for username in invalid_usernames:
            cursor.execute('UPDATE baristas SET is_active = 0 WHERE username = ?', (username,))
        self.conn.commit()
        return True

    # === АКЦИИ ===
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

    # === АДМИНЫ ===
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
    
        # === БЭКАП ===

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
            for f in files[:-keep]:  # удаляем всё, кроме последних keep
                f.unlink()
        except Exception:
            pass  # молчим, если не получилось
    
    def get_all_users(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id, username, first_name, last_name, purchases_count FROM users ORDER BY created_at DESC')
        return cursor.fetchall()
    
    def get_all_user_ids(self): 
        """Получить всех пользователей бота (только user_id для рассылки)"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        return [row[0] for row in cursor.fetchall()]  # ← возвращаем список ID

    
