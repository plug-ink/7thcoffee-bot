import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

# Поддержка нескольких админов: ADMIN_IDS="123,456" или старый формат ADMIN_ID
admin_ids_env = os.getenv('ADMIN_IDS') or os.getenv('ADMIN_ID', '')
ADMIN_IDS = []
for part in str(admin_ids_env).replace(' ', '').split(','):
    if part:
        try:
            ADMIN_IDS.append(int(part))
        except ValueError:
            pass

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

print("✅ Конфигурация загружена успешно!")