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
            review_sent SMALLINT DEFAULT 0,
            last_followup_sent TIMESTAMP,
            pending_followup_sent BOOLEAN DEFAULT FALSE
        )
    """)
    # Adaugă coloanele noi dacă baza de date deja există
    for col, definition in [
        ("last_followup_sent", "TIMESTAMP"),
        ("pending_followup_sent", "BOOLEAN DEFAULT FALSE"),
        ("test_date", "TIMESTAMP"),
        ("test_followup", "SMALLINT DEFAULT 0"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition}")
        except Exception:
            conn.rollback()
    conn.commit()
    cursor.close()
    conn.close()

def update_db(user_id, column, value):
    # NOTĂ: column trebuie să fie întotdeauna un string intern, niciodată de la user
    allowed_columns = {
        "has_access", "a_clicat_cumpara", "a_deschis_test",
        "last_followup", "review_sent", "last_followup_sent",
        "pending_followup_sent", "purchase_date", "username",
        "test_date", "test_followup"
    }
    if column not in allowed_columns:
        logging.warning(f"update_db: coloană nepermisă '{column}'")
        return
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {column} = %s WHERE user_id = %s", (value, user_id))
    conn.commit()
    cursor.close()
    conn.close()

def check_db_flag(user_id, column):
    allowed_columns = {
        "has_access", "a_clicat_cumpara", "a_deschis_test",
        "last_followup", "review_sent", "pending_followup_sent"
    }
    if column not in allowed_columns:
        return False
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
    builder.adjust(1, 2)
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
    builder.adjust(1, 2)
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
        try:
            await bot.send_video_note(chat_id=user_id, video_note=VIDEO_CRUJOC_ID)
            await asyncio.sleep(3)
        except Exception as e:
            logging.warning(f"send_video_note failed for {user_id}: {e}")

    await bot.send_message(
        user_id,
        "Bună! 🤍 Mă bucur că ai ajuns aici.\n"
        "Eu sunt Iuliana - Instructor fitness și nutriționist. "
        "Lucrez cu femei care vor să slăbească sănătos, să-și tonifieze abdomenul și să își recapete energia, fără diete extreme.",
        parse_mode="Markdown"
    )
    await asyncio.sleep(2)
    await bot.send_message(
        user_id,
        "Am creat ghidul pentru abdomen plat și digestie echilibrată. Este un ghid simplu și practic pentru femeile care:\n"
        " • Se confruntă cu balonare frecventă\n"
        " • Simt că abdomenul este mereu umflat\n"
        " • Nu știu ce să mănânce pentru a slăbi frumos\n"
        " • Vor să își tonifieze abdomenul fără diete\n\n"
        "În ghid găsești explicații clare, recomandări alimentare și exerciții care te ajută să reduci balonarea, "
        "să reactivezi core-ul și să obții un abdomen mai plat. ✨",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

# --- /start ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (user_id, username) VALUES (%s,%s) ON CONFLICT (user_id) DO NOTHING",
        (message.from_user.id, message.from_user.username)
    )
    conn.commit()
    cursor.close()
    conn.close()
    await send_welcome_flow(message.from_user.id)

# --- CHECK SUB ---
@dp.callback_query(F.data == "check_sub")
async def check_sub_cb(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await free_test(callback)
    else:
        await callback.answer("❌ Încă nu te-ai abonat la canal!", show_alert=True)

# --- CONTENTS ---
@dp.callback_query(F.data == "contents")
async def contents_handler(callback: types.CallbackQuery):
    await callback.message.delete()
    if PHOTO_1 and PHOTO_2:
        album = [InputMediaPhoto(media=PHOTO_1), InputMediaPhoto(media=PHOTO_2)]
        await bot.send_media_group(chat_id=callback.from_user.id, media=album)
    await bot.send_message(
        callback.from_user.id,
        "În ghid vei găsi răspunsuri clare la întrebările pe care multe femei le au:\n"
        " • De ce nu dispare burta, chiar dacă încerci să mănânci mai puțin.\n"
        " • 5 cauze reale pentru care nu slăbești\n"
        " • Cum ar trebui să arate mesele tale pentru echilibru și energie\n"
        " • Cum să slăbești sănătos, fără stres și fără diete extreme\n"
        " • De ce apar balonările frecvent și disconfortul după masă\n\n"
        "Ghidul explică toate aceste lucruri simplu și practic pentru rezultate reale.",
        reply_markup=post_contents_menu()
    )

# --- VIDEO INTRO ---
@dp.callback_query(F.data == "video_intro")
async def send_intro(callback: types.CallbackQuery):
    if VIDEO_DESCRIERE_ID:
        await callback.message.answer_video(
            video=VIDEO_DESCRIERE_ID,
            caption="Am pregătit acest video ca să-ți arăt, pas cu pas, despre ce e ghidul și cum te poate ajuta.",
            reply_markup=post_intro_menu()
        )
    await callback.answer()

# --- FREE TEST ---
@dp.callback_query(F.data == "free_test")
async def free_test(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not await check_subscription(user_id):
        await callback.message.answer(
            "Mă bucur că vrei să facem testul! ✨\n\n"
            "Pentru a debloca acest video și restul materialelor gratuite, "
            "te invit să te alături comunității mele de pe canal. "
            "Apasă butonul de mai jos, apoi revino aici:",
            reply_markup=sub_keyboard()
        )
        await callback.answer()
        return
    update_db(user_id, "a_deschis_test", True)
    update_db(user_id, "test_date", datetime.datetime.now())
    if FREE_TEST_ID:
        await callback.message.answer(
            "Vrei să afli cât de puternici sunt mușchii tăi abdominali?\n"
            "Hai să facem împreună un test rapid în trei exerciții! 💪"
        )
        await bot.send_video(user_id, video=FREE_TEST_ID)
        await asyncio.sleep(2)
        await bot.send_message(
            user_id,
            "Cum a fost? Dacă simți că ai nevoie de mai multă claritate în alimentație, "
            "ghidul meu te va ajuta enorm. 👇",
            reply_markup=premium_menu()
        )
    else:
        await callback.answer("⚠️ Video momentan indisponibil.", show_alert=True)
    await callback.answer()

# --- ADMIN PANEL ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_start(message: types.Message):
    await message.answer("🛠 PANOU CONTROL", reply_markup=admin_panel())

# --- /stats ---
@dp.message(Command("stats"), F.from_user.id == ADMIN_ID)
async def admin_stats(message: types.Message):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE has_access=TRUE")
    cumparati = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE a_clicat_cumpara=TRUE AND has_access=FALSE")
    pending = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE a_deschis_test=TRUE AND has_access=FALSE")
    au_testat = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE a_deschis_test=FALSE AND a_clicat_cumpara=FALSE AND has_access=FALSE")
    doar_start = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE review_sent=1")
    review_trimis = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM users
        WHERE purchase_date >= NOW() - INTERVAL '7 days' AND has_access=TRUE
    """)
    cumparati_7zile = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    conversie = round((cumparati / total * 100), 1) if total > 0 else 0

    text = (
        "📊 *STATISTICI BOT*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total useri: *{total}*\n"
        f"✅ Au cumpărat: *{cumparati}*\n"
        f"🛒 Pending (au apăsat Cumpără): *{pending}*\n"
        f"🏋️ Au făcut testul (fără cumpărare): *{au_testat}*\n"
        f"👶 Doar au dat /start: *{doar_start}*\n"
        f"⭐️ Review trimis: *{review_trimis}*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📈 Conversie generală: *{conversie}%*\n"
        f"🗓 Cumpărături ultimele 7 zile: *{cumparati_7zile}*"
    )
    await message.answer(text, parse_mode="Markdown")

