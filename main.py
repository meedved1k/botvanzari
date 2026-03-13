import asyncio
import logging
import os
import datetime
import psycopg2
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, FSInputFile, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")
LINK_MIA = os.getenv("MIA_LINK")
LINK_SUPORT = os.getenv("SUPORT_LINK")

VIDEO_CALORII = os.getenv("VIDEO_CALORII")
VIDEO_FELICITARI = os.getenv("CRUJOC_FELICITARI")
FREE_TEST_ID = os.getenv("FREE_TEST_ID")
VIDEO_CRUJOC_ID = os.getenv("VIDEO_CRUJOC_ID")
VIDEO_DESCRIERE_ID = os.getenv("VIDEO_DESCRIERE_ID")
VIDEO_CURS_ID = os.getenv("VIDEO_CURS_ID")
FREE_WORKOUT_ID = os.getenv("FREE_WORKOUT_ID")
PHOTO_1 = os.getenv("CUPRINS_PHOTO_1_ID")
PHOTO_2 = os.getenv("CUPRINS_PHOTO_2_ID")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- FSM Admin ---
class BroadcastState(StatesGroup):
    waiting_for_message = State()
    target_group = State()

# --- PostgreSQL ---
def get_conn():
    uri = os.getenv("DATABASE_URL")
    if not uri:
        raise ValueError("EROARE: Variabila DATABASE_URL nu este setată în Railway!")
    
    # Rezolvă eroarea de protocol dacă e cazul
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    return psycopg2.connect(uri)
def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            purchase_date TIMESTAMP,
            has_access BOOLEAN DEFAULT FALSE,
            a_clicat_cumpara BOOLEAN DEFAULT FALSE,
            a_deschis_test BOOLEAN DEFAULT FALSE,
            last_followup SMALLINT DEFAULT 0,
            review_sent SMALLINT DEFAULT 0
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()

def update_db(user_id, column, value):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {column} = %s WHERE user_id = %s", (value, user_id))
    conn.commit()
    cursor.close()
    conn.close()

def check_db_flag(user_id, column):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(f"SELECT {column} FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else False

# --- Subscription Check ---
async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# --- Keyboards ---
def post_contents_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✨VREAU ABDOMEN  PLAT (Acces Instant)", callback_data="buy_guide"))
    builder.row(
        InlineKeyboardButton(text="🎥 Prezentare Video", callback_data="video_intro"),
        InlineKeyboardButton(text="ℹ️ Întrebări / Suport", url=LINK_SUPORT)
    )
    builder.adjust(1,2)
    return builder.as_markup()

def sub_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📢 Abonează-te la Canal", url=CHANNEL_LINK))
    builder.row(InlineKeyboardButton(text="✅ Sunt deja abonat", callback_data="check_sub"))
    return builder.as_markup()

def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏋️ Testează-ți abdomenul", callback_data="free_test"))
    builder.row(InlineKeyboardButton(text="📋 Ce conține ghidul? (Cuprins)", callback_data="contents"))
    builder.row(InlineKeyboardButton(text="🎥 Prezentare Video", callback_data="video_intro"))
    builder.row(InlineKeyboardButton(text="✨VREAU ABDOMEN  PLAT (Acces Instant)", callback_data="buy_guide"))
    builder.adjust(1)
    return builder.as_markup()

def premium_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✨VREAU ABDOMEN  PLAT (Acces Instant)", callback_data="buy_guide"))
    builder.row(InlineKeyboardButton(text="📋 Ce conține ghidul? (Cuprins)", callback_data="contents"))
    builder.row(InlineKeyboardButton(text="🎥 Prezentare Video", callback_data="video_intro"))
    builder.row(InlineKeyboardButton(text="ℹ️ Întrebări / Suport", url=LINK_SUPORT))
    builder.adjust(1)
    return builder.as_markup()

def post_intro_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✨VREAU ABDOMEN  PLAT (Acces Instant)", callback_data="buy_guide"))
    builder.row(InlineKeyboardButton(text="🏋️ Testează-ți abdomenul", callback_data="free_test"))
    builder.row(InlineKeyboardButton(text="ℹ️ Întrebări / Suport", url=LINK_SUPORT))
    builder.adjust(1,2)
    return builder.as_markup()

def admin_panel():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📢 Toți utilizatorii", callback_data="send_to_all"))
    builder.row(InlineKeyboardButton(text="🛑 Doar cei care AU DAT START", callback_data="send_to_only_start"))
    builder.row(InlineKeyboardButton(text="🏋️ Cei care au făcut TESTUL", callback_data="send_to_test"))
    builder.row(InlineKeyboardButton(text="💰 Cei care AU APĂSAT CUMPĂRĂ", callback_data="send_to_pending"))
    builder.adjust(1)
    return builder.as_markup()

# --- Welcome Flow ---
async def send_welcome_flow(user_id):
    if VIDEO_CRUJOC_ID:
        try: await bot.send_video_note(chat_id=user_id, video_note=VIDEO_CRUJOC_ID); await asyncio.sleep(3)
        except: pass

    await bot.send_message(user_id, "Bună! 🤍 Mă bucur că ai ajuns aici.\nEu sunt Iuliana - Instructor fitness și nutriționist.", parse_mode="Markdown")
    await asyncio.sleep(2)
    await bot.send_message(user_id, "Am creat ghidul pentru abdomen plat și digestie echilibrată...", reply_markup=main_menu(), parse_mode="Markdown")

# --- /start ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id, username) VALUES (%s,%s) ON CONFLICT (user_id) DO NOTHING",
                   (message.from_user.id, message.from_user.username))
    conn.commit(); cursor.close(); conn.close()
    await send_welcome_flow(message.from_user.id)

