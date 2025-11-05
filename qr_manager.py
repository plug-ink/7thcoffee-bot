import qrcode
import io
import re
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from PIL import Image, ImageDraw, ImageFont
import random

def generate_qr_code(user_id: int) -> io.BytesIO:
    """Генерирует QR-код для пользователя с простым дизайном"""
    qr_data = f"coffeerina:{user_id}"
    
    # Создаем QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    # Создаем простое изображение QR-кода
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Создаем простой фон
    width, height = 300, 400
    background = Image.new('RGB', (width, height), color='#F5F5F5')  # Светло-серый фон
    
    # Вставляем QR-код в центр
    qr_size = 250
    qr_img = qr_img.resize((qr_size, qr_size))
    
    # Создаем белый фон для QR-кода
    qr_bg = Image.new('RGB', (qr_size + 20, qr_size + 20), color='white')
    qr_bg.paste(qr_img, (10, 10))
    
    # Вставляем QR-код на фон
    qr_x = (width - qr_size - 20) // 2
    qr_y = 50
    background.paste(qr_bg, (qr_x, qr_y))
    
    # Добавляем простой текст
    draw = ImageDraw.Draw(background)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except:
        font = ImageFont.load_default()
    
    # Текст "CoffeeRina"
    text_color = '#333333'  # Темно-серый
    text = "CoffeeRina"
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_x = (width - text_width) // 2
    draw.text((text_x, 20), text, fill=text_color, font=font)
    
    # Текст "Ваш персональный QR-код"
    try:
        small_font = ImageFont.truetype("arial.ttf", 12)
    except:
        small_font = ImageFont.load_default()
    
    small_text = "Ваш персональный QR-код"
    small_text_bbox = draw.textbbox((0, 0), small_text, font=small_font)
    small_text_width = small_text_bbox[2] - small_text_bbox[0]
    small_text_x = (width - small_text_width) // 2
    draw.text((small_text_x, qr_y + qr_size + 20), small_text, fill=text_color, font=small_font)
    
    # Сохраняем в BytesIO
    bio = io.BytesIO()
    background.save(bio, 'PNG')
    bio.seek(0)
    return bio

def parse_qr_data(qr_text: str):
    """
    Парсит данные из текста QR-кода
    Формат: coffeerina:123456
    """
    match = re.match(r'coffeerina:(\d+)', qr_text.strip())
    if match:
        return int(match.group(1))
    return None

def read_qr_from_image(image_data: bytes):
    """
    Распознает QR-код с изображения.
    Возвращает сырой текст QR (str) либо None, если распознать не удалось.
    """
    try:
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Попытка 1: pyzbar на исходном изображении
        if img is not None:
            decoded_objects = decode(img)
            if decoded_objects:
                return decoded_objects[0].data.decode('utf-8')

        # Попытка 2: OpenCV QRCodeDetector
        if img is not None:
            detector = cv2.QRCodeDetector()
            data, points, _ = detector.detectAndDecode(img)
            if points is not None and data:
                return data

        # Попытка 3: pyzbar на оттенках серого
        if img is not None:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            decoded_objects = decode(gray)
            if decoded_objects:
                return decoded_objects[0].data.decode('utf-8')

        # Попытка 4: PIL
        image = Image.open(io.BytesIO(image_data))
        decoded_objects = decode(image)
        if decoded_objects:
            return decoded_objects[0].data.decode('utf-8')

        if data and is_valid_qr_format(data):
            return data
        else:
            print(f"❌ Неверный формат QR-кода: {data}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка распознавания QR: {e}")
        return None

def is_valid_qr_format(qr_text: str) -> bool:
    """Проверяет, соответствует ли текст формату нашего QR-кода"""
    return bool(re.match(r'coffeerina:\d+', qr_text.strip()))