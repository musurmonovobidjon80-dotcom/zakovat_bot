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

# --- 30 TA TAYYOR ZAXIRA SAVOLLAR (TAKRORLANMASLIK FILTRI BILAN) ---
BACKUP_QUESTIONS = [
    {"question": "Quyosh sistemasida eng katta sayyora qaysi?", "options": ["Yupiter", "Saturn", "Neptun", "Uran"], "correct_index": 0, "explanation": "Yupiter Quyosh sistemasidagi eng katta sayyora hisoblanadi."},
    {"question": "Insonning eng kuchli mushagi qaysi?", "options": ["Yurak", "Jag' mushagi", "Boldir", "Dumba mushagi"], "correct_index": 1, "explanation": "Jag' mushagi (masseter) insonning eng kuchli mushagidir."},
    {"question": "Dunyodagi eng chuqur ko'l qaysi?", "options": ["Kaspiy", "Baykal", "Viktoriya", "Tanganika"], "correct_index": 1, "explanation": "Baykal ko'li dunyodagi eng chuqur chuchuk suvli ko'ldir."},
    {"question": "Birinchi elektron hisoblash mashinasi (EHM) qaysi yil yaratilgan?", "options": ["1936-yil", "1946-yil", "1953-yil", "1961-yil"], "correct_index": 1, "explanation": "Dunyodagi birinchi elektron kompyuter ENIAC 1946-yilda AQSHda yaratilgan."},
    {"question": "Qaysi davlat hududida eng ko'p vaqt mintaqalari joylashgan?", "options": ["Rossiya", "AQSH", "Fransiya", "Kanada"], "correct_index": 2, "explanation": "Fransiyaning chet eldagi hududlari bilan birga jami 12 ta vaqt mintaqasi bor."},
    {"question": "Inson tanasidagi eng kichik suyak qayerda joylashgan?", "options": ["Burunda", "Quloqda", "Barmoqda", "Ko'zda"], "correct_index": 1, "explanation": "Inson tanasidagi eng kichik suyak o'rta quloqdagi uzangisimon suyakdir."},
    {"question": "Dunyodagi eng uzun daryo qaysi?", "options": ["Amazonka", "Nil", "Missisipi", "Yanszi"], "correct_index": 1, "explanation": "Nil daryosi dunyodagi eng uzun daryo hisoblanadi (6650 km)."},
    {"question": "Fransiyaning poytaxti Parij shahrida joylashgan mashhur minora qaysi?", "options": ["Piza", "Eymor", "Eyfel", "Big Ben"], "correct_index": 2, "explanation": "Eyfel minorasi Parijning ramziy me'moriy yodgorligidir."},
    {"question": "Qaysi element kimyoviy elementlar davriy jadvalida birinchi bo'lib turadi?", "options": ["Geliy", "Kislorod", "Azot", "Vodorod"], "correct_index": 3, "explanation": "Vodorod eng engil element bo'lib, davriy jadvalda 1-raqamda turadi."},
    {"question": "Yer yuzida eng ko'p tarqalgan gaz qaysi?", "options": ["Kislorod", "Azot", "Karbonat angidrid", "Vodorod"], "correct_index": 1, "explanation": "Yer atmosferasining qariyb 78 foizini azot gazi tashkil qiladi."},
    {"question": "Dunyodagi eng katta okean qaysi?", "options": ["Atlantika", "Hind", "Tinch", "Shimaliy Muz"], "correct_index": 2, "explanation": "Tinch okeani maydoni bo'yicha dunyodagi eng katta okeandir."},
    {"question": "Shaxmat taxtasida jami nechta kvadrat kataklar bor?", "options": ["32 ta", "48 ta", "64 ta", "81 ta"], "correct_index": 2, "explanation": "Shaxmat taxtasi 8x8 o'lchamda bo'lib, jami 64 ta katakdan iborat."},
    {"question": "Internet tarmog'i dastlab qaysi tashkilot tomonidan ishlab chiqilgan?", "options": ["NASA", "Pentagon", "CERN", "Microsoft"], "correct_index": 1, "explanation": "Internet ARPANET loyihasi ostida AQSH Mudofaa vazirligi tomonidan yaratilgan."},
    {"question": "Kompyuterning miyasi hisoblangan va barcha amallarni bajaradigan qurilma nima?", "options": ["Operativ xotira", "Qattiq disk", "Prosedur", "Markaziy protsessor"], "correct_index": 3, "explanation": "Markaziy protsessor (CPU) kompyuterning barcha hisoblash ishlarini bajaradi."},
    {"question": "Matematikada har qanday sonning 0-darajasi nimaga teng bo'ladi?", "options": ["0 ga", "1 ga", "Sonning o'ziga", "Cheksizlikka"], "correct_index": 1, "explanation": "Noldan farqli har qanday sonning nolinchi darajasi doimo 1 ga teng."},
    {"question": "O'zbekiston Respublikasining milliy valyutasi qaysi yildan muomalaga kiritilgan?", "options": ["1991-yil", "1992-yil", "1994-yil", "1996-yil"], "correct_index": 2, "explanation": "O'zbekiston milliy valyutasi so'm 1994-yil 1-iyuldan boshlab muomalaga kiritilgan."},
    {"question": "Dunyoda eng ko'p aholi yashaydigan davlat qaysi?", "options": ["Xitoy", "Hindiston", "AQSH", "Indoneziya"], "correct_index": 1, "explanation": "Hozirgi kunda Hindiston aholi soni bo'yicha dunyoda birinchi o'rinda turadi."},
    {"question": "Avstraliya qit'asining poytaxti qaysi shahar?", "options": ["Sidney", "Melburn", "Kanberra", "Brisben"], "correct_index": 2, "explanation": "Kanberra shahri Avstraliya Ittifoqining rasmiy poytaxti hisoblanadi."},
    {"question": "Oddiy suv tarkibida nechta vodorod atomi muzojat etadi?", "options": ["1 ta", "2 ta", "3 ta", "4 ta"], "correct_index": 1, "explanation": "Suvning kimyoviy formulasi H2O bo'lib, unda 2 ta vodorod atomi bor."},
    {"question": "Yorug'lik tezligi sekundiga taxminan necha kilometrni tashkil etadi?", "options": ["150 000 km/s", "300 000 km/s", "450 000 km/s", "600 000 km/s"], "correct_index": 1, "explanation": "Yorug'lik vakuumda sekundiga taxminan 300 000 kilometr tezlikda harakatlanadi."},
    {"question": "O'zbekistonning eng chekka janubiy viloyati qaysi?", "options": ["Surxondaryo", "Qashqadaryo", "Xorazm", "Andijon"], "correct_index": 0, "explanation": "Surxondaryo viloyati mamlakatimizning eng janubiy hududida joyhazilgan."},
    {"question": "Qaysi sayyora o'zining atrofidagi ulkan halqalari bilan mashhur?", "options": ["Yupiter", "Saturn", "Mars", "Merkuriy"], "correct_index": 1, "explanation": "Saturn sayyorasi muz va tosh bo'laklaridan iborat ulkan yorqin halqalarga ega."},
    {"question": "Dasturlashda eng ko'p ishlatiladigan 'Python' tili qaysi yili yaratilgan?", "options": ["1989-yil", "1991-yil", "1995-yil", "2000-yil"], "correct_index": 1, "explanation": "Python tili Gvido van Rossum tomonidan 1991-yilda ommaga taqdim etilgan."},
    {"question": "Inson tanasidagi eng katta ichki organ qaysi?", "options": ["Yurak", "O'pka", "Jigar", "Oshqozon"], "correct_index": 2, "explanation": "Jigar inson organizmidagi eng katta ichki organ hisoblanadi."},
    {"question": "Yer Quyosh atrofini to'liq necha kunda aylanib chiqadi?", "options": ["360 kunda", "365 kunda", "366 kunda", "365 yoki 366 kunda"], "correct_index": 3, "explanation": "Yer Quyosh atrofini 365 kunu 6 soatda aylanadi, shu sababli har 4 yilda kabisa yili bo'ladi."},
    {"question": "Qaysi hayvon quruqlikdagi eng tezkor jonzot hisoblanadi?", "options": ["Arslon", "Gepard", "Qoplon", "Bo'ri"], "correct_index": 1, "explanation": "Gepard quruqlikda qisqa masofaga soatiga 110-120 km tezlikda yugura oladi."},
    {"question": "Olimpiada o'yinlari necha yilda bir marta o'tkaziladi?", "options": ["2 yilda", "3 yilda", "4 yilda", "5 yilda"], "correct_index": 2, "explanation": "Xalqaro Olimpiada o'yinlari an'anaviy ravishda har 4 yilda bir marta tashkil etiladi."},
    {"question": "Dunyodagi eng baland tog' cho'qqisi qaysi?", "options": ["K2", "Kanchedjanga", "Lxoze", "Everest"], "correct_index": 3, "explanation": "Everest cho'qqisi dengiz sathidan 8848 metr balandlikda joylashgan eng baland nuqtadir."},
    {"question": "Amerikani kashf etgan mashhur sayyoh kim?", "options": ["Vasko da Gama", "Xristofor Kolumb", "Magellan", "Marko Polo"], "correct_index": 1, "explanation": "Xristofor Kolumb 1492-yilda yangi qit'ani (Amerikani) kashf etgan."},
    {"question": "Inson ko'zi qaysi rang turlarini eng yaxshi va aniq ajrata oladi?", "options": ["Qizil", "Ko'k", "Yashil", "Sariq"], "correct_index": 2, "explanation": "Inson ko'zi evolyutsiya natijasida yashil rang spektrlarini eng sezgir qabul qiladi."}
]