# --- BROADCAST: inițiere ---
@dp.callback_query(F.data.startswith("send_to_"), F.from_user.id == ADMIN_ID)
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    target = callback.data.replace("send_to_", "")
    await state.update_data(target_group=target)
    await callback.message.answer(
        f"📝 Trimite mesajul pentru grup: *{target}*\n\n"
        "Poți trimite: text, foto, video sau document.",
        parse_mode="Markdown"
    )
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.answer()

# --- BROADCAST: livrare — suportă text, foto, video, document ---
@dp.message(BroadcastState.waiting_for_message, F.from_user.id == ADMIN_ID)
async def deliver_broadcast(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target = data['target_group']

    queries = {
        "all": "SELECT user_id FROM users",
        "only_start": "SELECT user_id FROM users WHERE a_deschis_test=FALSE AND a_clicat_cumpara=FALSE",
        "test": "SELECT user_id FROM users WHERE a_deschis_test=TRUE AND a_clicat_cumpara=FALSE",
        "pending": "SELECT user_id FROM users WHERE a_clicat_cumpara=TRUE AND has_access=FALSE",
    }
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(queries.get(target, "SELECT user_id FROM users"))
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    count = 0
    failed = 0
    for (user_id,) in users:
        try:
            if message.photo:
                await bot.send_photo(
                    user_id,
                    message.photo[-1].file_id,
                    caption=message.caption or "",
                    reply_markup=main_menu()
                )
            elif message.video:
                await bot.send_video(
                    user_id,
                    message.video.file_id,
                    caption=message.caption or "",
                    reply_markup=main_menu()
                )
            elif message.document:
                await bot.send_document(
                    user_id,
                    message.document.file_id,
                    caption=message.caption or "",
                    reply_markup=main_menu()
                )
            elif message.text:
                await bot.send_message(user_id, message.text, reply_markup=main_menu())
            else:
                await bot.send_message(user_id, message.caption or "—", reply_markup=main_menu())
            count += 1
        except Exception as e:
            logging.warning(f"Broadcast failed pentru {user_id}: {e}")
            failed += 1
        await asyncio.sleep(0.05)

    await message.answer(f"✅ Trimis la {count} persoane. ❌ Eșuat: {failed}.")
    await state.clear()

# --- Buy Guide ---
@dp.callback_query(F.data == "buy_guide")
async def process_buy(callback: types.CallbackQuery):
    update_db(callback.from_user.id, "a_clicat_cumpara", True)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Achită prin MIA", url=LINK_MIA))
    builder.row(InlineKeyboardButton(text="✅ Am achitat", callback_data="confirm_payment"))
    builder.row(InlineKeyboardButton(text="ℹ️ Am o  întrebare", url=LINK_SUPORT))
    await callback.message.answer(
        "Mă bucur mult că vrei să lucrăm împreună 🤍\n\n"
    "Am creat acest ghid exact așa cum mi-aș fi dorit să îl am când am început — atunci când încercam diete, mă înfometam și tot simțeam că nu înțeleg ce face cu adevărat diferența.\n\n"
"Este un ghid simplu, clar și construit ca să te ajute să obții abdomen mai plat fără diete extreme și fără stresul ce mai mănânc azi?\n\n"
"În el găsești:\n"
"🥗 structura corectă a meselor.\n"
"🍽 combinații simple de alimente care chiar funcționează.\n"
"📋 exemple reale de meniu pe care le poți urma imediat.\n"
"Practic, îți arată cum să mănânci corect în fiecare zi, astfel încât corpul tău să înceapă să se schimbe fără restricții inutile.\n\n"
"Prețul ghidului este 300 MDL.\n\n"
"Dacă simți că ai obosit de diete care nu funcționează și vrei în sfârșit un plan simplu pe care să-l poți urma, poți face plata prin MIA, iar eu îți trimit ghidul imediat aici ca să poți începe chiar de azi 🌿", reply_markup=builder.as_markup())
,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# --- Confirm Payment ---
@dp.callback_query(F.data == "confirm_payment")
async def ask_photo(callback: types.CallbackQuery):
    await callback.message.answer("Te rog să trimiți poza aici 👇")
    await callback.answer()

# --- Handle Photo ---
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        return
    if check_db_flag(message.from_user.id, "a_clicat_cumpara"):
        await message.answer(
            "✅ Am primit! Iuliana va verifica transferul în cel mai scurt timp "
            "(de obicei durează maxim 10 min). Vei primi un mesaj aici imediat!"
        )
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="✅ Aprobă", callback_data=f"approve_{message.from_user.id}"))
        builder.row(InlineKeyboardButton(text="❌ Respinge", callback_data=f"reject_{message.from_user.id}"))
        await bot.send_photo(
            ADMIN_ID,
            message.photo[-1].file_id,
            caption=f"🚨 PLATĂ @{message.from_user.username} (ID: {message.from_user.id})",
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer("⚠️ Folosește butonul 'Cumpără' mai întâi.", reply_markup=main_menu())

# --- Approve Payment ---
@dp.callback_query(F.data.startswith("approve_"))
async def approve(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    now_str = datetime.datetime.now()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET has_access=TRUE, purchase_date=%s WHERE user_id=%s",
        (now_str, uid)
    )
    conn.commit()
    cursor.close()
    conn.close()

    if VIDEO_FELICITARI:
        try:
            await bot.send_video_note(uid, video_note=VIDEO_FELICITARI)
        except Exception as e:
            logging.warning(f"Felicitări video eșuat pentru {uid}: {e}")
    await asyncio.sleep(2)

    try:
        await bot.send_document(
            uid,
            FSInputFile("Todirean Iuliana.pdf"),
            caption="📖 Ghidul tău Complet pentru Abdomen Plat\n\n"
                    "Salvează-l în telefon și citește primele 10 pagini chiar astăzi!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"PDF send eșuat pentru {uid}: {e}")
        await bot.send_message(uid, "⚠️ A apărut o problemă la trimiterea PDF-ului. Contactează suport.")

    if VIDEO_CURS_ID:
        await bot.send_video(
            uid, VIDEO_CURS_ID,
            caption="🎥 CUM SĂ ÎNCEPI (Mesaj Important)\n\n"
                    "Am pregătit acest video ca să mă asigur că obții rezultate maxime. "
                    "Urmărește-l cu atenție!"
        )
    if VIDEO_CALORII:
        await bot.send_video(
            uid, VIDEO_CALORII,
            caption="🥗 TOTUL DESPRE CALORII\n\n"
                    "În acest video îți explic cum să îți gestionezi alimentația "
                    "fără să te simți privată de mâncarea preferată. Vizionare plăcută!"
        )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="ℹ️ Suport", url=LINK_SUPORT))
    await bot.send_message(
        uid,
        "Sunt alături de tine în această transformare! Dacă ai întrebări pe parcurs, "
        "folosește butonul de suport. Spor la treabă! 💪✨",
        reply_markup=builder.as_markup()
    )

    await callback.message.edit_caption(caption="✅ LIVRAT CU SUCCES", parse_mode="Markdown")
    await callback.answer("Materiale trimise!")

