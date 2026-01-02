import asyncio
import logging
import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)

# ========== КОНФИГУРАЦИЯ ==========
# ТОЛЬКО ЭТО из переменных окружения:
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "").split(","))) if os.environ.get("ADMIN_IDS") else []
CRYPTOBOT_TOKEN = os.environ.get("CRYPTOBOT_TOKEN", "")

# ВСЁ ОСТАЛЬНОЕ В КОДЕ:
CARD_NUMBER = "2200700527205453"  # Ваша карта
STAR_RATE = 1.5  # 1 звезда = 1.5 руб
USD_RATE = 84.0  # 1 доллар = 84 руб

# Цены на премиум
PREMIUM_PRICES = {
    "3months": {
        "rub": 1124.11,
        "usd": 14.12,
        "name": "3 месяца"
    },
    "6months": {
        "rub": 1498.81,
        "usd": 14.12,
        "name": "6 месяцев"
    },
    "1year": {
        "rub": 2716.59,
        "usd": 34.12,
        "name": "1 год"
    }
}

# Ваше фото (file_id)
MAIN_PHOTO_ID = "AgACAgIAAxkBAAFAAYFpVl91J1kMKJxRmeWE0cL1JL4bMwACTA1rG3xAsEokOAkz6UTdpAEAAwIAA3kAAzgE"