def get_filtered_backup():
    # Chiqmagan zaxira savollarni qidirish
    available = [q for q in BACKUP_QUESTIONS if not is_question_sent(q['question'])]
    if available:
        return random.choice(available)
    # Agar barcha 30 ta savol ham chiqib ketgan bo'lsa, ro'yxatni boshidan aylantiradi
    return random.choice(BACKUP_QUESTIONS)

# --- GEMINI AI (MATNNI TOZALASH TIZIMI BILAN) ---
def get_ai_question():
    mavzular = ["Mantiq", "Tarix", "IT", "San'at", "Geografiya", "Sport", "Koinot", "Biologiya", "Fizika", "Kimyo"]
    mavzu = random.choice(mavzular)
    random_modifier = random.randint(1000, 99999)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt_text = f"""Siz Zakovat ekspertisiz. {mavzu} mavzusida mutloq yangi, qiziqarli savol tuzing. Kod: {random_modifier}.
    Javobni FAQAT toza JSON ko'rinishida bering, hech qanday markdown belgilari (masalan ```json) qo'shmang:
    {{
      "question": "Savol matni?",
      "options": ["V1", "V2", "V3", "V4"],
      "correct_index": 0,
      "explanation": "Qisqa izoh"
    }}"""
    
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.95, "responseMimeType": "application/json"}
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        if response.status_code == 200:
            res_json = response.json()
            ai_text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            
            # Agar Gemini baribir ```json yozib yuborgan bo'lsa, tozalaymiz
            ai_text = re.sub(r'^```text|^```json|```$', '', ai_text, flags=re.MULTILINE).strip()
            return json.loads(ai_text)
        return None
    except Exception as e:
        logger.error(f"❌ Gemini xatoligi: {e}")
        return None

