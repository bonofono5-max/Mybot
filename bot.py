#!/usr/bin/env python3
"""
Telegram Bot for Payment Gateway and Product Management
"""

import os
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Token and Admin ID
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_TELEGRAM_ID', '0'))

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'telegram_bot')
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# Exchange rate
EXCHANGE_RATE = 120  # 1 USD = 120 SYP


async def get_exchange_rate():
    """Get exchange rate from database or default"""
    settings = await db.settings.find_one({"key": "exchange_rate"}, {"_id": 0})
    if settings:
        return settings.get("value", EXCHANGE_RATE)
    return EXCHANGE_RATE


async def set_exchange_rate(rate: int):
    """Set exchange rate in database"""
    await db.settings.update_one(
        {"key": "exchange_rate"},
        {"$set": {"key": "exchange_rate", "value": rate}},
        upsert=True
    )

# Conversation states
(
    SYRIATEL_AMOUNT,
    SYRIATEL_CODE,
    SHAM_AMOUNT,
    SHAM_PROOF,
    CWALLET_AMOUNT,
    CWALLET_PROOF,
    COINEX_AMOUNT,
    COINEX_PROOF,
    BROADCAST_MESSAGE,
    ADD_PRODUCT_NAME,
    ADD_ACCOUNT_CATEGORY,
    ADD_ACCOUNT_DATA,
    ADD_ACCOUNT_PRICE,
    MANUAL_BALANCE_USER_ID,
    MANUAL_BALANCE_AMOUNT,
    BUY_QUANTITY,
    EDIT_EXCHANGE_RATE,
    EDIT_PRODUCT_PRICE_SELECT,
    EDIT_PRODUCT_PRICE_VALUE,
) = range(19)

# Default products
DEFAULT_PRODUCTS = [
    {"name": "حسابات iCloud", "category": "icloud", "emoji": "☁️"},
    {"name": "حسابات Gmail", "category": "gmail", "emoji": "📧"},
    {"name": "حسابات Outlook", "category": "outlook", "emoji": "📬"},
    {"name": "حسابات PayPal", "category": "paypal", "emoji": "💳"},
    {"name": "بطاقات SSN", "category": "ssn", "emoji": "🪪"},
    {"name": "بطاقات Visa", "category": "visa", "emoji": "💳"},
    {"name": "حسابات تواصل اجتماعي", "category": "social", "emoji": "📱"},
    {"name": "تصميم و برمجة بوتات تلجرام", "category": "telegram_dev", "emoji": "🤖"},
    {"name": "تصميم تطبيقات ومواقع ويب", "category": "web_dev", "emoji": "🌐"},
]


async def ensure_user_exists(user_id: int, username: str = None, first_name: str = None):
    """Ensure user exists in database"""
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        await db.users.insert_one({
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "balance": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    return await db.users.find_one({"user_id": user_id}, {"_id": 0})


async def get_user_balance(user_id: int) -> int:
    """Get user balance"""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return user.get("balance", 0) if user else 0


async def update_user_balance(user_id: int, amount: int):
    """Update user balance"""
    await db.users.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": amount}}
    )


async def init_default_products():
    """Initialize default products if not exist"""
    for product in DEFAULT_PRODUCTS:
        existing = await db.products.find_one({"category": product["category"]})
        if not existing:
            await db.products.insert_one({
     