# --- CHECK SUB ---
@dp.callback_query(F.data=="check_sub")
async def check_sub_cb(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete(); await free_test(callback)
    else: await callback.answer("❌ Încă nu te-ai abonat la canal!", show_alert=True)

# --- CONTENTS ---
@dp.callback_query(F.data=="contents")
async def contents_handler(callback: types.CallbackQuery):
    await callback.message.delete()
    if PHOTO_1 and PHOTO_2:
        album=[InputMediaPhoto(media=PHOTO_1), InputMediaPhoto(media=PHOTO_2)]
        await bot.send_media_group(chat_id=callback.from_user.id, media=album)
    await bot.send_message(callback.from_user.id, "În ghid vei găsi răspunsuri...", reply_markup=post_contents_menu())

# --- VIDEO INTRO ---
@dp.callback_query(F.data=="video_intro")
async def send_intro(callback: types.CallbackQuery):
    if VIDEO_DESCRIERE_ID:
        await callback.message.answer_video(video=VIDEO_DESCRIERE_ID, caption="Am pregătit acest video...", reply_markup=post_intro_menu())
    await callback.answer()

# --- FREE TEST ---
@dp.callback_query(F.data=="free_test")
async def free_test(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not await check_subscription(user_id):
        await callback.message.answer("Te rog să te abonezi la canal...", reply_markup=sub_keyboard()); await callback.answer(); return
    update_db(user_id,"a_deschis_test",True)
    if FREE_TEST_ID:
        await callback.message.answer("Hai să facem testul! 💪")
        await bot.send_video(user_id, video=FREE_TEST_ID)
        await asyncio.sleep(2)
        await bot.send_message(user_id, "Dacă vrei să continui, ghidul meu te va ajuta...", reply_markup=premium_menu())
    else: await callback.answer("⚠️ Video momentan indisponibil.", show_alert=True)
    await callback.answer()

# --- ADMIN PANEL ---
@dp.message(Command("admin"), F.from_user.id==ADMIN_ID)
async def admin_start(message: types.Message):
    await message.answer("🛠 PANOU CONTROL", reply_markup=admin_panel())

# --- BROADCAST ---
@dp.callback_query(F.data.startswith("send_to_"), F.from_user.id==ADMIN_ID)
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    target = callback.data.replace("send_to_","")
    await state.update_data(target_group=target)
    await callback.message.answer(f"📝 Scrie mesajul pentru grup: {target}")
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.answer()

@dp.message(BroadcastState.waiting_for_message, F.from_user.id==ADMIN_ID)
async def deliver_broadcast(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target = data['target_group']
    conn = get_conn(); cursor = conn.cursor()
    queries={
        "all":"SELECT user_id FROM users",
        "only_start":"SELECT user_id FROM users WHERE a_deschis_test=FALSE AND a_clicat_cumpara=FALSE",
        "test":"SELECT user_id FROM users WHERE a_deschis_test=TRUE AND a_clicat_cumpara=FALSE",
        "pending":"SELECT user_id FROM users WHERE a_clicat_cumpara=TRUE AND has_access=FALSE"
    }
    cursor.execute(queries.get(target,"all"))
    users = cursor.fetchall()
    cursor.close(); conn.close()
    count=0
    for user in users:
        try: await bot.send_message(user[0], message.text, reply_markup=main_menu()); count+=1; await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Mesaj trimis la {count} persoane!"); await state.clear()

# --- Buy Guide ---
@dp.callback_query(F.data=="buy_guide")
async def process_buy(callback: types.CallbackQuery):
    update_db(callback.from_user.id,"a_clicat_cumpara",True)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Achită prin MIA", url=LINK_MIA))
    builder.row(InlineKeyboardButton(text="✅ Am achitat", callback_data="confirm_payment"))
    builder.row(InlineKeyboardButton(text="ℹ️ Am o  întrebare", url=LINK_SUPORT))
    await callback.message.answer("Ghidul costă 300 MDL...", reply_markup=builder.as_markup())

# --- Confirm Payment ---
@dp.callback_query(F.data=="confirm_payment")
async def ask_photo(callback: types.CallbackQuery):
    await callback.message.answer("Te rog să trimiți poza aici 👇")
    await callback.answer()

# --- Handle Photo ---
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    if message.from_user.id==ADMIN_ID: return
    if check_db_flag(message.from_user.id,"a_clicat_cumpara"):
        await message.answer("✅ Am primit! Iuliana va verifica transferul...")
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="✅ Aprobă", callback_data=f"approve_{message.from_user.id}"))
        builder.row(InlineKeyboardButton(text="❌ Respinge", callback_data=f"reject_{message.from_user.id}"))
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"🚨 PLATĂ @{message.from_user.username}", reply_markup=builder.as_markup())
    else:
        await message.answer("⚠️ Folosește butonul 'Cumpără' mai întâi.", reply_markup=main_menu())

