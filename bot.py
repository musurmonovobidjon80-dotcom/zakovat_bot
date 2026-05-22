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

def is_question_sent(question_text):
    conn = sqlite3.connect('zakovat_tizimi.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sent_questions WHERE question_text = ?", (question_text.strip(),))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def save_sent_question(question_text):
    try:
        conn = sqlite3.connect('zakovat_tizimi.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO sent_questions VALUES (?)", (question_text.strip(),))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Savolni bazaga saqlashda xato: {e}")

# --- 100 TA ENG SARA VA HAR XIL MAVZUDAGI ZAXIRA SAVOLLAR KLUBI ---
BACKUP_QUESTIONS = [
    {"question": "Quyosh sistemasida eng katta sayyora qaysi?", "options": ["Yupiter", "Saturn", "Neptun", "Uran"], "correct_index": 0, "explanation": "Yupiter Quyosh sistemasidagi eng katta sayyora hisoblanadi."},
    {"question": "Insonning eng kuchli mushagi qaysi?", "options": ["Yurak", "Jag' mushagi", "Boldir", "Dumba mushagi"], "correct_index": 1, "explanation": "Jag' mushagi insonning eng kuchli mushagidir."},
    {"question": "Dunyodagi eng chuqur ko'l qaysi?", "options": ["Kaspiy", "Baykal", "Viktoriya", "Tanganika"], "correct_index": 1, "explanation": "Baykal ko'li dunyodagi eng chuqur chuchuk suvli ko'ldir."},
    {"question": "Birinchi elektron hisoblash mashinasi (EHM) qaysi yil yaratilgan?", "options": ["1936-yil", "1946-yil", "1953-yil", "1961-yil"], "correct_index": 1, "explanation": "Dunyodagi birinchi elektron kompyuter ENIAC 1946-yilda yaratilgan."},
    {"question": "Qaysi davlat hududida eng ko'p vaqt mintaqalari joylashgan?", "options": ["Rossiya", "AQSH", "Fransiya", "Kanada"], "correct_index": 2, "explanation": "Fransiyaning chet eldagi hududlari bilan birga jami 12 ta vaqt mintaqasi bor."},
    {"question": "Inson tanasidagi eng kichik suyak qayerda joykahgan?", "options": ["Burunda", "Quloqda", "Barmoqda", "Ko'zda"], "correct_index": 1, "explanation": "Inson tanasidagi eng kichik suyak o'rta quloqdagi uzangisimon suyakdir."},
    {"question": "Dunyodagi eng uzun daryo qaysi?", "options": ["Amazonka", "Nil", "Missisipi", "Yanszi"], "correct_index": 1, "explanation": "Nil daryosi dunyodagi eng uzun daryo hisoblanadi."},
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
    {"question": "Oddiy suv tarkibida nechta vodorod atomi mavjud?", "options": ["1 ta", "2 ta", "3 ta", "4 ta"], "correct_index": 1, "explanation": "Suvning kimyoviy formulasi H2O bo'lib, unda 2 ta vodorod atomi bor."},
    {"question": "Yorug'lik tezligi sekundiga taxminan necha kilometrni tashkil etadi?", "options": ["150 000 km/s", "300 000 km/s", "450 000 km/s", "600 000 km/s"], "correct_index": 1, "explanation": "Yorug'lik vakuumda sekundiga taxminan 300 000 kilometr tezlikda harakatlanadi."},
    {"question": "O'zbekistonning eng chekka janubiy viloyati qaysi?", "options": ["Surxondaryo", "Qashqadaryo", "Xorazm", "Andijon"], "correct_index": 0, "explanation": "Surxondaryo viloyati mamlakatimizning eng janubiy hududida joylashgan."},
    {"question": "Qaysi sayyora o'zining atrofidagi ulkan halqalari bilan mashhur?", "options": ["Yupiter", "Saturn", "Mars", "Merkuriy"], "correct_index": 1, "explanation": "Saturn sayyorasi muz va tosh bo'laklaridan iborat ulkan yorqin halqalarga ega."},
    {"question": "Dasturlashda eng ko'p ishlatiladigan 'Python' tili qaysi yili yaratilgan?", "options": ["1989-yil", "1991-yil", "1995-yil", "2000-yil"], "correct_index": 1, "explanation": "Python tili Gvido van Rossum tomonidan 1991-yilda ommaga taqdim etilgan."},
    {"question": "Inson tanasidagi eng katta ichki organ qaysi?", "options": ["Yurak", "O'pka", "Jigar", "Oshqozon"], "correct_index": 2, "explanation": "Jigar inson organizmidagi eng katta ichki organ hisoblanadi."},
    {"question": "Yer Quyosh atrofini to'liq necha kunda aylanib chiqadi?", "options": ["360 kunda", "365 kunda", "366 kunda", "365 yoki 366 kunda"], "correct_index": 3, "explanation": "Yer Quyosh atrofini 365 kunu 6 soatda aylanadi."},
    {"question": "Qaysi hayvon quruqlikdagi eng tezkor jonzot hisoblanadi?", "options": ["Arslon", "Gepard", "Qoplon", "Bo'ri"], "correct_index": 1, "explanation": "Gepard quruqlikda qisqa masofaga soatiga 110-120 km tezlikda yugura oladi."},
    {"question": "Olimpiada o'yinlari necha yilda bir marta o'tkaziladi?", "options": ["2 yilda", "3 yilda", "4 yilda", "5 yilda"], "correct_index": 2, "explanation": "Xalqaro Olimpiada o'yinlari an'anaviy ravishda har 4 yilda bir marta tashkil etiladi."},
    {"question": "Dunyodagi eng baland tog' cho'qqisi qaysi?", "options": ["K2", "Kanchedjanga", "Lxoze", "Everest"], "correct_index": 3, "explanation": "Everest cho'qqisi dengiz sathidan 8848 metr balandlikda joylashgan eng baland nuqtadir."},
    {"question": "Amerikani kashf etgan mashhur sayyoh kim?", "options": ["Vasko da Gama", "Xristofor Kolumb", "Magellan", "Marko Polo"], "correct_index": 1, "explanation": "Xristofor Kolumb 1492-yilda yangi qit'ani (Amerikani) kashf etgan."},
    {"question": "Inson ko'zi qaysi rang turlarini eng yaxshi va aniq ajrata oladi?", "options": ["Qizil", "Ko'k", "Yashil", "Sariq"], "correct_index": 2, "explanation": "Inson ko'zi evolyutsiya natijasida yashil rang spektrlarini eng sezgir qabul qiladi."},
    # --- YANGI QO'SHILGAN CHEKSIZ VA ARALASH SAVOLLAR (31-100) ---
    {"question": "Nobel mukofoti qaysi davlatda topshiriladi?", "options": ["Norvegiya va Shvetsiya", "Angliya", "AQSH", "Germaniya"], "correct_index": 0, "explanation": "Tinchlik mukofoti Osloda (Norvegiya), qolgan barcha mukofotlar Stokgolmda (Shvetsiya) topshiriladi."},
    {"question": "Dunyodagi eng katta yarim orol qaysi?", "options": ["Hindiston", "Arabiston", "Labrador", "Skandinaviya"], "correct_index": 1, "explanation": "Arabiston yarim oroli maydoni bo'yicha dunyodagi eng ulkan yarim oroldir."},
    {"question": "Qaysi metall oddiy xona haroratida suyuq holatda bo'ladi?", "options": ["Simob", "Galiy", "Seziy", "Yod"], "correct_index": 0, "explanation": "Simob xona haroratida suyuq bo'lgan yagona metalldir."},
    {"question": "Alisher Navoiy bobomiz qaysi shaharda tug'ilganlar?", "options": ["Samarkand", "Buxoro", "Hirot", "Andijon"], "correct_index": 2, "explanation": "Alisher Navoiy 1441-yilda Hirot shahrida dunyoga kelganlar."},
    {"question": "Oila a'zolaridan faqat urg'ochilari ov qiladigan yirtqich hayvon qaysi?", "options": ["Bo'ri", "Arslon", "Sirtlon", "Yo'lbars"], "correct_index": 1, "explanation": "Arslonlar galasida ovning 90% qismini urg'ochi arslonlar bajaradi."},
    {"question": "Dunyoda eng baland sharshara qaysi?", "options": ["Niagara", "Viktoriya", "Anxel", "Iguasu"], "correct_index": 2, "explanation": "Venesueladagi Anxel sharsharasi dunyodagi eng baland sharsharadir (979 metr)."},
    {"question": "Inson organizmidagi eng uzun va eng katta suyak qaysi?", "options": ["Ufq suyagi", "Son suyagi", "To'sh suyagi", "Yelka suyagi"], "correct_index": 1, "explanation": "Son suyagi odam tanasidagi eng uzun va eng mustahkam suyak hisoblanadi."},
    {"question": "Dunyodagi birinchi kosmonavt kim?", "options": ["Nil Armstrong", "Yuriy Gagarin", "Aleksey Leonov", "Valentin Tereshkova"], "correct_index": 1, "explanation": "Yuriy Gagarin 1961-yil 12-aprelda koinotga uchgan birinchi insondir."},
    {"question": "Mikroskop ostida qon guruhlarini birinchi bo'lib kim aniqlagan?", "options": ["Karl Landshteyner", "Robert Kox", "Lui Paster", "Ilya Mechnikov"], "correct_index": 0, "explanation": "Karl Landshteyner 1900-yilda qon guruhlarini ajratib, Nobel mukofotini olgan."},
    {"question": "Qaysi davlat 'Katta Dubulg'a' tennis turnirlarining vatani emas?", "options": ["Fransiya", "Avstraliya", "Braziliya", "Angliya"], "correct_index": 2, "explanation": "Katta dubulg'a o'yinlari Avstraliya, Fransiya, Angliya va AQSHda o'tkaziladi."},
    {"question": "Dunyodagi eng kichik qush qaysi?", "options": ["Kolibri", "Chittak", "Qaldirg'och", "Chumchuq"], "correct_index": 0, "explanation": "Asalari-kolibri qushi dunyodagi eng mitti qush hisoblanadi."},
    {"question": "O'zbekistonning poytaxti Toshkent shahrida birinchi Metro liniyasi qaysi yil ochilgan?", "options": ["1977-yil", "1980-yil", "1985-yil", "1991-yil"], "correct_index": 0, "explanation": "Toshkent metrosining birinchi liniyasi (Chilonzor) 1977-yilda ishga tushgan."},
    {"question": "Qaysi mamlakat 'Kunchiqar yurt' deb ataladi?", "options": ["Xitoy", "Yaponiya", "Koreya", "Vyetnam"], "correct_index": 1, "explanation": "Yaponiya davlati geografik joylashuviga ko'ra an'anaviy ravishda Kunchiqar yurt deyiladi."},
    {"question": "Kimyo fanida oltinning ramzi qanday belgilangan?", "options": ["Ag", "Au", "Fe", "Cu"], "correct_index": 1, "explanation": "Oltin lotincha 'Aurum' so'zidan olingan bo'lib, Au ramzi bilan belgilanadi."},
    {"question": "O'zbekiston Respublikasi Konstitutsiyasi qaysi yil va sanada qabul qilingan?", "options": ["1991-yil 31-avgust", "1992-yil 8-dekabr", "1993-yil 9-aprel", "1995-yil 21-dekabr"], "correct_index": 1, "explanation": "O'zbekiston Konstitutsiyasi 1992-yil 8-dekabrda Oliy Kengash sessiyasida qabul qilingan."},
    {"question": "Dunyodagi eng katta cho'l qaysi?", "options": ["Sahroi Kabir", "Gobi", "Kalahari", "Antarktida cho'li"], "correct_index": 3, "explanation": "Geografik jihatdan Antarktida muzlik cho'li dunyodagi eng katta qutb cho'li hisoblanadi."},
    {"question": "Futbol bo'yicha dunyoda eng ko'p Jahon Chempioni bo'lgan terma jamoa qaysi?", "options": ["Germaniya", "Italiya", "Braziliya", "Argentina"], "correct_index": 2, "explanation": "Braziliya terma jamoasi jami 5 marta Jahon chempionligini qo'lga kiritgan."},
    {"question": "Qaysi qit'ada umuman daryolar mavjud emas?", "options": ["Avstraliya", "Antarktida", "Afrika", "Janubiy Amerika"], "correct_index": 1, "explanation": "Antarktida qit'asi butunlay muz bilan qoplangan bo'lib, u yerda doimiy oqar daryolar yo'q."},
    {"question": "Dunyodagi eng baland bino 'Burj Xalifa' qaysi shaharda joylashgan?", "options": ["Ar-Riyod", "Doha", "Abu-Dabi", "Dubay"], "correct_index": 3, "explanation": "Burj Xalifa minorasi BAAning Dubay shahrida joylashgan (balandligi 828 metr)."},
    {"question": "Inson ko'zining rangdor pardasi ortida joylashgan shaffof linza nima deb ataladi?", "options": ["To'r parda", "Ko'z gavhari", "Shox parda", "Qorachiq"], "correct_index": 1, "explanation": "Ko'z gavhari (xrustalik) yorug'likni sindirib, to'r pardaga tushiruvchi linzadir."},
    {"question": "Mantiqiy savol: Uni sotib olgan odam ishlatmaydi, yasagan odam o'zi uchun yasamaydi. Bu nima?", "options": ["Tobut", "Kiyim", "Mashina", "Pul"], "correct_index": 0, "explanation": "Tobutni sotib olgan tirik odam o'zi ishlatmaydi, marhum esa o'zi sotib ololmaydi."},
    {"question": "Amir Temur bobomiz asos solgan davlatning poytaxti qaysi shahar bo'lgan?", "options": ["Buxoro", "Toshkent", "Samarkand", "Shaxrisabz"], "correct_index": 2, "explanation": "Samarqand shahri Amir Temur saltanatining ulkan poytaxti va madaniyat markazi bo'lgan."},
    {"question": "Dunyodagi eng mashhur 'Mona Liza' (Jokonda) asarining muallifi kim?", "options": ["Mikelyanjelo", "Rafael", "Leonardo da Vinchi", "Rembrandt"], "correct_index": 2, "explanation": "Mona Liza portreti Uyg'onish davri dahosi Leonardo da Vinchi tomonidan chizilgan."},
    {"question": "Yer sharidagi eng sho'r dengiz qaysi?", "options": ["O'rta yer dengizi", "Qizil dengiz", "O'lik dengiz", "Qora dengiz"], "correct_index": 2, "explanation": "O'lik dengiz (aslida ko'l) suvida tuz konsentratsiyasi juda yuqoriligi sababli unda hayot mavjud emas."},
    {"question": "O'zbekistondagi eng baland tog' cho'qqisi qaysi va u qaysi tizmada?", "options": ["Hazrati Sulton cho'qqisi", "Adelunga", "Katta Chimyon", "Beshtor"], "correct_index": 0, "explanation": "Hisor tizmasidagi Hazrati Sulton cho'qqisi O'zbekistonning eng baland nuqtasidir (4643 m)."},
    {"question": "Telefon ixtirochisi Aleksandr Bell birinchi marta telefonda kimga qo'ng'iroq qilgan?", "options": ["Ayoliga", "Yordamchisi Vatsonga", "Prezidentga", "Ukasiga"], "correct_index": 1, "explanation": "U o'z yordamchisiga 'Vatson, bu yoqqa keling, siz kerakiz' deb aytgan."},
    {"question": "Dunyodagi eng qadimgi yozuv turi qaysi?", "options": ["Iyeroglif", "Mixxat (piktografik)", "Lotin", "Kirill"], "correct_index": 1, "explanation": "Shumerlarning mixxat yozuvlari dunyodagi eng qadimgi yozuv tizimi hisoblanadi."},
    {"question": "Kompyuter klaviaturasida eng uzun tugma qaysi?", "options": ["Enter", "Shift", "Backspace", "Probel (Space)"], "correct_index": 3, "explanation": "Probel (bo'shliq qoldirish) tugmasi har qanday standart klaviaturada eng uzuni hisoblanadi."},
    {"question": "Qaysi sayyorada bir yil Yerning 88 kuniga teng bo'ladi?", "options": ["Venera", "Merkuriy", "Mars", "Yupiter"], "correct_index": 1, "explanation": "Merkuriy Quyoshga eng yaqin bo'lgani uchun uning atrofini 88 kunda aylanib chiqadi."},
    {"question": "Inson miyasining necha foiz qismi suvdan iborat?", "options": ["Taxminan 50%", "Taxminan 60%", "Taxminan 75-80%", "Taxminan 95%"], "correct_index": 2, "explanation": "Tirik inson miya to'qimalarining qariyb 75-80% qismini toza suv tashkil etadi."},
    {"question": "Statistikaga ko'ra, dunyoda eng ko'p gapiriladigan ona tili qaysi?", "options": ["Ingliz tili", "Ispan tili", "Xitoy (Mandarin)", "Arab tili"], "correct_index": 2, "explanation": "Aholi soni va ona tili sifatida aniqlanganda Xitoy mandarin tili 1-o'rinda turadi."},
    {"question": "Qaysi yirtqich hayvon suv ostida 15 daqiqagacha nafas olmasdan tura oladi?", "options": ["Oq ayiq", "Timsoh", "Begemot", "Morskoy leopard"], "correct_index": 1, "explanation": "Timsohlar suv ostida harakatsiz holda uzoq vaqt nafasni ushlab tura oladilar."},
    {"question": "Dunyodagi birinchi dasturchi ayol kim hisoblanadi?", "options": ["Ada Lavleys", "Mari Kyuri", "Greys Xopper", "Yekaterina"], "correct_index": 0, "explanation": "Ada Lavleys Bebbajning hisoblash mashinasi uchun birinchi algoritmni yozgan."},
    {"question": "BMT (Birashgan Millatlar Tashkiloti) rasmiy ravishda qaysi yili tashkil topgan?", "options": ["1919-yil", "1945-yil", "1950-yil", "1991-yil"], "correct_index": 1, "explanation": "Ikkinchi jahon urushidan so'ng, 1945-yil 24-oktyabrda BMT nizomi kuchga kirgan."},
    {"question": "Matematikada 'Algoritm' so'zi qaysi buyuk allomaning nomidan olingan?", "options": ["Ibn Sino", "Al-Xorazmiy", "Abu Rayhon Beruniy", "Mirzo Ulug'bek"], "correct_index": 1, "explanation": "Muhammad ibn Muso al-Xorazmiy nomining lotinchalashtirilgan shakli Algoritmga aylangan."},
    {"question": "Inson tanasida qonni filtrlaydigan va tozalaydigan juft organ nima?", "options": ["O'pka", "Buyrak", "Jigar", "Yurak"], "correct_index": 1, "explanation": "Buyraklar organizmdagi suyuqlik va qonni zararli moddalardan tozalab beradi."},
    {"question": "Tarixdagi eng daxshatli va eng katta kemalardan biri 'Titanik' qaysi okeanda cho'kib ketgan?", "options": ["Tinch okeani", "Hind okeani", "Atlantika okeani", "Shimoliy muz okeani"], "correct_index": 2, "explanation": "Titanik loyihasi 1912-yilda Shimoliy Atlantika okeanida aysbergga urilib cho'kkan."},
    {"question": "O'zbekiston Respublikasining davlat gerbi qaysi qush tasvirlangan?", "options": ["Burgut", "Lochin", "Xumo qushi", "Laylak"], "correct_index": 2, "explanation": "O'zbekiston gerbida baxt va hurlik ramzi bo'lgan afsonaviy Humo qushi tasvirlangan."},
    {"question": "Dunyodagi eng yirik orol qaysi?", "options": ["Madagaskar", "Grenlandiya", "Borneo", "Sumatra"], "correct_index": 1, "explanation": "Grenlandiya oroli geografik jihatdan dunyoning eng katta oroli hisoblanadi."},
    {"question": "Suyuqliklar va gazlarning bosimni hamma tomonga teng uzatishi qaysi qonun deyiladi?", "options": ["Nyuton qonuni", "Arximed qonuni", "Paskal qonuni", "Om qonuni"], "correct_index": 2, "explanation": "Gidravlikada bosimning hamma tomonga teng tarqalishi Paskal qonuniga asoslanadi."},
    {"question": "Qaysi sutemizuvchi hayvon ucha oladi?", "options": ["Ko'rshapalak", "Uchar olmaxon", "Pingvin", "Tuyaqush"], "correct_index": 0, "explanation": "Ko'rshapalaklar faol ucha oladigan yagona sutemizuvchilar guruhi hisoblanadi."},
    {"question": "Uchburchakning ichki burchaklari yig'indisi har doim nechaga teng bo'ladi?", "options": ["90 daraja", "180 daraja", "270 daraja", "360 daraja"], "correct_index": 1, "explanation": "Geometriyada har qanday yassi uchburchak burchaklari yig'indisi 180 darajadir."},
    {"question": "Eng mashhur kriptovalyuta 'Bitcoin' qaysi yili tarmoqda ishga tushirilgan?", "options": ["2005-yil", "2009-yil", "2012-yil", "2015-yil"], "correct_index": 1, "explanation": "Satoshi Nakamoto laqabli dasturchi tomonidan Bitcoin tarmog'i 2009-yilda ochilgan."},
    {"question": "O'simliklar quyosh nuri yordamida organik moddalar yaratish jarayoni nima deyiladi?", "options": ["Transpiratsiya", "Fotosintez", "Diffuziya", "Respiratsiya"], "correct_index": 1, "explanation": "Fotosintez quyosh energiyasi yordamida karbonat angidrid va suvdan glyukoza hosil qilishdir."},
    {"question": "Mantiqiy savol: Qaysi so'z doimo xato yoziladi?", "options": ["Xato", "To'g'ri", "Lug'at", "Imlo"], "correct_index": 0, "explanation": "Savolning o'zida javob bor, 'Xato' so'zi har doim 'xato' deb o'qiladi va yoziladi."},
    {"question": "Atom elektronlari qanday zaryadga ega bo'ladi?", "options": ["Musbat (+)", "Manfiy (-)", "Neytral (0)", "O'zgaruvchan"], "correct_index": 1, "explanation": "Atom tarkibidagi elektronlar manfiy, protonlar musbat, neytronlar zaryadsiz bo'ladi."},
    {"question": "Dunyodagi eng ko'p davlatlar bilan chegaradosh mamlakat qaysi?", "options": ["Rossiya va Xitoy", "AQSH", "Braziliya", "Hindiston"], "correct_index": 0, "explanation": "Rossiya va Xitoy har biri 14 tadan qo'shni davlatlar bilan quruqlik chegarasiga ega."},
    {"question": "Kimyoda eng og'ir tabiiy element qaysi?", "options": ["Platin", "Uran", "Oltin", "Qorg'oshin"], "correct_index": 1, "explanation": "Tabiatda sof holda uchraydigan eng og'ir element Uran (tartib raqami 92) hisoblanadi."},
    {"question": "Mashhur Microsoft kompaniyasining asoschisi kim?", "options": ["Stiv Jobs", "Bill Geyts", "Mark Sukerberg", "Elon Mask"], "correct_index": 1, "explanation": "Microsoft korporatsiyasi 1975-yilda Bill Geyts va Pol Allen tomonidan tuzilgan."},
    {"question": "Odam tanasida qon aylanish tizimini birinchi bo'lib to'liq tasvirlagan olim kim?", "options": ["Uilyam Garvey", "Aristotel", "Gipportat", "Galen"], "correct_index": 0, "explanation": "Uilyam Garvey 1628-yilda yurak va qon tomirlarining yopiq tizimini isbotlab bergan."},
    {"question": "Evropa Ittifoqining umumiy valyutasi 'Evro' nechanchi yildan naqd muomalaga kirdi?", "options": ["1995-yil", "1999-yil", "2002-yil", "2005-yil"], "correct_index": 2, "explanation": "Evro banknot va tangalari 2002-yil 1-yanvardan boshlab muomalaga chiqarilgan."},
    {"question": "Dunyodagi eng katta ko'l (maydoni bo'yicha) qaysi?", "options": ["Orol", "Baykal", "Kaspiy dengizi", "Michigan"], "correct_index": 2, "explanation": "Kaspiy dengizi o'zining ulkan o'lchamlari tufayli dengiz deyiladi, lekin u berk ko'ldir."},
    {"question": "Qaysi qush orqaga qarab ham ucha oladigan yagona jonzotdir?", "options": ["Qaldirg'och", "Kolibri", "To'tiqush", "Burgut"], "correct_index": 1, "explanation": "Kolibrilar qanot qoqish tezligi evaziga havoda muallaq tura oladi va orqaga ucha oladi."},
    {"question": "Buyuk ipak yo'li qaysi qit'alarni bog'lagan?", "options": ["Osiyo va Evropa", "Osiyo va Afrika", "Evropa va Amerika", "Afrika va Evropa"], "correct_index": 0, "explanation": "Buyuk ipak yo'li qadimgi Xitoydan tortib O'rta Osiyo orqali O'rta yer dengizigacha cho'zilgan."},
    {"question": "Mashhur 'O'tkan kunlar' birinchi o'zbek romanining muallifi kim?", "options": ["Cho'lpon", "Abdulla Qodiriy", "Gafur Gulom", "Oybek"], "correct_index": 1, "explanation": "'O'tkan kunlar' romani 1922-yilda Abdulla Qodiriy tomonidan yozila boshlangan."},
    {"question": "Mantiqiy savol: Qaysi oyda 28 kun bor?", "options": ["Fevralda", "Faqat kabisa yilida", "Hamma oylarda", "Yanvarda"], "correct_index": 2, "explanation": "Yilning barcha 12 ta oyida ham kamida 28 kun mavjud (ba'zilarida 30 yoki 31)."},
    {"question": "Inson tanasidagi suv muvozanatini saqlashga mas'ul bo'lgan asosiy gormon qaysi?", "options": ["Insulin", "Adrenalin", "Vazopressin (antidiuretik)", "Tiroksin"], "correct_index": 2, "explanation": "Vazopressin gormoni buyraklarda suvning qayta so'rilishini boshqaradi."},
    {"question": "Klassik mexanikaning 3 ta asosiy qonunini kashf etgan ingliz olimi kim?", "options": ["Galiley", "Albert Eynshteyn", "Isaak Nyuton", "Nil Bor"], "correct_index": 2, "explanation": "Isaak Nyuton butun dunyo tortishish qonuni va mexanika asoslarini yaratgan."},
    {"question": "Dunyodagi eng uzun temir yo'l magistrali qaysi?", "options": ["Trans-Sibir", "Katta Xitoy yo'li", "Kanada temir yo'li", "Hindiston ekspressi"], "correct_index": 0, "explanation": "Rossiyadagi Trans-Sibir temir yo'lining uzunligi 9200 kilometrdan oshadi."},
    {"question": "O'zbekistondagi eng katta va mashhur ochiq oltin koni qaysi?", "options": ["Muruntov", "Kalmakir", "Qo'shbuloq", "Zarmitan"], "correct_index": 0, "explanation": "Navoiy viloyatidagi Muruntov koni dunyodagi eng yirik ochiq oltin konlaridan biridir."},
    {"question": "Dengiz sathidan eng pastda joylashgan quruqlik nuqtasi qayerda?", "options": ["Turfan botig'i", "O'lik dengiz sohili", "O'lim vodiysi", "Kaspiy bo'yi"], "correct_index": 1, "explanation": "O'lik dengiz qirg'oqlari dengiz sathidan qariyb 430 metr pastda joylashgan."},
    {"question": "Inson qonida kislorod tashish vazifasini bajaradigan qizil oqsil nima?", "options": ["Leykotsit", "Trombotsit", "Gemoglobin", "Plazma"], "correct_index": 2, "explanation": "Eritrotsitlar tarkibidagi gemoglobin oqsili kislorod bilan birikib, uni tanaga tarqatadi."},
    {"question": "Mashhur 'Google' qidiruv tizimi qaysi yili talabalar tomonidan tuzilgan?", "options": ["1995-yil", "1998-yil", "2001-yil", "2004-yil"], "correct_index": 1, "explanation": "Larri Peyj va Sergey Brin tomonidan Google kompaniyasiga 1998-yilda asos solingan."},
    {"question": "Er sharining qattiq va tashqi qobig'i geografiyada nima deyiladi?", "options": ["Litosfera", "Atmosfera", "Gidrosfera", "Biosfera"], "correct_index": 0, "explanation": "Litosfera Yerning eng tashqi qattiq tosh qobig'i (Yer po'sti) hisoblanadi."},
    {"question": "Shaxmat o'yinida qaysi figura faqat va faqat diagonal bo'ylab harakatlanadi?", "options": ["Rux (Kema)", "Fil", "Farzin", "Ot"], "correct_index": 1, "explanation": "Shaxmatda fillar faqat o'zlari turgan rangdagi diagonallar bo'ylab yura oladi."},
    {"question": "Avtomobil ixtirochisi va konveyer usulida mashina ishlab chiqarishni yo'lga qo'ygan shaxs kim?", "options": ["Genri Ford", "Rudolf Dizel", "Karl Bens", "Enso Ferrari"], "correct_index": 0, "explanation": "Genri Ford konveyer tizimi orqali Ford-T avtomobillarini ommaviy ishlab chiqargan."},
    {"question": "Dunyodagi eng katta va eng og'ir sutemizuvchi hayvon qaysi?", "options": ["Ko'k kit", "Afrika fillari", "Kashalot", "Karkidon"], "correct_index": 0, "explanation": "Ko'k kitning og'irligi 150-180 tonnagacha yetadi va u Yerdagi eng ulkan jonzotdir."},
    {"question": "Mashhur nisbiylik nazariyasi (E=mc^2) muallifi bo'lgan fizik olim kim?", "options": ["Isaak Nyuton", "Albert Eynshteyn", "Nikola Tesla", "Tomas Edison"], "correct_index": 1, "explanation": "Albert Eynshteyn 1905 va 1915-yillarda maxsus va umumiy nisbiylik nazariyalarini yaratgan."},
    {"question": "O'zbekiston hududidan oqib o'tuvchi eng sersuv va yirik ikki daryo qaysilar?", "options": ["Zarafshon va Chirchiq", "Amudaryo va Sirdaryo", "Surxondaryo va Ohangaron", "Narin va Qoradaryo"], "correct_index": 1, "explanation": "Amudaryo va Sirdaryo O'rta Osiyoning eng yirik transchegaraviy daryolari hisoblanadi."},
    {"question": "Mantiqiy savol: Uni yorug'likda ko'rish mumkin, lekin mutloq qorong'uda uni hech kim ko'rolmaydi. Bu nima?", "options": ["Ko'zgu", "Soya", "Havo", "Rasm"], "correct_index": 1, "explanation": "Soya paydo bo'lishi uchun yorug'lik manbai kerak, qorong'uda hamma narsa qora bo'lib, soya bo'lmaydi."},
    {"question": "Birinchi marta antibiotik (penitsillin) daxshatli mikrob o'ldiruvchisini kim kashf etgan?", "options": ["Aleksandr Fleming", "Lui Paster", "Robert Kox", "Zigmunt Freyd"], "correct_index": 0, "explanation": "Aleksandr Fleming 1928-yilda mog'or zamburug'idan birinchi antibiotikni ajratib olgan."},
    {"question": "Erning tabiiy yo'ldoshi bo'lgan Oy Yer atrofini necha kunda to'liq aylanadi?", "options": ["24 kunda", "27.3 kunda", "30 kunda", "365 kunda"], "correct_index": 1, "explanation": "Oy Yer atrofini taxminan 27.3 sutkada (sinodik oy esa 29.5 kun) to'liq aylanadi."},
    {"question": "Internet domenlarida '.uz' qaysi davlatga tegishli milliy yuqori darajali domen hisoblanadi?", "options": ["Ukraina", "O'zbekiston", "Urugvay", "Yangi Zelandiya"], "correct_index": 1, "explanation": ".uz domeni O'zbekiston Respublikasining rasmiy milliy internet hududidir."},
    {"question": "Inson yuragi o'rtacha bir daqiqada necha marta uradi?", "options": ["40-50 marta", "60-80 marta", "90-110 marta", "120-140 marta"], "correct_index": 1, "explanation": "Sog'lom katta yoshli insonning tinch holatdagi yurak urishi daqiqasiga 60-80 tani tashkil etadi."},
    {"question": "Dunyodagi eng katta o'rmon massivi (tayga) qaysi mamlakat hududida joylashgan?", "options": ["Braziliya", "Kanada", "Rossiya", "AQSH"], "correct_index": 2, "explanation": "Rossiya Federatsiyasining Sibir hududidagi ignabargli tayga o'rmonlari eng yirik hisoblanadi."},
    {"question": "Qaysi mashhur olim o'zining teleskopi orqali Yupiter yo'ldoshlarini birinchi bo'lib ko'rgan?", "options": ["Kopernik", "Galileo Galiley", "Iogann Kepler", "Jordano Bruno"], "correct_index": 1, "explanation": "Galileo Galiley 1610-yilda Yupiterning 4 ta eng yirik yo'ldoshini kashf etgan."},
    {"question": "Dunyodagi eng qadimgi va hozirgacha saqlanib qolgan 'Usmon Qur'oni' qaysi shaharda saqlanadi?", "options": ["Makka", "Qohira", "Toshkent", "Madina"], "correct_index": 2, "explanation": "Muqaddas Usmon Qur'oni (Sankt-Peterburgdan keltirilgan) Toshkentdagi Mo'yi Muborak madrasasida saqlanadi."},
    {"question": "Inson tanasidagi eng kichik qon tomirlari nima deb ataladi?", "options": ["Arteriyalar", "Venalar", "Kapillyarlar", "Aorta"], "correct_index": 2, "explanation": "Kapillyarlar eng ingichka qon tomirlari bo'lib, ular to'qimalar bilan gaz almashinuvini bajaradi."},
    {"question": "Mashhur Facebook ijtimoiy tarmog'ining asoschisi kim?", "options": ["Stiv Voznyak", "Mark Sukerberg", "Pavel Durov", "Jek Ma"], "correct_index": 1, "explanation": "Mark Sukerberg Garvard universitetida o'qib yurganida (2004-yil) tarmoqqa asos solgan."},
    {"question": "Yer yuzidagi eng uzun tog' tizmasi (quruqlikda) qaysi?", "options": ["Himolay", "And tog'lari", "Kordilyer", "Ural tog'lari"], "correct_index": 1, "explanation": "Janubiy Amerikadagi And tog' tizmasi quruqlikdagi eng uzun tog' zanjiridir (7000 km)."}
]

def get_filtered_backup():
    available = [q for q in BACKUP_QUESTIONS if not is_question_sent(q['question'])]
    if available:
        return random.choice(available)
    return random.choice(BACKUP_QUESTIONS)

# --- GEMINI AI SIZNING CHEKSIZ GENERATORINGIZ ---
def get_ai_question():
    mavzular = [
        "Mantiqiy topishmoq", "Tarixiy faktlar", "Texnologiya va IT", "Adabiyot va San'at", 
        "Geografiya va Sayyoralar", "Sport va Olimpiada", "Biologiya va Tabiat"
    ]
    mavzu = random.choice(mavzular)
    random_modifier = random.randint(1000, 99999)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt_text = f"""Siz Zakovat ekspertisiz. {mavzu} mavzusida o'ta qiziqarli savol tuzing. Kod: {random_modifier}.
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
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code == 200:
            res_json = response.json()
            ai_text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            ai_text = re.sub(r'^```text|^```json|```$', '', ai_text, flags=re.MULTILINE).strip()
            return json.loads(ai_text)
        return None
    except Exception as e:
        logger.error(f"❌ Gemini API xatoligi: {e}")
        return None

# --- SAVOL YUBORISH VA NAZORAT REJIMI ---
def send_quiz():
    try:
        data = None
        # Birinchi o'rinda sun'iy intellektdan mutloq yangi savol olishga urinadi
        for _ in range(3):
            potential_data = get_ai_question()
            if potential_data and 'question' in potential_data:
                if not is_question_sent(potential_data['question']):
                    data = potential_data
                    break
        
        # AGAR GEMINI LIMITI TUGASA YOKI TARMOQDA XATO BO'LSA - 100 TA ARALASH BAZAGA O'TADI
        if not data:
            logger.info("⚠️ Gemini API javob bermadi. 100 talik ulkan zaxiradan aralash savol tanlanmoqda...")
            data = get_filtered_backup()

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
        
        # Savol takrorlanmasligi uchun eslab qolish
        save_sent_question(data['question'])
        
        conn = sqlite3.connect('zakovat_tizimi.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO polls VALUES (?, ?)", (msg.poll.id, int(data['correct_index'])))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Savol yuborishda xato: {e}")
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
    bot.reply_to(message, "👋 Zakovat AI boshqaruv paneli faol! 100 talik zaxira va cheksiz AI generatori ishga tushirildi.")

@bot.message_handler(commands=['test'])
def test_handler(message):
    me = bot.get_me()
    bot.reply_to(message, f"🚀 Tizim: ONLAYN\n🤖 Bot: @{me.username}\n📢 Kanal: {CHANNEL}")

@bot.message_handler(commands=['savol'])
def admin_savol(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "⏳ Tizim tekshirilmoqda va aralash intellektual savol chiqarilmoqda...")
        if send_quiz():
            bot.send_message(message.chat.id, "✅ Savol muvaffaqiyatli joylashtirildi!")
        else:
            bot.send_message(message.chat.id, "❌ Kutilmagan texnik xatolik yuz berdi.")
    else:
        bot.reply_to(message, "⚠️ Bu buyruq faqat bot egasi uchun!")

def scheduled_quiz():
    send_quiz()

if __name__ == "__main__":
    init_db()
    scheduler = BackgroundScheduler(timezone="Asia/Tashkent")
    for h in [9, 12, 15, 18, 21]:
        scheduler.add_job(scheduled_quiz, 'cron', hour=h, minute=0)
    scheduler.start()
    bot.infinity_polling()