# --- SAVOL YUBORISH VA NAZORAT ---
def send_quiz():
    try:
        data = None
        # 1-Bosqich: Sun'iy intellektdan takrorlanmas yangi savol olishga urinish (5 marta)
        for _ in range(5):
            potential_data = get_ai_question()
            if potential_data and 'question' in potential_data:
                if not is_question_sent(potential_data['question']):
                    data = potential_data
                    break
        
        # 2-Bosqich: Agar sun'iy intellekt ishlamasa, filtrdan o'tgan zaxira savolni olish
        if not data:
            logger.info("⚠️ Gemini API-dan javob bo'lmadi yoki hamma savollar takroriy. Zaxira ro'yxat ishlatilmoqda...")
            data = get_filtered_backup()

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
        
        # Kelajakda takrorlanmasligi uchun bazaga muhrlash
        save_sent_question(data['question'])
        
        conn = sqlite3.connect('zakovat_tizimi.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO polls VALUES (?, ?)", (msg.poll.id, data['correct_index']))
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Savol muvaffaqiyatli chiqdi: {data['question']}")
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
    bot.reply_to(message, "👋 Assalomu alaykum! Zakovat AI to'liq xavfsiz va uzluksiz tizimiga xush kelibsiz.\n\n🤖 Bot endi bir marta chiqqan savolni qayta aslo chiqarmaydi!")

@bot.message_handler(commands=['test'])
def test_handler(message):
    me = bot.get_me()
    bot.reply_to(message, f"🚀 Tizim: ONLAYN\n🤖 Bot: @{me.username}\n📢 Kanal: {CHANNEL}")

@bot.message_handler(commands=['savol'])
def admin_savol(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "⏳ Tizim tekshirilmoqda va takrorlanmas yangi savol tayyorlanmoqda...")
        if send_quiz():
            bot.send_message(message.chat.id, "✅ Savol muvaffaqiyatli joylashtirildi!")
        else:
            bot.send_message(message.chat.id, "❌ Kutilmagan xatolik yuz berdi.")
    else:
        bot.reply_to(message, "⚠️ Bu buyruq faqat admin uchun!")

# --- SCHEDULER ---
def scheduled_quiz():
    send_quiz()

if __name__ == "__main__":
    init_db()
    scheduler = BackgroundScheduler(timezone="Asia/Tashkent")
    for h in [9, 12, 15, 18, 21]:
        scheduler.add_job(scheduled_quiz, 'cron', hour=h, minute=0)
    scheduler.start()
    
    logger.info("🚀 Bot barqaror rejimda ishga tushdi...")
    bot.infinity_polling()
