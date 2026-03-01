import gspread
from datetime import datetime
from database import Database
import threading
import time
import schedule
from dotenv import load_dotenv
import os

load_dotenv()

db = Database()

try:
    gc = gspread.service_account(filename="service-account.json")
    sh = gc.open_by_key("1-DEldh4_DJOlWm7zpUW6Mo-JlQ9eYiacr3Vt-UeBG38")
    
    try:
        wks = sh.worksheet("Клиенты")
    except gspread.exceptions.WorksheetNotFound:
        wks = sh.add_worksheet(title="Клиенты", rows=1000, cols=9)
        print("✅ Создан лист 'Клиенты'")
        
except Exception as e:
    print(f"❌ Ошибка подключения к Google Sheets: {e}")
    exit(1)

def export_users_to_google_sheets():
    """Экспортирует всех пользователей в Google Sheets"""
    try:
        users = db.get_all_users()
        
        print(f"📊 Получено {len(users)} пользователей из базы")
        
        header = [
            "ID",
            "Имя",
            "Номер",
            "@username",
            "Счётчик",
            "Подарков выдано",
            "Всего начислений",
            "Дата крайнего визита",
            "Дата регистрации"
        ]
        
        rows = [header]
        
        for user in users:
            try:
                user_id = user[0]
                username = user[1]
                first_name = user[2]
                last_name = user[3]
                purchases_now = user[4]
                phone = user[5]
                free_given = user[6] or 0
                total_purchases = user[7] or purchases_now
                last_visit = user[8]
                created_at = user[9]
                
                full_name = f"{first_name or ''} {last_name or ''}".strip()
                if not full_name:
                    if username and username.strip() and username != "Не указан":
                        full_name = username.replace('@', '').strip()
                    else:
                        full_name = "Без имени"
                
                phone_display = phone or ""
                
                username_display = ""
                if username and username.strip() and username != "Не указан":
                    if not username.startswith('@'):
                        username_display = f"@{username}"
                    else:
                        username_display = username
                
                purchases_display = purchases_now or 0
                free_display = free_given
                total_display = total_purchases
                
                last_visit_display = ""
                if last_visit:
                    try:
                        if isinstance(last_visit, datetime):
                            last_visit_display = last_visit.strftime("%Y-%m-%d %H:%M")
                        elif isinstance(last_visit, str):
                            last_visit_display = last_visit
                    except:
                        pass
                
                reg_date_display = ""
                if created_at:
                    try:
                        if isinstance(created_at, datetime):
                            reg_date_display = created_at.strftime("%Y-%m-%d %H:%M")
                        elif isinstance(created_at, str):
                            reg_date_display = created_at
                    except:
                        pass
                
                row = [
                    str(user_id),
                    str(full_name),
                    str(phone_display),
                    str(username_display),
                    int(purchases_display),
                    int(free_display),
                    int(total_display),
                    str(last_visit_display),
                    str(reg_date_display)
                ]
                
                rows.append(row)
                print(f"✓ {full_name}: тел.{phone_display}, покупок:{purchases_display}, подарков:{free_display}")
                
            except Exception as e:
                print(f"❌ Ошибка обработки пользователя {user_id if 'user_id' in locals() else 'unknown'}: {e}")
                continue
        
        if len(rows) > 1:
            print(f"📝 Записываю {len(rows)-1} пользователей в таблицу...")
            wks.clear()
            wks.update(values=rows, range_name='A1')
            
            total_free = 0
            total_all = 0
            for row in rows[1:]:
                try:
                    total_free += int(row[5]) if row[5] else 0
                    total_all += int(row[6]) if row[6] else 0
                except:
                    pass
            
            print(f"✅ Выгружено {len(rows)-1} клиентов в Google Sheets")
            print(f"🎁 Всего подарков выдано: {total_free}")
            print(f"☕ Всего начислений: {total_all}")
            print(f"🕒 Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("⚠️ Нет данных для экспорта")
        
    except Exception as e:
        print(f"❌ Критическая ошибка при экспорте: {e}")
        import traceback
        traceback.print_exc()

def schedule_auto_updates():
    """Настраивает автоматическое обновление"""
    
    schedule.every().day.at("04:00:30").do(export_users_to_google_sheets)
    
    schedule.every(2).hours.do(export_users_to_google_sheets)
    
    print("⏰ Планировщик обновлений Google Sheets запущен")
    print("📅 Автоматическое обновление в: 04:00:30 ежедневно")
    print("📅 Также каждые 2 часа")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    print("📤 Экспорт данных в Google Sheets...")
    export_users_to_google_sheets()
    
    print("🚀 Запуск автоматического обновления...")
    scheduler_thread = threading.Thread(target=schedule_auto_updates, daemon=True)
    scheduler_thread.start()
    
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("👋 Остановка планировщика...")