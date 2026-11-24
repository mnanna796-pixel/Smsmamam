import os
import asyncio
import logging
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor

from aiogram import Bot, Dispatcher, F, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oldx-bot")

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@OLDXXbotkanal")
CHANNEL_URL = "https://t.me/OLDXXbotkanal"
WEBAPP_URL = "https://smsmamam-3.onrender.com" # Mini App linkiniz

if not TOKEN or not DATABASE_URL:
    raise SystemExit("XƏTA: BOT_TOKEN və ya DATABASE_URL tapılmadı.")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------- Verilənlər bazası ----------
def db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY, full_name TEXT, 
        azn_balance NUMERIC(10,2) DEFAULT 0, 
        coin_balance INTEGER DEFAULT 0,
        referal_id BIGINT, referal_count INTEGER DEFAULT 0, 
        last_bonus TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY, category TEXT, name TEXT, 
        description TEXT, price NUMERIC(10,2), is_active BOOLEAN DEFAULT TRUE
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY, user_id BIGINT, product_id INTEGER, product_name TEXT, 
        price NUMERIC(10,2), status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    
    c.execute("SELECT 1 FROM users WHERE user_id=%s", (ADMIN_ID,))
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id, full_name, azn_balance, coin_balance) VALUES (%s, %s, 100, 1000)", (ADMIN_ID, "Admin"))
        conn.commit()
    c.close()
    conn.close()

def get_user(uid):
    conn = db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT * FROM users WHERE user_id=%s", (uid,))
    u = c.fetchone()
    c.close()
    conn.close()
    return u

def update_balance(uid, azn=0, coin=0):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE users SET azn_balance = azn_balance + %s, coin_balance = coin_balance + %s WHERE user_id=%s", (azn, coin, uid))
    conn.commit()
    c.close()
    conn.close()

# ---------- Məcburi Abunəlik ----------
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception:
        return False

def sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanala Abunə Ol", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Abunəliyi yoxla", callback_data="check_sub")]
    ])

# ---------- Klaviaturalar ----------
def main_menu(uid):
    kb = [
        [InlineKeyboardButton(text="🛒 Mağazaya keç (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="💰 Balansım", callback_data="balance")],
        [InlineKeyboardButton(text="🎁 Gündəlik bonus", callback_data="bonus")],
        [InlineKeyboardButton(text="👥 Referal sistemi", callback_data="referal")],
        [InlineKeyboardButton(text="📢 Rəsmi kanal", url=CHANNEL_URL)],
    ]
    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="👨‍💻 Admin Paneli", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Məhsul əlavə et", callback_data="add_product")],
        [InlineKeyboardButton(text="📋 Sifarişlərə bax", callback_data="view_orders")],
        [InlineKeyboardButton(text="🔙 Geri", callback_data="back_main")]
    ])

# ---------- /start ----------
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try: ref_id = int(args[1][4:])
        except: ref_id = None

    user = get_user(uid)
    if not user:
        conn = db()
        c = conn.cursor()
        c.execute("INSERT INTO users (user_id, full_name, referal_id) VALUES (%s, %s, %s)", (uid, message.from_user.full_name, ref_id))
        conn.commit()
        c.close()
        conn.close()
        
        if ref_id and ref_id != uid and get_user(ref_id):
            update_balance(ref_id, coin=5)
            conn = db()
            c = conn.cursor()
            c.execute("UPDATE users SET referal_count = referal_count + 1 WHERE user_id=%s", (ref_id,))
            conn.commit()
            c.close()
            conn.close()
            try: await bot.send_message(ref_id, "🎉 Yeni referalınız var! +5 coin qazandınız.")
            except: pass

    if not await is_subscribed(uid):
        await message.answer(
            "👑 <b>亗 𝙊𝙇𝘿 𝙓 亗 BOT</b>\n\n"
            "Botdan istifadə etmək üçün əvvəlcə kanalımıza abunə olmalısınız! 👇",
            reply_markup=sub_keyboard()
        )
        return

    await message.answer(
        f"👑 <b>亗 𝙊𝙇𝘿 𝙓 亗 BOT</b>\n\n"
        f"Salam, {html.bold(message.from_user.full_name)}! 👋\n\n"
        f"Rəsmi satış və rəqəmsal xidmət platformamıza xoş gəlmisiniz!\n\n"
        f"🎮 PUBG UC\n🪙 TikTok Jetonları\n📱 SMM Xidmətləri\n"
        f"💰 Balans artırma\n🎁 Promo kodlar\n👥 Referal qazancı\n🎉 Gündəlik bonuslar\n\n"
        f"Bütün xidmətlər bir platformada!",
        reply_markup=main_menu(uid)
    )

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: CallbackQuery):
    if await is_subscribed(cb.from_user.id):
        await cb.message.edit_text(
            f"👑 <b>亗 𝙊𝙇𝘿 𝙓 亗 BOT</b>\n\n"
            f"Salam, {html.bold(cb.from_user.full_name)}! 👋\n\n"
            f"Rəsmi satış və rəqəmsal xidmət platformamıza xoş gəlmisiniz!",
            reply_markup=main_menu(cb.from_user.id)
        )
    else:
        await cb.answer("❌ Siz hələ kanala abunə olmamısınız!", show_alert=True)

