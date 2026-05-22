import os
import telebot
import requests
import json
import sqlite3
import random
import logging
import time
import re
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# --- LOGGING SOZLAMALARI ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- SOZLAMALAR ---
TOKEN = os.environ.get("BOT_TOKEN", "7957174866:AAGeLbH08tpnpi1lUdKevWe2lM98Qic1M6A")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyCpFIXo31H7BP6O0yKmHPyIBc-Sjp6H9TU")

ADMIN_ID = 8553158957  
CHANNEL = -1003843614474  

bot = telebot.TeleBot(TOKEN)

# --- MA'LUMOTLAR BAZASI ---
def init_db():
    conn = sqlite3.connect('zakovat_tizimi.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS scores 
                      (user_id INTEGER, username TEXT, score INTEGER, date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS polls 
                      (poll_id TEXT PRIMARY KEY, correct_option INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS sent_questions 
                      (question_text TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()
    logger.info("✅ Ma'lumotlar bazasi va nazorat tizimi tayyor")

# --- SAVOL OLDIN CHIQANINI TEKSHIRISH ---
def is_question_sent(question_text):
    conn = sqlite3.connect('zakovat_tizimi.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sent_questions WHERE question_text = ?", (question_text.strip(),))
    row = cursor.fetchone()
    conn.close()
    return row is not None

# --- SAVOLNI BAZAGA QO'SHISH ---
def save_sent_question(question_text):
    try:
        conn = sqlite3.connect('zakovat_tizimi.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO sent_questions VALUES (?)", (question_text.strip(),))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Savolni bazaga saqlashda xato: {e}")

# --- GEMINI AI (QAT'IY JSON SXEMA INTEGRATSIYASI) ---
def get_ai_question():
    # Kengaytirilgan va har xil mavzular ro'yxati
    mavzular = [
        "Mantiqiy va intellektual topishmoq", "Jahon tarixi va qiziqarli faktlar", 
        "Zamonaviy IT, texnologiyalar va kashfiyotlar", "Klassik san'at, kino va adabiyot", 
        "Sirli geografiya, davlatlar va urf-odatlar", "Sport tarixi va Olimpiada qiziqarli voqealari", 
        "Koinot, astronomiya va qora tuynuklar", "Biologiya, anatomiya va tabiat mo'jizalari",
        "Fizika qonunlari va kimyoviy parodokslar", "Mashhur shaxslarning yashirin hayotiy faktlari"
    ]
    
    mavzu = random.choice(mavzular)
    random_modifier = random.randint(10000, 999999)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt_text = f"""Siz tajribali Zakovat klubi muharririsiz. {mavzu} yo'nalishida o'ta qiziqarli, o'ylantiradigan, avval hech qayerda berilmagan mutloq yangi intellektual savol tuzing.
    Savol lo'nda, aniq va qiziqarli bo'lsin. Variantlar ichida faqat bittasi to'g'ri bo'lishi shart. Kod: {random_modifier}."""
    
    # Google API rad etolmaydigan qat'iy JSON sxemasi
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 1.0,  # Har xillikni (kreativlikni) maksimal qilish uchun
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "question": {"type": "STRING"},
                    "options": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                        "minItems": 4,
                        "maxItems": 4
                    },
                    "correct_index": {"type": "INTEGER"},
                    "explanation": {"type": "STRING"}
                },
                "required": ["question", "options", "correct_index", "explanation"]
            }
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        if response.status_code == 200:
            res_json = response.json()
            ai_text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            return json.loads(ai_text)
        else:
            logger.error(f"❌ Google API xato berdi. Status: {response.status_code}, Javob: {response.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Gemini tizimida xatolik: {e}")
        return None

# --- SAVOL YUBORISH VA NAZORAT TIZIMI ---
def send_quiz():
    try:
        data = None
        # Faqat sun'iy intellektdan yangi va takrorlanmas savol topguncha 5 marta urinadi
        for i in range(5):
            potential_data = get_ai_question()
            if potential_data and 'question' in potential_data:
                # Agar savol matni bazada bo'lmasa - qabul qilamiz
                if not is_question_sent(potential_data['question']):
                    data = potential_data
                    break
                else:
                    logger.info(f"🔄 Takroriy savol rad etildi, qayta urinish: {i+1}")
        
        # Agar qat'iy sxemaga qaramay Gemini'dan mutloq javob bo'lmasa, favqulodda xabar logga yoziladi
        if not data:
            logger.error("❌ Sun'iy intellektdan yangi savol olib bo'lmadi, API kalit yoki limitni tekshiring.")
            return False

        explanation = data.get('explanation', "To'g'ri javob!")[:190]
        
        msg = bot.send_poll(
            chat_id=CHANNEL,
            question=data['question'],
            options=data['options'],
            type='quiz',
            correct_option_id=data['correct_index'],
            explanation=explanation,
            is_anonymous=True  
        )
        
        # Kelajakda bu savol umuman qaytalanmasligi uchun bazaga yozamiz
        save_sent_question(data['question'])
        
        conn = sqlite3.connect('zakovat_tizimi.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO polls VALUES (?, ?)", (msg.poll.id, data['correct_index']))
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Kanalga mutloq yangi savol chiqdi: {data['question']}")
        return True
    except Exception as e:
        logger.error(f"❌ Savol yuborish tizimida kutilmagan xato: {e}")
        return False

# --- HANDLERS ---
@bot.poll_answer_handler()
def handle_poll_answer(answer):
    try:
        conn = sqlite3.connect('zakovat_tizimi.db')
        cursor = conn.cursor()
        cursor.execute("SELECT correct_option FROM polls WHERE poll_id = ?", (answer.poll_id,))
        row = cursor.fetchone()
        
        if row and len(answer.option_ids) > 0 and answer.option_ids[0] == row[0]:
            user_id = answer.user.id
            username = answer.user.username or answer.user.first_name or "Noma'lum"
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("INSERT INTO scores VALUES (?, ?, ?, ?)", (user_id, username, 1, today))
            conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Ball hisoblashda xato: {e}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.reply_to(message, "👋 Zakovat AI boshqaruv tizimi faol!\n\n🤖 Tizim har safar Gemini intellektidan mutloq yangi, takrorlanmas savollar generatsiya qiladi.")

@bot.message_handler(commands=['test'])
def test_handler(message):
    me = bot.get_me()
    bot.reply_to(message, f"🚀 Tizim holati: ONLAYN\n🤖 Bot: @{me.username}\n📢 Kanal: {CHANNEL}")

@bot.message_handler(commands=['savol'])
def admin_savol(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "⏳ Gemini AI tizimidan mutloq yangi va har xil mavzuda savol olinmoqda...")
        if send_quiz():
            bot.send_message(message.chat.id, "✅ Yangi savol kanalga muvaffaqiyatli joylashtirildi!")
        else:
            bot.send_message(message.chat.id, "❌ API ulanishda xato. Railway loglarini tekshiring yoki API kalit almashtiring.")
    else:
        bot.reply_to(message, "⚠️ Bu buyruq faqat bot egasi uchun!")

# --- SCHEDULER ---
def scheduled_quiz():
    send_quiz()

if __name__ == "__main__":
    init_db()
    scheduler = BackgroundScheduler(timezone="Asia/Tashkent")
    for h in [9, 12, 15, 18, 21]:
        scheduler.add_job(scheduled_quiz, 'cron', hour=h, minute=0)
    scheduler.start()
    
    logger.info("🚀 Bot cheksiz va har xil savollar rejimida ishga tushdi...")
    bot.infinity_polling()
