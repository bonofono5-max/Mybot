#!/usr/bin/env python3
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_TELEGRAM_ID', '0'))
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'telegram_bot')
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]
EXCHANGE_RATE = 120

(SYRIATEL_AMOUNT, SYRIATEL_CODE, SHAM_AMOUNT, SHAM_PROOF, CWALLET_AMOUNT, CWALLET_PROOF,
 COINEX_AMOUNT, COINEX_PROOF, BROADCAST_MESSAGE, ADD_PRODUCT_NAME, ADD_ACCOUNT_CATEGORY,
 ADD_ACCOUNT_DATA, ADD_ACCOUNT_PRICE, MANUAL_BALANCE_USER_ID, MANUAL_BALANCE_AMOUNT,
 BUY_QUANTITY, EDIT_EXCHANGE_RATE, EDIT_PRODUCT_PRICE_SELECT, EDIT_PRODUCT_PRICE_VALUE) = range(19)

DEFAULT_PRODUCTS = [
    {"name": "iCloud Accounts", "category": "icloud", "emoji": "☁️"},
    {"name": "Gmail Accounts", "category": "gmail", "emoji": "📧"},
    {"name": "Outlook Accounts", "category": "outlook", "emoji": "📬"},
    {"name": "PayPal Accounts", "category": "paypal", "emoji": "💳"},
    {"name": "SSN Cards", "category": "ssn", "emoji": "🪪"},
    {"name": "Visa Cards", "category": "visa", "emoji": "💳"},
    {"name": "Social Media Accounts", "category": "social", "emoji": "📱"},
    {"name": "Telegram Bot Development", "category": "telegram_dev", "emoji": "🤖"},
    {"name": "App & Web Development", "category": "web_dev", "emoji": "🌐"},
]

async def get_exchange_rate():
    settings = await db.settings.find_one({"key": "exchange_rate"}, {"_id": 0})
    return settings.get("value", EXCHANGE_RATE) if settings else EXCHANGE_RATE

async def set_exchange_rate(rate):
    await db.settings.update_one({"key": "exchange_rate"}, {"$set": {"key": "exchange_rate", "value": rate}}, upsert=True)

async def ensure_user_exists(user_id, username=None, first_name=None):
    if not await db.users.find_one({"user_id": user_id}):
        await db.users.insert_one({"user_id": user_id, "username": username, "first_name": first_name, "balance": 0, "created_at": datetime.now(timezone.utc).isoformat()})
    return await db.users.find_one({"user_id": user_id}, {"_id": 0})

async def get_user_balance(user_id):
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return user.get("balance", 0) if user else 0

async def update_user_balance(user_id, amount):
    await db.users.update_one({"user_id": user_id}, {"$inc": {"balance": amount}})

async def init_default_products():
    for product in DEFAULT_PRODUCTS:
        if not await db.products.find_one({"category": product["category"]}):
            await db.products.insert_one({"name": product["name"], "category": product["category"], "emoji": product["emoji"], "created_at": datetime.now(timezone.utc).isoformat()})

def get_main_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("Recharge Balance", callback_data="recharge")],
        [InlineKeyboardButton("My Balance", callback_data="my_balance")],
        [InlineKeyboardButton("Products", callback_data="products")],
        [InlineKeyboardButton("Support", callback_data="support")],
        [InlineKeyboardButton("Prices", callback_data="prices")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

async def start(update, context):
    user = update.effective_user
    await ensure_user_exists(user.id, user.username, 