@dp.callback_query(F.data == "back_main")
async def cb_back_main(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Əsas menyu:", reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

# ---------- Balans ----------
@dp.callback_query(F.data == "balance")
async def cb_balance(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"💰 <b>BALANSIM</b>\n\n"
        f"AZN balansı: <b>{u['azn_balance']} AZN</b>\n"
        f"Coin balansı: <b>{u['coin_balance']} coin</b>",
        reply_markup=main_menu(cb.from_user.id)
    )
    await cb.answer()

# ---------- Referal ----------
@dp.callback_query(F.data == "referal")
async def cb_referal(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{cb.from_user.id}"
    await cb.message.edit_text(
        f"👥 <b>REFERAL SİSTEMİ</b>\n\n"
        f"Sizin linkiniz:\n<code>{link}</code>\n\n"
        f"Dəvət etdiyiniz: {u['referal_count']} nəfər\nHər dəvətə: 5 coin",
        reply_markup=main_menu(cb.from_user.id)
    )
    await cb.answer()

# ---------- Bonus ----------
@dp.callback_query(F.data == "bonus")
async def cb_bonus(cb: CallbackQuery):
    uid = cb.from_user.id
    u = get_user(uid)
    today = date.today().isoformat()
    if u["last_bonus"] == today:
        return await cb.answer("❌ Bu gün artıq bonus almısınız!", show_alert=True)
    
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE users SET coin_balance = coin_balance + 3, last_bonus = %s WHERE user_id=%s", (today, uid))
    conn.commit()
    c.close()
    conn.close()
    await cb.message.edit_text(
        f"🎁 <b>Gündəlik bonus alındı!</b>\n+3 coin\n\nBalans: {get_user(uid)['coin_balance']} coin",
        reply_markup=main_menu(uid)
    )
    await cb.answer("✅ +3 coin")

# ---------- ADMIN PANEL ----------
@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    await cb.message.edit_text("👨‍💻 <b>Admin Paneli</b>", reply_markup=admin_menu())
    await cb.answer()

class AddProduct(StatesGroup):
    name = State()
    price = State()
    category = State()

@dp.callback_query(F.data == "add_product")
async def cb_add_product(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    await cb.message.edit_text("📝 Məhsulun adını yazın:")
    await state.set_state(AddProduct.name)
    await cb.answer()

@dp.message(AddProduct.name)
async def process_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddProduct.price)
    await message.answer("💰 Məhsulun qiymətini (AZN) yazın:")

@dp.message(AddProduct.price)
async def process_add_price(message: Message, state: FSMContext):
    try: price = float(message.text)
    except: return await message.answer("Yalnız rəqəm yazın.")
    await state.update_data(price=price)
    await state.set_state(AddProduct.category)
    await message.answer("📂 Kateqoriyanı seçin:\nmarket / pubg / tiktok / smm")

@dp.message(AddProduct.category)
async def process_add_category(message: Message, state: FSMContext):
    category = message.text.lower()
    if category not in ["market", "pubg", "tiktok", "smm"]:
        return await message.answer("Yalnız market, pubg, tiktok, smm yazın.")
    
    data = await state.get_data()
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO products (name, price, category) VALUES (%s, %s, %s)", (data['name'], data['price'], category))
    conn.commit()
    c.close()
    conn.close()
    
    await state.clear()
    await message.answer(f"✅ Məhsul əlavə edildi: <b>{data['name']}</b> - {data['price']} AZN ({category})", reply_markup=main_menu(message.from_user.id))

# ---------- START ----------
async def start_polling():
    init_db()
    logger.info("Bot işə düşür...")
    await dp.start_polling(bot, handle_signals=False)

if __name__ == "__main__":
    asyncio.run(start_polling())
