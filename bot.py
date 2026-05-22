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

# --- SOZLAMALAR ---
TOKEN = os.environ.get("BOT_TOKEN", "7957174866:AAGeLbH08tpnpi1lUdKevWe2lM98Qic1M6A")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyCpFIXo31H7BP6O0yKmHPyIBc-Sjp6H9TU")

ADMIN_ID = 362514006
CHANNEL = -1003843614474  

bot = telebot.TeleBot(TOKEN)

# --- MA'LUMOTLAR BAZASI (YANGILANDI) ---
def init_db():
    conn = sqlite3.connect('zakovat_tizimi.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS scores 
                      (user_id INTEGER, username TEXT, score INTEGER, date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS polls 
                      (poll_id TEXT PRIMARY KEY, correct_option INTEGER)''')
    # Chiqqan savollarni takrorlamaslik uchun yangi jadval
    cursor.execute('''CREATE TABLE IF NOT EXISTS sent_questions 
                      (question_text TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()
    logger.info("✅ Ma'lumotlar bazasi va nazorat tizimi tayyor")

# --- SAVOL OLDIN CHIQANINI TEKSHIRISH ---
def is_question_sent(question_text):
    conn = sqlite3.connect('zakovat_tizimi.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sent_questions WHERE question_text = ?", (question_text,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

# --- SAVOLNI BAZAGA QO'SHISH ---
def save_sent_question(question_text):
    try:
        conn = sqlite3.connect('zakovat_tizimi.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO sent_questions VALUES (?)", (question_text,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Savolni bazaga saqlashda xato: {e}")

# --- GEMINI AI (XATOSIZ VA YANGILANGAN FORMAT) ---
def get_ai_question():
    mavzular = [
        "Mantiqiy savollar", "Dunyo tarixi", "IT va Texnologiya", "San'at va Adabiyot", 
        "Geografiya va Sayyoralar", "Sport olami", "Koinot sirlari", "Biologiya va Tabiat",
        "Kimyo va Fizika qonunlari", "Mashhur shaxslar hayoti", "Iqtisodiyot va Biznes"
    ]
    
    # Har safar butunlay tasodifiy mavzu va qo'shimcha tasodifiy raqam beriladi (Gemini bir xil qaytarmasligi uchun)
    mavzu = random.choice(mavzular)
    random_modifier = random.randint(100, 9999)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt_text = f"""Siz professional Zakovat ekspertisiz. {mavzu} mavzusida o'ta qiziqarli, o'ylantiradigan yangi intellektual savol tuzing. (Identifikator: {random_modifier}).
    Javob mutloq va FAQAT quyidagi JSON formatda bo'lishi shart, hech qanday qo'shimcha matn yozmang:
    {{
      "question": "Savol matni bu yerda?",
      "options": ["Variant 1", "Variant 2", "Variant 3", "Variant 4"],
      "correct_index": 0,
      "explanation": "To'g'ri javobning qisqacha ilmiy yoki mantiqiy izohi"
    }}"""
    
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.95, 
            "responseMimeType": "application/json"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            ai_text = res_json['candidates'][0]['content']['parts'][0]['text']
            return json.loads(ai_text)
        else:
            logger.error(f"❌ Google API xato berdi, Status: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"❌ Gemini tizimida texnik xatolik: {e}")
        return None

# --- SAVOL YUBORISH VA TAKRORLANISH NAZORATI ---
def send_quiz():
    try:
        # Yangi va takrorlanmas savol topilguncha urinib ko'radi (maksimal 5 marta)
        data = None
        for _ in range(5):
            potential_data = get_ai_question()
            if potential_data and 'question' in potential_data:
                # Agar bu savol oldin kanalga chiqmagan bo'lsa, qabul qilamiz
                if not is_question_sent(potential_data['question']):
                    data = potential_data
                    break
                else:
                    logger.info(f"🔄 Takroriy savol aniqlandi, qayta so'ralmoqda: {potential_data['question']}")
        
        if not data:
            logger.error("❌ Yangi va takrorlanmas savol generatsiya qilib bo'lmadi.")
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
        
        # Kelajakda takrorlanmasligi uchun savol matnini bazaga yozib qo'yamiz
        save_sent_question(data['question'])
        
        # Poll javoblarini tekshirish uchun bazaga yozish
        conn = sqlite3.connect('zakovat_tizimi.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO polls VALUES (?, ?)", (msg.poll.id, data['correct_index']))
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Yangi savol kanalga chiqdi: {data['question']}")
        return True
    except Exception as e:
        logger.error(f"❌ Savol yuborishda umumiy xatolik: {e}")
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
    bot.reply_to(
        message, 
        "👋 Assalomu alaykum! Zakovat AI intellektual boshqaruv botiga xush kelibsiz.\n\n"
        "🤖 Bot har safar takrorlanmas va mutloq yangi savollarni generatsiya qilib kanalga uzatadi."
    )

@bot.message_handler(commands=['test'])
def test_handler(message):
    me = bot.get_me()
    bot.reply_to(
        message, 
        f"🚀 Bot holati: FAOL (Uzluksiz rejim)\n"
        f"🤖 Bot: @{me.username}\n"
        f"📢 Kanal ID: {CHANNEL}\n"
        f"👤 Sizning ID: {message.from_user.id}"
    )

@bot.message_handler(commands=['savol'])
def admin_savol(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "⏳ Google AI tizimidan takrorlanmas yangi savol olinmoqda...")
        if send_quiz():
            bot.send_message(message.chat.id, "✅ Mutloq yangi savol kanalga muvaffaqiyatli joylandi!")
        else:
            bot.send_message(message.chat.id, "❌ Savol yuborishda xatolik yuz berdi. Railway loglarini ko'ring.")
    else:
        bot.reply_to(message, f"⚠️ Bu buyruq faqat admin uchun!")

# --- SCHEDULER ---
def scheduled_quiz():
    send_quiz()

if __name__ == "__main__":
    init_db()
    scheduler = BackgroundScheduler(timezone="Asia/Tashkent")
    # Har kuni belgilangan soatlarda yangi savol yuboriladi
    for h in [9, 12, 15, 18, 21]:
        scheduler.add_job(scheduled_quiz, 'cron', hour=h, minute=0)
    scheduler.start()
    
    logger.info("🚀 Bot va takrorlanishni nazorat qiluvchi tizim ishga tushdi...")
    bot.infinity_polling()
