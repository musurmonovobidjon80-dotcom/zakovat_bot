import os
import telebot
import requests
import json
import sqlite3
import random
import logging
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# --- LOGGING SOZLAMALARI ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- SOZLAMALAR (Railway o'zgaruvchilaridan o'qiydi) ---
TOKEN = os.environ.get("BOT_TOKEN", "7957174866:AAGeLbH08tpnpi1lUdKevWe2lM98Qic1M6A")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyCpFIXo31H7BP6O0yKmHPyIBc-Sjp6H9TU")

ADMIN_ID = 362514006
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
    conn.commit()
    conn.close()
    logger.info("✅ Ma'lumotlar bazasi tayyor")

# --- BACKUP SAVOLLAR ---
BACKUP_QUESTIONS = [
    {
        "question": "Quyosh sistemasida eng katta sayyora qaysi?",
        "options": ["Yupiter", "Saturn", "Neptun", "Uran"],
        "correct_index": 0,
        "explanation": "Yupiter Quyosh sistemasidagi eng katta sayyora hisoblanadi."
    },
    {
        "question": "Insonning eng kuchli mushagi qaysi?",
        "options": ["Yurak", "Jag' mushagi", "Boldir", "Dumba mushagi"],
        "correct_index": 1,
        "explanation": "Jag' mushagi (masseter) insonning eng kuchli mushagidir."
    }
]

def get_backup_question():
    return random.choice(BACKUP_QUESTIONS)

# --- GEMINI AI ---
def get_ai_question():
    mavzular = ["Mantiq", "Tarix", "IT", "San'at", "Geografiya", "Sport", "Koinot", "Biologiya"]
    mavzu = random.choice(mavzular)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt_text = f"""Zakovat bot uchun {mavzu} mavzusida qiziqarli savol tuzing.
    Javob FAQAT JSON formatda bo'lsin:
    {{
      "question": "Savol?",
      "options": ["V1", "V2", "V3", "V4"],
      "correct_index": 0,
      "explanation": "Izoh"
    }}"""
    
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.9, "responseMimeType": "application/json"}
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            ai_text = res_json['candidates'][0]['content']['parts'][0]['text']
            return json.loads(ai_text)
        return None
    except Exception as e:
        logger.error(f"❌ Gemini xatosi: {e}")
        return None

# --- SAVOL YUBORISH ---
def send_quiz():
    try:
        data = get_ai_question()
        if not data:
            data = get_backup_question()
        
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
        
        # Bazaga saqlash
        conn = sqlite3.connect('zakovat_tizimi.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO polls VALUES (?, ?)", (msg.poll.id, data['correct_index']))
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Savol yuborildi: {msg.poll.id}")
        return True
    except Exception as e:
        logger.error(f"❌ Xato: {e}")
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

@bot.message_handler(commands=['savol'])
def admin_savol(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "⏳ Savol kanalga yuborilmoqda...")
        if send_quiz():
            bot.send_message(message.chat.id, "✅ Savol chiqdi!")
        else:
            bot.send_message(message.chat.id, "❌ Xato! Bot adminligini tekshiring.")

@bot.message_handler(commands=['test'])
def test_handler(message):
    if message.from_user.id == ADMIN_ID:
        me = bot.get_me()
        bot.reply_to(message, f"🤖 @{me.username} ishlamoqda\n📢 Kanal ID: {CHANNEL}")

# --- SCHEDULER ---
def scheduled_quiz():
    send_quiz()

if __name__ == "__main__":
    init_db()
    scheduler = BackgroundScheduler(timezone="Asia/Tashkent")
    for h in [9, 12, 15, 18, 21]:
        scheduler.add_job(scheduled_quiz, 'cron', hour=h, minute=0)
    scheduler.start()
    
    logger.info("🚀 Bot va Scheduler ishga tushdi...")
    bot.infinity_polling()