# --- Reject Payment ---
@dp.callback_query(F.data.startswith("reject_"))
async def reject(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🆘 Suport", url=LINK_SUPORT))
    await bot.send_message(
        uid,
        "😔 Plata nu a putut fi confirmată. Contactează suport.",
        reply_markup=builder.as_markup()
    )
    await callback.message.edit_caption(caption="❌ PLATĂ RESPINSĂ", parse_mode="Markdown")
    await callback.answer("Notificare de respingere trimisă.")

# --- Give Review Handler ---
@dp.callback_query(F.data == "give_review")
async def give_review_start(callback: types.CallbackQuery):
    # Verificăm că userul chiar a cumpărat
    if not check_db_flag(callback.from_user.id, "has_access"):
        await callback.answer("⚠️ Această opțiune e doar pentru clienți.", show_alert=True)
        return
    await callback.message.answer(
        "✍️ Mulțumesc că vrei să lași un review! 🌸\n\n"
        "Scrie-mi în câteva cuvinte:\n"
        " • Ce ți-a plăcut cel mai mult la ghid?\n"
        " • Ce rezultate ai observat?\n\n"
        "Scrie mesajul tău chiar aici 👇"
    )
    await callback.answer()

@dp.message(F.text & ~F.from_user.id.in_({ADMIN_ID}))
async def handle_review_text(message: types.Message):
    user_id = message.from_user.id

    # Procesăm mesajul ca review doar dacă userul are acces și review_sent=1
    # (adică a primit cererea de review dar nu a trimis încă unul)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT has_access, review_sent FROM users WHERE user_id=%s",
        (user_id,)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return  # user necunoscut, ignorăm

    has_access, review_sent = row

    if has_access and review_sent == 1:
        # Salvăm review_sent=2 ca să știm că a trimis review
        update_db(user_id, "review_sent", 2)

        # Trimitem bonusul
        if FREE_WORKOUT_ID:
            try:
                await bot.send_video(
                    user_id,
                    FREE_WORKOUT_ID,
                    caption="🎁 *VIDEO ANTRENAMENT BONUS*\n\n"
                            "Mulțumesc din suflet pentru review! "
                            "Ești minunată și mă bucur că ești în această comunitate. 💪✨",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.warning(f"Bonus video eșuat pentru {user_id}: {e}")
                await message.answer("⚠️ A apărut o problemă la trimiterea bonusului. Contactează suport.")
        else:
            await message.answer(
                "🎁 Mulțumesc pentru review! Bonusul va fi trimis în curând. 🌸"
            )

        # Forwarding review la admin
        await bot.send_message(
            ADMIN_ID,
            f"⭐️ *REVIEW NOU* de la @{message.from_user.username} (ID: {user_id}):\n\n"
            f"{message.text}",
            parse_mode="Markdown"
        )

# --- Auto Followup Loop ---
async def auto_followup_loop():
    while True:
        await asyncio.sleep(3600)
        conn = None
        try:
            conn = get_conn()
            cursor = conn.cursor()
            now = datetime.datetime.now()

            # -------------------------------------------------------
            # FOLLOWUP POST-TEST
            # Segment: a făcut testul dar NU a cumpărat încă.
            # Mesaj 1 — la 1h după test: empatie + legătură cu ghidul
            # Mesaj 2 — la 6h după test: social proof + urgență blândă
            # -------------------------------------------------------
            cursor.execute("""
                SELECT user_id, test_date, test_followup
                FROM users
                WHERE a_deschis_test=TRUE
                  AND has_access=FALSE
                  AND test_followup < 2
                  AND test_date IS NOT NULL
            """)
            post_test_users = cursor.fetchall()

            for user in post_test_users:
                u_id, test_date, test_followup = user
                hours_since_test = (now - test_date).total_seconds() / 3600
                try:
                    if test_followup == 0 and hours_since_test >= 1:
                        await bot.send_message(
                            u_id,
                            "Hei! 🤍 Dacă unele exerciții din test au fost grele, "
                            "e absolut normal — mușchii abdominali slăbiți nu se tonifiează "
                            "din întâmplare, dar se tonifiează cu metodă.\n\n"
                            "Exact asta îți arată ghidul meu — pas cu pas, fără complicații. 👇",
                            reply_markup=premium_menu()
                        )
                        cursor.execute(
                            "UPDATE users SET test_followup=1 WHERE user_id=%s",
                            (u_id,)
                        )
                        conn.commit()

                    elif test_followup == 1 and hours_since_test >= 6:
                        await bot.send_message(
                            u_id,
                            "Astăzi mai multe fete care au făcut același test ca tine "
                            "au decis să înceapă ghidul. 🌿\n\n"
                            "Multe mi-au spus că prima săptămână le-a surprins cel mai mult. "
                            "Tu ești următoarea? ✨",
                            reply_markup=premium_menu()
                        )
                        cursor.execute(
                            "UPDATE users SET test_followup=2 WHERE user_id=%s",
                            (u_id,)
                        )
                        conn.commit()
                except Exception as e:
                    logging.warning(f"Post-test followup eșuat pentru {u_id}: {e}")

            # -------------------------------------------------------
            # FOLLOWUP VÂNZARE
            # Folosim last_followup_sent (nu join_date) ca să nu trimitem
            # prea des. Trimitem followup-ul 1 la 2h după join,
            # followup-ul 2 la minimum 22h după followup-ul 1.
            # -------------------------------------------------------
            cursor.execute("""
                SELECT user_id, join_date, last_followup, last_followup_sent
                FROM users
                WHERE has_access=FALSE AND last_followup < 2
            """)
            prospects = cursor.fetchall()

            for user in prospects:
                u_id, join_date, last_followup, last_followup_sent = user
                hours_since_join = (now - join_date).total_seconds() / 3600
                try:
                    if last_followup == 0 and hours_since_join >= 2:
                        await bot.send_message(
                            u_id,
                            "Hei! ✨ Nu uita de tine. "
                            "Multe fete au scăpat de balonare cu acest ghid. 🌿",
                            reply_markup=main_menu()
                        )
                        cursor.execute(
                            "UPDATE users SET last_followup=1, last_followup_sent=%s WHERE user_id=%s",
                            (now, u_id)
                        )
                        conn.commit()

                    elif last_followup == 1 and last_followup_sent:
                        hours_since_last = (now - last_followup_sent).total_seconds() / 3600
                        if hours_since_last >= 22:
                            await bot.send_message(
                                u_id,
                                "Bună! ✨ Un mic secret: Hidratarea corectă e baza unui abdomen plat. 📲",
                                reply_markup=main_menu()
                            )
                            cursor.execute(
                                "UPDATE users SET last_followup=2, last_followup_sent=%s WHERE user_id=%s",
                                (now, u_id)
                            )
                            conn.commit()
                except Exception as e:
                    logging.warning(f"Followup vânzare eșuat pentru {u_id}: {e}")

            # -------------------------------------------------------
            # FOLLOWUP PENDING BUYERS
            # Se trimite O SINGURĂ DATĂ, la 1-5h după join, dacă userul
            # a apăsat Cumpără dar nu a plătit încă.
            # -------------------------------------------------------
            cursor.execute("""
                SELECT user_id, join_date
                FROM users
                WHERE a_clicat_cumpara=TRUE
                  AND has_access=FALSE
                  AND pending_followup_sent=FALSE
            """)
            pending_buyers = cursor.fetchall()

            for user in pending_buyers:
                u_id, join_date = user
                hours_since_join = (now - join_date).total_seconds() / 3600
                if 1 <= hours_since_join < 5:
                    try:
                        builder = InlineKeyboardBuilder()
                        builder.row(InlineKeyboardButton(text="💸 Achită prin MIA", url=LINK_MIA))
                        builder.row(InlineKeyboardButton(text="ℹ️ Am o întrebare", url=LINK_SUPORT))
                        await bot.send_message(
                            u_id,
                            "Dacă ai vreo întrebare, trimite-o la suport, o să îți răspundem la orice ✨",
                            reply_markup=builder.as_markup()
                        )
                        cursor.execute(
                            "UPDATE users SET pending_followup_sent=TRUE WHERE user_id=%s",
                            (u_id,)
                        )
                        conn.commit()
                    except Exception as e:
                        logging.warning(f"Pending followup eșuat pentru {u_id}: {e}")

            # -------------------------------------------------------
            # FOLLOWUP REVIEW — la 24h după cumpărare, o singură dată
            # -------------------------------------------------------
            cursor.execute("""
                SELECT user_id, purchase_date
                FROM users
                WHERE has_access=TRUE AND review_sent=0
            """)
            customers = cursor.fetchall()

            for user in customers:
                u_id, p_date = user
                if not p_date:
                    continue
                hours_since_purchase = (now - p_date).total_seconds() / 3600
                if hours_since_purchase >= 24:
                    try:
                        builder = InlineKeyboardBuilder()
                        builder.row(InlineKeyboardButton(text="✍️ Trimite un Review", callback_data="give_review"))
                        builder.row(InlineKeyboardButton(text="ℹ️ Suport", url=LINK_SUPORT))
                        await bot.send_message(
                            u_id,
                            "Bună! ✨ A trecut o zi de când ai ghidul. Ai reușit să-l răsfoiești?\n\n"
                            "Dacă îmi lași o recenzie scurtă, îți trimit cadou un Video Antrenament Bonus! 🎁",
                            reply_markup=builder.as_markup()
                        )
                        cursor.execute(
                            "UPDATE users SET review_sent=1 WHERE user_id=%s",
                            (u_id,)
                        )
                        conn.commit()
                    except Exception as e:
                        logging.warning(f"Review followup eșuat pentru {u_id}: {e}")

            cursor.close()

        except Exception as e:
            logging.error(f"Eroare critică în followup loop: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

# --- Main ---
async def main():
    init_db()
    asyncio.create_task(auto_followup_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