# Ссылки
REPUTATION_CHANNEL = "https://t.me/+3pbAABRgo1ljOTJi"
NEWS_CHANNEL = "https://t.me/NewsDigistars"
SUPPORT_USER = "@swordSar"

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self, db_name="digistore.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_type TEXT,
            recipient TEXT,
            details TEXT,
            amount_rub REAL,
            amount_usd REAL,
            payment_method TEXT,
            payment_status TEXT DEFAULT 'pending',
            admin_checked INTEGER DEFAULT 0,
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payment_date TIMESTAMP,
            completed_date TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS crypto_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            invoice_id TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders (id)
        )''')
        
        self.conn.commit()
    
    def add_user(self, user_id, username, full_name):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name)
        )
        self.conn.commit()
    
    def add_order(self, user_id, order_type, recipient, details, amount_rub, amount_usd, payment_method):
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO orders 
            (user_id, order_type, recipient, details, amount_rub, amount_usd, payment_method) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, order_type, recipient, details, amount_rub, amount_usd, payment_method)
        )
        order_id = cursor.lastrowid
        self.conn.commit()
        return order_id
    
    def update_order_status(self, order_id, status):
        cursor = self.conn.cursor()
        
        if status == 'completed':
            cursor.execute(
                "UPDATE orders SET payment_status = ?, completed_date = CURRENT_TIMESTAMP WHERE id = ?",
                (status, order_id)
            )
        elif status == 'paid':
            cursor.execute(
                "UPDATE orders SET payment_status = ?, payment_date = CURRENT_TIMESTAMP WHERE id = ?",
                (status, order_id)
            )
        else:
            cursor.execute(
                "UPDATE orders SET payment_status = ? WHERE id = ?",
                (status, order_id)
            )
        
        self.conn.commit()
        return cursor.rowcount > 0
    
    def get_pending_orders(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, user_id, order_type, recipient, details, amount_rub, payment_method, order_date 
            FROM orders 
            WHERE payment_status IN ('pending', 'waiting') 
            ORDER BY order_date DESC
        """)
        return cursor.fetchall()
    
    def get_active_orders(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, user_id, order_type, recipient, details, amount_rub, payment_method, order_date 
            FROM orders 
            WHERE payment_status = 'paid' 
            ORDER BY order_date DESC
        """)
        return cursor.fetchall()
    
    def get_completed_orders(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, user_id, order_type, recipient, details, amount_rub, payment_method, order_date, completed_date 
            FROM orders 
            WHERE payment_status = 'completed' 
            ORDER BY completed_date DESC
            LIMIT 50
        """)
        return cursor.fetchall()
    
    def get_order_info(self, order_id):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT user_id, order_type, recipient, details, amount_rub, payment_method, payment_status 
            FROM orders WHERE id = ?
        """, (order_id,))
        return cursor.fetchone()
    
    def get_statistics(self):
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE payment_status = 'completed'")
        completed_orders = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(amount_rub) FROM orders WHERE payment_status = 'completed'")
        total_revenue = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE payment_status IN ('pending', 'waiting')")
        pending_orders = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE payment_status = 'paid'")
        paid_orders = cursor.fetchone()[0]
        
        return {
            "total_users": total_users,
            "completed_orders": completed_orders,
            "total_revenue": total_revenue,
            "pending_orders": pending_orders,
            "paid_orders": paid_orders
        }

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()

user_states = {}

# ========== КЛАВИАТУРЫ ==========
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ Купить звезды", callback_data="buy_stars")],
        [InlineKeyboardButton(text="👑 Купить премиум", callback_data="buy_premium")],
        [InlineKeyboardButton(text="💱 Обмен валют", callback_data="exchange")],
        [InlineKeyboardButton(text="📊 Информация", callback_data="info")],
        [InlineKeyboardButton(text="🆘 Тех поддержка", url=f"https://t.me/{SUPPORT_USER[1:] if SUPPORT_USER.startswith('@') else SUPPORT_USER}")]
    ])

def back_to_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

def payment_methods_kb(order_type, order_data):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перевод на карту", callback_data=f"pay_card_{order_type}_{order_data}")],
    ])
    
    if CRYPTOBOT_TOKEN:
        keyboard.inline_keyboard.insert(0, 
            [InlineKeyboardButton(text="💎 CryptoBot", callback_data=f"pay_crypto_{order_type}_{order_data}")]
        )
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_{order_type}")])
    
    return keyboard

def card_payment_kb(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я перевел", callback_data=f"card_paid_{order_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def admin_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="⏳ Ожидают проверки", callback_data="admin_pending")],
        [InlineKeyboardButton(text="💰 Оплаченные", callback_data="admin_paid")],
        [InlineKeyboardButton(text="✅ Выполненные", callback_data="admin_completed")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="main_menu")]
    ])

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name
    
    db.add_user(user_id, username, full_name)
    
    try:
        await message.answer_photo(
            photo=MAIN_PHOTO_ID,
            caption=(
                "🪐 **Digi Store - Главное меню**\n\n"
                "C помощью нашего магазина вы можете:\n"
                "• ⭐️ Купить Telegram Stars\n"
                "• 👑 Купить Telegram Premium\n"
                "• 💱 Обменять рубли на доллары\n\n"
                f"📊 **Текущие курсы:**\n"
                f"• 1 звезда = {STAR_RATE} RUB\n"
                f"• 1 USD = {USD_RATE} RUB\n\n"
                "Выберите действие:"
            ),
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
    except Exception as e:
        # Если фото не работает, отправляем текст
        await message.answer(
            text=(
                "🪐 **Digi Store - Главное меню**\n\n"
                "C помощью нашего магазина вы можете:\n"
                "• ⭐️ Купить Telegram Stars\n"
                "• 👑 Купить Telegram Premium\n"
                "• 💱 Обменять рубли на доллары\n\n"
                f"📊 **Текущие курсы:**\n"
                f"• 1 звезда = {STAR_RATE} RUB\n"
                f"• 1 USD = {USD_RATE} RUB\n\n"
                "Выберите действие:"
            ),
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )

@dp.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: types.CallbackQuery):
    try:
        await callback.message.edit_caption(
            caption=(
                "🪐 **Digi Store - Главное меню**\n\n"
                "C помощью нашего магазина вы можете:\n"
                "• ⭐️ Купить Telegram Stars\n"
                "• 👑 Купить Telegram Premium\n"
                "• 💱 Обменять рубли на доллары\n\n"
                f"📊 **Текущие курсы:**\n"
                f"• 1 звезда = {STAR_RATE} RUB\n"
                f"• 1 USD = {USD_RATE} RUB\n\n"
                "Выберите действие:"
            ),
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
    except:
        await callback.message.edit_text(
            text=(
                "🪐 **Digi Store - Главное меню**\n\n"
                "C помощью нашего магазина вы можете:\n"
                "• ⭐️ Купить Telegram Stars\n"
                "• 👑 Купить Telegram Premium\n"
                "• 💱 Обменять рубли на доллары\n\n"
                f"📊 **Текущие курсы:**\n"
                f"• 1 звезда = {STAR_RATE} RUB\n"
                f"• 1 USD = {USD_RATE} RUB\n\n"
                "Выберите действие:"
            ),
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
    await callback.answer()

# ========== ПОКУПКА ЗВЕЗД ==========
@dp.callback_query(F.data == "buy_stars")
async def buy_stars_handler(callback: types.CallbackQuery):
    await callback.message.edit_caption(
        caption=(
            "⭐️ **Покупка Telegram Stars**\n\n"
            f"Курс: **1 звезда = {STAR_RATE} RUB**\n"
            "Диапазон: от 50 до 1,000,000 звезд\n\n"
            "✏️ Введите username получателя:"
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Ввести получателя", callback_data="enter_stars_recipient")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "enter_stars_recipient")
async def enter_stars_recipient_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_states[user_id] = {"action": "waiting_stars_recipient"}
    
    await callback.message.edit_caption(
        caption=(
            "✏️ **Введите username получателя**\n\n"
            "Формат: @username или просто username\n"
            "Пример: @username\n\n"
            "Отправьте username сообщением:"
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_stars")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

# ========== ПОКУПКА ПРЕМИУМА ==========
@dp.callback_query(F.data == "buy_premium")
async def buy_premium_handler(callback: types.CallbackQuery):
    price_text = ""
    for key, value in PREMIUM_PRICES.items():
        price_text += f"• {value['name']}: {value['rub']:.2f} RUB\n"
    
    await callback.message.edit_caption(
        caption=(
            "👑 **Покупка Telegram Premium**\n\n"
            "Выберите период:\n\n"
            f"{price_text}"
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="3 месяца", callback_data="premium_3months")],
            [InlineKeyboardButton(text="6 месяцев", callback_data="premium_6months")],
            [InlineKeyboardButton(text="1 год", callback_data="premium_1year")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("premium_"))
async def select_premium_period_handler(callback: types.CallbackQuery):
    period = callback.data.split("_")[1]
    
    if period in PREMIUM_PRICES:
        user_id = callback.from_user.id
        price = PREMIUM_PRICES[period]
        
        user_states[user_id] = {
            "action": "premium_selected",
            "period": period,
            "period_name": price["name"],
            "amount_rub": price["rub"]
        }
        
        await callback.message.edit_caption(
            caption=(
                f"👑 **Telegram Premium - {price['name']}**\n\n"
                f"Цена: **{price['rub']:.2f} RUB**\n\n"
                "✏️ Введите username получателя:"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Ввести получателя", callback_data="enter_premium_recipient")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_premium")]
            ]),
            parse_mode="Markdown"
        )
    
    await callback.answer()

@dp.callback_query(F.data == "enter_premium_recipient")
async def enter_premium_recipient_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_states:
        user_states[user_id]["action"] = "waiting_premium_recipient"
    
    await callback.message.edit_caption(
        caption=(
            "✏️ **Введите username получателя**\n\n"
            "Отправьте username сообщением:"
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_premium")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

# ========== ОБМЕН ВАЛЮТЫ ==========
@dp.callback_query(F.data == "exchange")
async def exchange_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_states[user_id] = {"action": "waiting_exchange_amount"}
    
    await callback.message.edit_caption(
        caption=(
            "💱 **Обмен валют**\n\n"
            f"Курс: **1 USD = {USD_RATE} RUB**\n\n"
            "Введите сумму в рублях:\n"
            "(Минимум: 100 RUB)"
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

# ========== ИНФОРМАЦИЯ ==========
@dp.callback_query(F.data == "info")
async def info_handler(callback: types.CallbackQuery):
    await callback.message.edit_caption(
        caption="📊 **Информация**\n\nВыберите раздел:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📈 Репутация", url=REPUTATION_CHANNEL)],
            [InlineKeyboardButton(text="📰 Новости", url=NEWS_CHANNEL)],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

# ========== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ==========
@dp.message()
async def handle_messages(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id not in user_states:
        await message.answer("Используйте меню", reply_markup=main_menu())
        return
    
    state = user_states[user_id]
    action = state.get("action", "")
    
    if action == "waiting_stars_recipient":
        recipient = text.replace("@", "")
        state["recipient"] = recipient
        state["action"] = "waiting_stars_amount"
        
        await message.answer(
            f"✅ Получатель: {recipient}\n\n"
            "Введите количество звезд (50-1,000,000):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_stars")]
            ])
        )
    
    elif action == "waiting_stars_amount":
        try:
            stars = int(text)
            if stars < 50 or stars > 1000000:
                await message.answer("❌ От 50 до 1,000,000")
                return
            
            amount_rub = stars * STAR_RATE
            amount_usd = amount_rub / USD_RATE
            recipient = state.get("recipient", "")
            
            state["stars_amount"] = stars
            state["amount_rub"] = amount_rub
            
            await message.answer(
                f"✅ {stars} звезд\n"
                f"💰 {amount_rub:.2f} RUB\n\n"
                "Выберите оплату:",
                reply_markup=payment_methods_kb("stars", f"{stars}_{recipient}")
            )
        except ValueError:
            await message.answer("❌ Введите число")
    
    elif action == "waiting_premium_recipient":
        recipient = text.replace("@", "")
        period = state.get("period")
        period_name = state.get("period_name")
        amount_rub = state.get("amount_rub")
        
        if period and amount_rub:
            state["recipient"] = recipient
            
            await message.answer(
                f"✅ Получатель: {recipient}\n"
                f"👑 {period_name}\n"
                f"💰 {amount_rub:.2f} RUB\n\n"
                "Выберите оплату:",
                reply_markup=payment_methods_kb("premium", f"{period}_{recipient}")
            )
    
    elif action == "waiting_exchange_amount":
        try:
            amount_rub = float(text)
            if amount_rub < 100:
                await message.answer("❌ Минимум 100 RUB")
                return
            
            amount_usd = amount_rub / USD_RATE
            state["exchange_amount"] = amount_rub
            
            await message.answer(
                f"✅ {amount_rub:.2f} RUB → {amount_usd:.2f} USD\n"
                f"Курс: 1 USD = {USD_RATE} RUB\n\n"
                "Выберите оплату:",
                reply_markup=payment_methods_kb("exchange", f"{amount_rub}")
            )
        except ValueError:
            await message.answer("❌ Введите число")

# ========== ОПЛАТА КАРТОЙ ==========
@dp.callback_query(F.data.startswith("pay_card_"))
async def card_payment_handler(callback: types.CallbackQuery):
    data = callback.data.split("_")
    order_type = data[2]
    order_data = data[3] if len(data) > 3 else ""
    
    user_id = callback.from_user.id
    user_state = user_states.get(user_id, {})
    
    if order_type == "stars":
        if "_" in order_data:
            stars_str, recipient = order_data.split("_")
            stars = int(stars_str)
            amount_rub = stars * STAR_RATE
            details = f'{{"stars": {stars}, "recipient": "{recipient}"}}'
        else:
            stars = user_state.get("stars_amount", 0)
            recipient = user_state.get("recipient", "")
            amount_rub = stars * STAR_RATE
            details = f'{{"stars": {stars}, "recipient": "{recipient}"}}'
        
        amount_usd = amount_rub / USD_RATE
        
        order_id = db.add_order(
            user_id, "stars", recipient, details, 
            amount_rub, amount_usd, "card"
        )
        
        caption = (
            f"⭐️ **Покупка звезд**\n\n"
            f"Получатель: {recipient}\n"
            f"Количество: {stars} ⭐️\n"
            f"Сумма: **{amount_rub:.2f} RUB**\n\n"
        )
    
    elif order_type == "premium":
        if "_" in order_data:
            period, recipient = order_data.split("_")
        else:
            period = user_state.get("period")
            recipient = user_state.get("recipient", "")
        
        price = PREMIUM_PRICES[period]
        amount_rub = price["rub"]
        amount_usd = price["usd"]
        details = f'{{"period": "{period}", "recipient": "{recipient}"}}'
        
        order_id = db.add_order(
            user_id, "premium", recipient, details, 
            amount_rub, amount_usd, "card"
        )
        
        caption = (
            f"👑 **Telegram Premium**\n\n"
            f"Период: {price['name']}\n"
            f"Получатель: {recipient}\n"
            f"Сумма: **{amount_rub:.2f} RUB**\n\n"
        )
    
    elif order_type == "exchange":
        amount_rub = float(order_data) if order_data else user_state.get("exchange_amount", 0)
        amount_usd = amount_rub / USD_RATE
        details = f'{{"amount_rub": {amount_rub}, "amount_usd": {amount_usd}}}'
        
        order_id = db.add_order(
            user_id, "exchange", "", details, 
            amount_rub, amount_usd, "card"
        )
        
        caption = (
            f"💱 **Обмен валют**\n\n"
            f"Отдаете: {amount_rub:.2f} RUB\n"
            f"Получаете: {amount_usd:.2f} USD\n"
            f"Курс: 1 USD = {USD_RATE} RUB\n\n"
        )
    
    caption += (
        "💳 **Перевод на карту:**\n"
        f"`{CARD_NUMBER}`\n\n"
        "**Инструкция:**\n"
        "1. Переведите точную сумму\n"
        "2. Сделайте скриншот перевода\n"
        "3. Нажмите ✅ Я перевел\n"
        "4. Админ проверит оплату\n\n"
        f"🆔 Заказ: #{order_id}"
    )
    
    await callback.message.edit_caption(
        caption=caption,
        reply_markup=card_payment_kb(order_id),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("card_paid_"))
async def card_paid_handler(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    
    db.update_order_status(order_id, "waiting")
    
    order_info = db.get_order_info(order_id)
    if order_info:
        user_id, order_type, recipient, details, amount_rub, payment_method, status = order_info
        
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"🆕 **Ожидает проверки**\n\n"
                    f"🆔 Заказ: #{order_id}\n"
                    f"👤 Пользователь: {callback.from_user.username or 'Нет юзернейма'}\n"
                    f"🆔 ID: {callback.from_user.id}\n"
                    f"💰 Сумма: {amount_rub:.2f} RUB\n"
                    f"📦 Тип: {order_type}\n"
                    f"👤 Получатель: {recipient}\n\n"
                    f"Для проверки: /check_{order_id}",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    await callback.answer(
        "✅ Заказ передан админу на проверку!\n"
        "Проверка занимает до 15 минут.",
        show_alert=True
    )
    
    await main_menu_handler(callback)

# ========== АДМИН ПАНЕЛЬ ==========
@dp.message(Command("admin"))
async def admin_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return
    
    stats = db.get_statistics()
    
    await message.answer(
        f"🛠️ **Админ панель**\n\n"
        f"📊 Статистика:\n"
        f"👥 Пользователей: {stats['total_users']}\n"
        f"✅ Выполнено: {stats['completed_orders']}\n"
        f"💰 Выручка: {stats['total_revenue']:.2f} RUB\n\n"
        f"⏳ Ожидают: {stats['pending_orders']}\n"
        f"💳 Оплачено: {stats['paid_orders']}\n\n"
        "Выберите раздел:",
        reply_markup=admin_menu_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен")
        return
    
    stats = db.get_statistics()
    
    await callback.message.edit_text(
        f"📊 **Статистика**\n\n"
        f"👥 Пользователи: {stats['total_users']}\n"
        f"✅ Выполнено заказов: {stats['completed_orders']}\n"
        f"💰 Общая выручка: {stats['total_revenue']:.2f} RUB\n\n"
        f"⏳ Ожидают проверки: {stats['pending_orders']}\n"
        f"💳 Оплачено: {stats['paid_orders']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_pending")
async def admin_pending_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен")
        return
    
    orders = db.get_pending_orders()
    
    if not orders:
        await callback.message.edit_text(
            "✅ Нет заказов ожидающих проверки",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
            ])
        )
        return
    
    text = "⏳ **Ожидают проверки:**\n\n"
    
    for order in orders[:10]:
        order_id, user_id, order_type, recipient, details, amount_rub, payment_method, order_date = order
        
        emoji = "⭐️" if order_type == "stars" else "👑" if order_type == "premium" else "💱"
        text += f"{emoji} #{order_id}\n"
        text += f"👤 User ID: {user_id}\n"
        
        if order_type == "stars":
            text += f"⭐️ Звезды для: {recipient}\n"
        elif order_type == "premium":
            text += f"👑 Премиум для: {recipient}\n"
        elif order_type == "exchange":
            text += f"💱 Обмен валют\n"
        
        text += f"💰 {amount_rub:.2f} RUB\n"
        text += f"💳 {payment_method}\n"
        text += f"📅 {order_date}\n"
        text += f"🔗 /check_{order_id}\n"
        text += "─" * 20 + "\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_pending")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_paid")
async def admin_paid_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен")
        return
    
    orders = db.get_active_orders()
    
    if not orders:
        await callback.message.edit_text(
            "✅ Нет оплаченных заказов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
            ])
        )
        return
    
    text = "💳 **Оплаченные заказы:**\n\n"
    
    for order in orders[:10]:
        order_id, user_id, order_type, recipient, details, amount_rub, payment_method, order_date = order
        
        emoji = "⭐️" if order_type == "stars" else "👑" if order_type == "premium" else "💱"
        text += f"{emoji} #{order_id}\n"
        text += f"👤 User ID: {user_id}\n"
        text += f"💰 {amount_rub:.2f} RUB\n"
        text += f"👤 Получатель: {recipient}\n"
        text += f"✅ Статус: Оплачено\n"
        text += f"📅 {order_date}\n"
        text += f"🔗 /complete_{order_id}\n"
        text += "─" * 20 + "\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_paid")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_completed")
async def admin_completed_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен")
        return
    
    orders = db.get_completed_orders()
    
    if not orders:
        await callback.message.edit_text(
            "📭 Нет выполненных заказов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
            ])
        )
        return
    
    text = "✅ **Выполненные заказы (последние 50):**\n\n"
    
    for order in orders[:20]:
        order_id, user_id, order_type, recipient, details, amount_rub, payment_method, order_date, completed_date = order
        
        emoji = "⭐️" if order_type == "stars" else "👑" if order_type == "premium" else "💱"
        text += f"{emoji} #{order_id}\n"
        text += f"👤 User ID: {user_id}\n"
        text += f"💰 {amount_rub:.2f} RUB\n"
        text += f"✅ Выполнено: {completed_date}\n"
        text += "─" * 15 + "\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_completed")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_settings")
async def admin_settings_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен")
        return
    
    await callback.message.edit_text(
        f"⚙️ **Настройки**\n\n"
        f"📊 Текущие настройки:\n"
        f"• Карта: {CARD_NUMBER}\n"
        f"• Звезда: {STAR_RATE} RUB\n"
        f"• USD: {USD_RATE} RUB\n"
        f"• Премиум 3м: {PREMIUM_PRICES['3months']['rub']} RUB\n"
        f"• Премиум 6м: {PREMIUM_PRICES['6months']['rub']} RUB\n"
        f"• Премиум 1г: {PREMIUM_PRICES['1year']['rub']} RUB\n\n"
        f"Для изменения нужно редактировать код бота.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_back")
async def admin_back_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен")
        return
    
    stats = db.get_statistics()
    
    await callback.message.edit_text(
        f"🛠️ **Админ панель**\n\n"
        f"📊 Статистика:\n"
        f"👥 Пользователей: {stats['total_users']}\n"
        f"✅ Выполнено: {stats['completed_orders']}\n"
        f"💰 Выручка: {stats['total_revenue']:.2f} RUB\n\n"
        f"⏳ Ожидают: {stats['pending_orders']}\n"
        f"💳 Оплачено: {stats['paid_orders']}\n\n"
        "Выберите раздел:",
        reply_markup=admin_menu_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()

# ========== КОМАНДЫ АДМИНА ==========
@dp.message(F.text.startswith("/check_"))
async def check_order_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return
    
    try:
        order_id = int(message.text.split("_")[1])
        order_info = db.get_order_info(order_id)
        
        if not order_info:
            await message.answer(f"❌ Заказ #{order_id} не найден")
            return
        
        user_id, order_type, recipient, details, amount_rub, payment_method, status = order_info
        
        text = (
            f"🔍 **Заказ #{order_id}**\n\n"
            f"👤 User ID: {user_id}\n"
            f"📦 Тип: {order_type}\n"
            f"👤 Получатель: {recipient}\n"
            f"💰 Сумма: {amount_rub:.2f} RUB\n"
            f"💳 Метод: {payment_method}\n"
            f"📊 Статус: {status}\n\n"
            "**Действия:**\n"
            f"✅ Подтвердить: /confirm_{order_id}\n"
            f"❌ Отменить: /cancel_{order_id}"
        )
        
        await message.answer(text, parse_mode="Markdown")
    
    except (ValueError, IndexError):
        await message.answer("❌ Формат: /check_123")

@dp.message(F.text.startswith("/confirm_"))
async def confirm_order_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return
    
    try:
        order_id = int(message.text.split("_")[1])
        
        success = db.update_order_status(order_id, "paid")
        
        if success:
            order_info = db.get_order_info(order_id)
            if order_info:
                user_id = order_info[0]
                
                try:
                    await bot.send_message(
                        user_id,
                        f"✅ **Заказ #{order_id} оплачен!**\n\n"
                        "Админ подтвердил получение оплаты.\n"
                        "Ваш товар будет доставлен в течение 15 минут."
                    )
                except:
                    pass
            
            await message.answer(f"✅ Заказ #{order_id} подтвержден")
        else:
            await message.answer(f"❌ Заказ #{order_id} не найден")
    
    except (ValueError, IndexError):
        await message.answer("❌ Формат: /confirm_123")

@dp.message(F.text.startswith("/complete_"))
async def complete_order_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return
    
    try:
        order_id = int(message.text.split("_")[1])
        
        success = db.update_order_status(order_id, "completed")
        
        if success:
            order_info = db.get_order_info(order_id)
            if order_info:
                user_id = order_info[0]
                
                try:
                    await bot.send_message(
                        user_id,
                        f"🎉 **Заказ #{order_id} выполнен!**\n\n"
                        "Товар успешно доставлен.\n"
                        "Спасибо за покупку! 🛍️"
                    )
                except:
                    pass
            
            await message.answer(f"✅ Заказ #{order_id} выполнен")
        else:
            await message.answer(f"❌ Заказ #{order_id} не найден")
    
    except (ValueError, IndexError):
        await message.answer("❌ Формат: /complete_123")

@dp.message(F.text.startswith("/cancel_"))
async def cancel_order_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Доступ запрещен")
        return
    
    try:
        order_id = int(message.text.split("_")[1])
        
        success = db.update_order_status(order_id, "cancelled")
        
        if success:
            order_info = db.get_order_info(order_id)
            if order_info:
                user_id = order_info[0]
                
                try:
                    await bot.send_message(
                        user_id,
                        f"❌ **Заказ #{order_id} отменен**\n\n"
                        "Админ отменил ваш заказ.\n"
                        "Если вы уже оплатили, свяжитесь с поддержкой."
                    )
                except:
                    pass
            
            await message.answer(f"✅ Заказ #{order_id} отменен")
        else:
            await message.answer(f"❌ Заказ #{order_id} не найден")
    
    except (ValueError, IndexError):
        await message.answer("❌ Формат: /cancel_123")

# ========== ЗАПУСК БОТА ==========
async def main():
    print("=" * 50)
    print("🚀 Digi Store Bot запускается...")
    print("=" * 50)
    
    if not BOT_TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не найден!")
        print("Добавьте BOT_TOKEN в переменные окружения")
        return
    
    print(f"🤖 Бот: {'✅ Настроен' if BOT_TOKEN else '❌ Нет токена'}")
    print(f"👑 Админы: {len(ADMIN_IDS)} пользователей")
    print(f"💳 Карта: {CARD_NUMBER}")
    print(f"⭐️ Курс звезд: 1 звезда = {STAR_RATE} RUB")
    print(f"💱 Курс обмена: 1 USD = {USD_RATE} RUB")
    print(f"🖼️ Фото: ✅ Встроено в код")
    print("=" * 50)
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())