# --- Approve Payment ---
@dp.callback_query(F.data.startswith("approve_"))
async def approve(callback: types.CallbackQuery):
    uid=int(callback.data.split("_")[1])
    now_str=datetime.datetime.now()
    conn=get_conn(); cursor=conn.cursor()
    cursor.execute("UPDATE users SET has_access=TRUE, purchase_date=%s WHERE user_id=%s",(now_str, uid))
    conn.commit(); cursor.close(); conn.close()
    if VIDEO_FELICITARI:
        try: await bot.send_video_note(uid, video_note=VIDEO_FELICITARI)
        except: pass
    await asyncio.sleep(2)
    try:
        await bot.send_document(uid, FSInputFile("Todirean Iuliana.pdf"), caption="📖 Ghidul tău Complet pentru Abdomen Plat", parse_mode="Markdown")
    except: await bot.send_message(uid, "⚠️ A apărut o problemă la trimiterea PDF-ului.")
    if VIDEO_CURS_ID: await bot.send_video(uid, VIDEO_CURS_ID, caption="🎥 CUM SĂ ÎNCEPI (Mesaj Important)")
    if VIDEO_CALORII: await bot.send_video(uid, VIDEO_CALORII, caption="🥗 TOTUL DESPRE CALORII")
    builder = InlineKeyboardBuilder(); builder.row(InlineKeyboardButton(text="ℹ️ Suport", url=LINK_SUPORT))
    await bot.send_message(uid, "Spor la treabă! 💪✨", reply_markup=builder.as_markup())
    await callback.message.edit_caption(caption="✅ LIVRAT CU SUCCES", parse_mode="Markdown")
    await callback.answer("Materiale trimise!")

