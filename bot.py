import os
import asyncio
import logging
from datetime import datetime, date
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor

from aiogram import Bot, Dispatcher, F, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("market-bot")

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL")

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
    # İstifadəçilər
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY, full_name TEXT, balance INTEGER DEFAULT 0, 
        referal_id BIGINT, referal_count INTEGER DEFAULT 0, last_bonus TEXT
    )""")
    # Market məhsulları
    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY, name TEXT, price INTEGER, is_active BOOLEAN DEFAULT TRUE
    )""")
    # Sifarişlər
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY, user_id BIGINT, product_id INTEGER, product_name TEXT, 
        price INTEGER, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    
    # Admini qeydiyyata alırıq
    c.execute("SELECT 1 FROM users WHERE user_id=%s", (ADMIN_ID,))
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id, full_name, balance) VALUES (%s, %s, 1000)", (ADMIN_ID, "Admin"))
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

def update_balance(uid, amount):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (amount, uid))
    conn.commit()
    c.close()
    conn.close()

# ---------- FSM ----------
class BuyProduct(StatesGroup):
    product_id = State()

class AddProduct(StatesGroup):
    name = State()
    price = State()

# ---------- Klaviaturalar ----------
def main_menu(uid):
    kb = [
        [InlineKeyboardButton(text="🛒 Market", callback_data="market")],
        [InlineKeyboardButton(text="💰 Balansım", callback_data="balance")],
        [InlineKeyboardButton(text="👥 Referal sistemi", callback_data="referal")],
        [InlineKeyboardButton(text="🎁 Gündəlik bonus", callback_data="bonus")],
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
            update_balance(ref_id, 5)
            conn = db()
            c = conn.cursor()
            c.execute("UPDATE users SET referal_count = referal_count + 1 WHERE user_id=%s", (ref_id,))
            conn.commit()
            c.close()
            conn.close()
            try: await bot.send_message(ref_id, "🎉 Yeni referalınız var! +5 coin qazandınız.")
            except: pass

    await message.answer(
        f"Salam, {html.bold(message.from_user.full_name)}! 👋\n\nXoş gəldiniz!",
        reply_markup=main_menu(uid)
    )

@dp.callback_query(F.data == "back_main")
async def cb_back_main(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Əsas menyu:", reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

# ---------- Balans ----------
@dp.callback_query(F.data == "balance")
async def cb_balance(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    await cb.message.edit_text(f"💰 <b>Balansınız:</b> {u['balance']} coin", reply_markup=main_menu(cb.from_user.id))
    await cb.answer()

# ---------- Referal ----------
@dp.callback_query(F.data == "referal")
async def cb_referal(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{cb.from_user.id}"
    await cb.message.edit_text(
        f"👥 <b>Referal sistemi</b>\n\nSizin linkiniz:\n<code>{link}</code>\n\n"
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
    c.execute("UPDATE users SET balance = balance + 3, last_bonus = %s WHERE user_id=%s", (today, uid))
    conn.commit()
    c.close()
    conn.close()
    await cb.message.edit_text(f"🎁 <b>Gündəlik bonus alındı!</b>\n+3 coin\n\nBalans: {get_user(uid)['balance']} coin", reply_markup=main_menu(uid))
    await cb.answer("✅ +3 coin")

# ---------- MARKET ----------
@dp.callback_query(F.data == "market")
async def cb_market(cb: CallbackQuery):
    conn = db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT * FROM products WHERE is_active = TRUE")
    products = c.fetchall()
    c.close()
    conn.close()
    
    if not products:
        return await cb.answer("Marketdə hələ məhsul yoxdur.", show_alert=True)
    
    await cb.message.edit_text("🛒 <b>Market</b>\n\nMəhsul seçin:", reply_markup=main_menu(cb.from_user.id))
    
    for p in products:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🛍 Al ({p['price']} coin)", callback_data=f"buy_{p['id']}")]
        ])
        await cb.message.answer(f"<b>{p['name']}</b>\nQiymət: {p['price']} coin", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(cb: CallbackQuery):
    product_id = int(cb.data.replace("buy_", ""))
    uid = cb.from_user.id
    u = get_user(uid)
    
    conn = db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT * FROM products WHERE id=%s AND is_active=TRUE", (product_id,))
    p = c.fetchone()
    
    if not p:
        c.close(); conn.close()
        return await cb.answer("Məhsul tapılmadı.", show_alert=True)
    
    if u["balance"] < p["price"]:
        c.close(); conn.close()
        return await cb.answer("❌ Balansınız kifayət etmir!", show_alert=True)
    
    update_balance(uid, -p["price"])
    
    c.execute("INSERT INTO orders (user_id, product_id, product_name, price) VALUES (%s, %s, %s, %s) RETURNING id", 
              (uid, product_id, p["name"], p["price"]))
    order_id = c.fetchone()["id"]
    conn.commit()
    c.close()
    conn.close()
    
    await cb.message.edit_text(f"✅ <b>Sifariş qeydə alındı!</b>\n\nMəhsul: {p['name']}\nÖdənildi: {p['price']} coin\nSifariş ID: #{order_id}\n\nAdmin tezliklə sizinlə əlaqə saxlayacaq.", reply_markup=main_menu(uid))
    await cb.answer("✅ Sifariş qəbul edildi!")
    
    try:
        await bot.send_message(ADMIN_ID, 
            f"🔔 <b>YENİ SİFARİŞ!</b>\n\n"
            f"👤 İstifadəçi: {cb.from_user.full_name}\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📦 Məhsul: {p['name']}\n"
            f"💰 Qiymət: {p['price']} coin\n"
            f"📋 Sifariş ID: #{order_id}"
        )
    except: pass

# ---------- ADMIN PANEL ----------
@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    await cb.message.edit_text("👨‍💻 <b>Admin Paneli</b>", reply_markup=admin_menu())
    await cb.answer()

@dp.callback_query(F.data == "add_product")
async def cb_add_product(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    await state.set_state(AddProduct.name)
    await cb.message.edit_text("📝 Məhsulun adını yazın:")
    await cb.answer()

@dp.message(AddProduct.name)
async def process_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddProduct.price)
    await message.answer("💰 Məhsulun qiymətini (coin) yazın:")

@dp.message(AddProduct.price)
async def process_add_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Yalnız rəqəm yazın.")
    data = await state.get_data()
    
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO products (name, price) VALUES (%s, %s)", (data['name'], int(message.text)))
    conn.commit()
    c.close()
    conn.close()
    
    await state.clear()
    await message.answer(f"✅ Məhsul əlavə edildi: <b>{data['name']}</b> - {message.text} coin", reply_markup=main_menu(message.from_user.id))

@dp.callback_query(F.data == "view_orders")
async def cb_view_orders(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    conn = db()
    c = conn.cursor(cursor_factory=DictCursor)
    c.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 10")
    orders = c.fetchall()
    c.close()
    conn.close()
    
    if not orders:
        return await cb.answer("Sifariş yoxdur.", show_alert=True)
    
    text = "📋 <b>Son 10 sifariş:</b>\n\n"
    for o in orders:
        text += f"#{o['id']} - {o['product_name']} - {o['price']} coin - <code>{o['user_id']}</code>\n"
    
    await cb.message.edit_text(text, reply_markup=admin_menu())
    await cb.answer()

# ---------- START ----------
async def start_polling():
    init_db()
    logger.info("Bot işə düşür...")
    await dp.start_polling(bot, handle_signals=False)

if __name__ == "__main__":
    asyncio.run(start_polling())
