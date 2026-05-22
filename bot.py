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

# --- GEMINI AI (XATOSIZ STANDARD STRUKTURA) ---
def get_ai_question():
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
    
    prompt_text = f"""Siz tajribali Zakovat klubi muharririsiz. {mavzu} yo'nalishida o'ta qiziqarli, o'ylantiradigan, avval hech qayerda berilmagan mutloq yangi intellektual savol tuzing. Kod: {random_modifier}.
    Javobni FAQAT va FAQAT pastdagi JSON formatida qaytaring, hech qanday kirish yoki tushuntirish matni yozmang, markdown (```json) belgilarini ishlatmang:
    {{
      "question": "Savol matni shu yerda?",
      "options": ["Variant 1", "Variant 2", "Variant 3", "Variant 4"],
      "correct_index": 0,
      "explanation": "To'g'ri javobning qisqacha izohi"
    }}"""
    
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 1.0,
            "responseMimeType": "application/json"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        if response.status_code == 200:
            res_json = response.json()
            ai_text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            # Har ehtimolga qarshi ortiqcha belgilarni tozalash
            ai_text = re.sub(r'^```text|^```json|```$', '', ai_text, flags=re.MULTILINE).strip()
            return json.loads(ai_text)
        else:
            logger.error(f"❌ Google API Status: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"❌ Gemini xatoligi: {e}")
        return None

# --- SAVOL YUBORISH REJIMI ---
def send_quiz():
    try:
        data = None
        # Yangi va har xil savol topguncha 5 marta urinish
        for i in range(5):
            potential_data = get_ai_question()
            if potential_data and 'question' in potential_data and 'options' in potential_data:
                if not is_question_sent(potential_data['question']):
                    data = potential_data
                    break
                else:
                    logger.info(f"🔄 Takroriy savol chiqdi, tashlab yuborildi. Urinish: {i+1}")
        
        if not data:
            logger.error("❌ Sun'iy intellektdan mutloq yangi savol olib bo'lmadi.")
            return False

        explanation = data.get('explanation', "To'g'ri javob!")[:190]
        
        msg = bot.send_poll(
            chat_id=CHANNEL,
            question=data['question'],
            options=data['options'],
            type='quiz',
            correct_option_id=int(data['correct_index']),
            explanation=explanation,
            is_anonymous=True  
        )
        
        # Savolni eslab qolish mantiqi
        save_sent_question(data['question'])
        
        conn = sqlite3.connect('zakovat_tizimi.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO polls VALUES (?, ?)", (msg.poll.id, int(data['correct_index'])))
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Kanalga mutloq yangi savol chiqdi: {data['question']}")
        return True
    except Exception as e:
        logger.error(f"❌ Savol yuborish tizimida xato: {e}")
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
    bot.reply_to(message, "👋 Assalomu alaykum! Zakovat AI tizimi to'liq va xatosiz rejimda ishga tushdi.\n\n🤖 Bot endi faqat sun'iy intellektdan mutloq yangi va har xil savollarni oladi.")

@bot.message_handler(commands=['test'])
def test_handler(message):
    me = bot.get_me()
    bot.reply_to(message, f"🚀 Tizim: ONLAYN\n🤖 Bot: @{me.username}\n📢 Kanal: {CHANNEL}")

@bot.message_handler(commands=['savol'])
def admin_savol(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "⏳ Gemini AI tizimidan mutloq yangi va har xil mavzuda savol olinmoqda...")
        if send_quiz():
            bot.send_message(message.chat.id, "✅ Yangi savol kanalga muvaffaqiyatli joylashtirildi!")
        else:
            bot.send_message(message.chat.id, "❌ API ulanish yoki formatlashda xato bo'ldi. Railway loglarini tekshiring.")
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
    
    logger.info("🚀 Bot barqaror va cheksiz savollar rejimida ishga tushdi...")
    bot.infinity_polling()