# --- Reject Payment ---
@dp.callback_query(F.data.startswith("reject_"))
async def reject(callback: types.CallbackQuery):
    uid=int(callback.data.split("_")[1])
    await bot.send_message(uid,"😔 Plata nu a putut fi confirmată. Contactează suport.", reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🆘 Suport", url=LINK_SUPORT)).as_markup())
    await callback.message.edit_caption(caption="❌ PLATĂ RESPINSĂ", parse_mode="Markdown")
    await callback.answer("Notificare de respingere trimisă.")

# --- Auto Followup Loop ---
async def auto_followup_loop():
    while True:
        await asyncio.sleep(3600)
        try:
            conn=get_conn(); cursor=conn.cursor()
            now=datetime.datetime.now()
            # --- FOLLOWUP VÂNZARE ---
            cursor.execute("SELECT user_id, join_date, last_followup FROM users WHERE has_access=FALSE AND last_followup<2")
            prospects=cursor.fetchall()
            for user in prospects:
                u_id, join_date, last_followup = user
                hours_passed=(now-join_date).total_seconds()/3600
                if 2<=hours_passed<24 and last_followup==0:
                    await bot.send_message(u_id,"Hei! ✨ Nu uita de tine.", reply_markup=main_menu())
                    cursor.execute("UPDATE users SET last_followup=1 WHERE user_id=%s",(u_id,))
                elif hours_passed>=24 and last_followup==1:
                    await bot.send_message(u_id,"Un mic secret: hidratarea corectă...", reply_markup=main_menu())
                    cursor.execute("UPDATE users SET last_followup=2 WHERE user_id=%s",(u_id,))
                conn.commit()
            # --- FOLLOWUP PENDING BUYERS ---
            cursor.execute("SELECT user_id, join_date FROM users WHERE a_clicat_cumpara=TRUE AND has_access=FALSE")
            pending_buyers=cursor.fetchall()
            for user in pending_buyers:
                u_id, join_date = user
                hours_passed=(now-join_date).total_seconds()/3600
                if 1<=hours_passed<5:
                    builder = InlineKeyboardBuilder()
                    builder.row(InlineKeyboardButton(text="💸 Achită prin MIA", url=LINK_MIA))
                    builder.row(InlineKeyboardButton(text="ℹ️ Am o întrebare", url=LINK_SUPORT))
                    await bot.send_message(u_id,"Dacă ai avut vreo problemă la transfer...", reply_markup=builder.as_markup())
            # --- FOLLOWUP REVIEW ---
            cursor.execute("SELECT user_id, purchase_date FROM users WHERE has_access=TRUE AND review_sent=0")
            customers=cursor.fetchall()
            for user in customers:
                u_id, p_date = user
                if not p_date: continue
                hours_since_purchase=(now-p_date).total_seconds()/3600
                if hours_since_purchase>=24:
                    builder = InlineKeyboardBuilder()
                    builder.row(InlineKeyboardButton(text="✍️ Trimite un Review", callback_data="give_review"))
                    builder.row(InlineKeyboardButton(text="ℹ️ Suport", url=LINK_SUPORT))
                    await bot.send_message(u_id,"A trecut o zi de când ai ghidul...", reply_markup=builder.as_markup())
                    cursor.execute("UPDATE users SET review_sent=1 WHERE user_id=%s",(u_id,))
            conn.commit(); cursor.close(); conn.close()
        except Exception as e:
            logging.error(f"Eroare follow-up: {e}")
            if 'conn' in locals(): conn.close()

# --- Main ---
async def main():
    init_db()
    asyncio.create_task(auto_followup_loop())
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
