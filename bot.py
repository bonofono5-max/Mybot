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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_TELEGRAM_ID', '0'))

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'telegram_bot')
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

EXCHANGE_RATE = 120

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
    if settings:
        return settings.get("value", EXCHANGE_RATE)
    return EXCHANGE_RATE


async def set_exchange_rate(rate: int):
    await db.settings.update_one(
        {"key": "exchange_rate"},
        {"$set": {"key": "exchange_rate", "value": rate}},
        upsert=True
    )


async def ensure_user_exists(user_id: int, username: str = None, first_name: str = None):
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
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return user.get("balance", 0) if user else 0


async def update_user_balance(user_id: int, amount: int):
    await db.users.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": amount}}
    )


async def init_default_products():
    for product in DEFAULT_PRODUCTS:
        existing = await db.products.find_one({"category": product["category"]})
        if not existing:
            await db.products.insert_one({
                "name": product["name"],
                "category": product["category"],
                "emoji": product["emoji"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })


def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_exists(user.id, user.username, user.first_name)
    welcome_text = "Welcome " + str(user.first_name) + "!\n\nChoose from the menu below:"
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(user.id))


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    await query.edit_message_text(text="Choose from the menu below:", reply_markup=get_main_menu_keyboard(user.id))


async def recharge_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Syriatel Cash", callback_data="recharge_syriatel")],
        [InlineKeyboardButton("Sham Cash", callback_data="recharge_sham")],
        [InlineKeyboardButton("CWallet", callback_data="recharge_cwallet")],
        [InlineKeyboardButton("CoinEx", callback_data="recharge_coinex")],
        [InlineKeyboardButton("Back", callback_data="main_menu")],
    ]
    await query.edit_message_text("Choose payment method:", reply_markup=InlineKeyboardMarkup(keyboard))


async def syriatel_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "Syriatel Cash Transfer\n\n"
        "Numbers:\n"
        "0934595626\n"
        "0935579034\n\n"
        "Steps:\n"
        "1. Transfer the amount\n"
        "2. Press Confirm below\n"
        "3. Keep the transfer code"
    )
    keyboard = [[
        InlineKeyboardButton("Confirm", callback_data="syriatel_confirm"),
        InlineKeyboardButton("Cancel", callback_data="recharge"),
    ]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def syriatel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Enter the amount you transferred (in SYP, numbers only):")
    return SYRIATEL_AMOUNT


async def syriatel_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        context.user_data['syriatel_amount'] = amount
        await update.message.reply_text("Enter the transfer code:")
        return SYRIATEL_CODE
    except ValueError:
        await update.message.reply_text("Please enter a valid number!")
        return SYRIATEL_AMOUNT


async def syriatel_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text
    amount = context.user_data.get('syriatel_amount', 0)
    user = update.effective_user
    request_doc = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "method": "syriatel",
        "amount": amount,
        "code": code,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.recharge_requests.insert_one(request_doc)
    request_id = str(result.inserted_id)
    admin_text = (
        "New Recharge Request (Syriatel)\n\n"
        "User: " + str(user.first_name) + "\n"
        "Username: @" + str(user.username or 'N/A') + "\n"
        "ID: " + str(user.id) + "\n"
        "Amount: " + str(amount) + " SYP\n"
        "Code: " + str(code)
    )
    keyboard = [[
        InlineKeyboardButton("Approve", callback_data="approve_recharge_" + request_id),
        InlineKeyboardButton("Reject", callback_data="reject_recharge_" + request_id),
    ]]
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("Request sent! Waiting for admin approval.", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END


async def sham_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Enter the amount to recharge (in SYP):")
    return SHAM_AMOUNT


async def sham_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        context.user_data['sham_amount'] = amount
        text = "Sham Cash ID:\nbc9d9b41336308e2a4f9e0ffe86f48a0\n\nPlease send a screenshot as proof."
        await update.message.reply_text(text)
        return SHAM_PROOF
    except ValueError:
        await update.message.reply_text("Please enter a valid number!")
        return SHAM_AMOUNT


async def sham_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Please send a photo!")
        return SHAM_PROOF
    photo = update.message.photo[-1]
    amount = context.user_data.get('sham_amount', 0)
    user = update.effective_user
    request_doc = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "method": "sham_cash",
        "amount": amount,
        "photo_file_id": photo.file_id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.recharge_requests.insert_one(request_doc)
    request_id = str(result.inserted_id)
    admin_text = (
        "New Recharge Request (Sham Cash)\n\n"
        "User: " + str(user.first_name) + "\n"
        "Username: @" + str(user.username or 'N/A') + "\n"
        "ID: " + str(user.id) + "\n"
        "Amount: " + str(amount) + " SYP"
    )
    keyboard = [[
        InlineKeyboardButton("Approve", callback_data="approve_recharge_" + request_id),
        InlineKeyboardButton("Reject", callback_data="reject_recharge_" + request_id),
    ]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo.file_id, caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("Request sent! Waiting for admin approval.", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END


async def cwallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    exchange_rate = await get_exchange_rate()
    await query.edit_message_text("Enter the amount to recharge (in SYP):\n\n1 USD = " + str(exchange_rate) + " SYP")
    return CWALLET_AMOUNT


async def cwallet_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        context.user_data['cwallet_amount'] = amount
        exchange_rate = await get_exchange_rate()
        usd_amount = amount / exchange_rate
        text = (
            "CWallet Address:\nTHEaoFQmETNbxiouYCBhKkaYZT4Zoo8GwJ\n\n"
            "Amount in USD: $" + "{:.2f}".format(usd_amount) + "\n"
            "1 USD = " + str(exchange_rate) + " SYP\n\n"
            "Please send a screenshot as proof."
        )
        await update.message.reply_text(text)
        return CWALLET_PROOF
    except ValueError:
        await update.message.reply_text("Please enter a valid number!")
        return CWALLET_AMOUNT


async def cwallet_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Please send a photo!")
        return CWALLET_PROOF
    photo = update.message.photo[-1]
    amount = context.user_data.get('cwallet_amount', 0)
    user = update.effective_user
    exchange_rate = await get_exchange_rate()
    request_doc = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "method": "cwallet",
        "amount": amount,
        "photo_file_id": photo.file_id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.recharge_requests.insert_one(request_doc)
    request_id = str(result.inserted_id)
    usd_amount = amount / exchange_rate
    admin_text = (
        "New Recharge Request (CWallet)\n\n"
        "User: " + str(user.first_name) + "\n"
        "Username: @" + str(user.username or 'N/A') + "\n"
        "ID: " + str(user.id) + "\n"
        "Amount: " + str(amount) + " SYP ($" + "{:.2f}".format(usd_amount) + ")"
    )
    keyboard = [[
        InlineKeyboardButton("Approve", callback_data="approve_recharge_" + request_id),
        InlineKeyboardButton("Reject", callback_data="reject_recharge_" + request_id),
    ]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo.file_id, caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("Request sent! Waiting for admin approval.", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END


async def coinex_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    exchange_rate = await get_exchange_rate()
    await query.edit_message_text("Enter the amount to recharge (in SYP):\n\n1 USD = " + str(exchange_rate) + " SYP")
    return COINEX_AMOUNT


async def coinex_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        context.user_data['coinex_amount'] = amount
        exchange_rate = await get_exchange_rate()
        usd_amount = amount / exchange_rate
        text = (
            "CoinEx Address:\n0xaace6d4956b27c293018556bedba49a5074d6020\n\n"
            "Amount in USD: $" + "{:.2f}".format(usd_amount) + "\n"
            "1 USD = " + str(exchange_rate) + " SYP\n\n"
            "Please send a screenshot as proof."
        )
        await update.message.reply_text(text)
        return COINEX_PROOF
    except ValueError:
        await update.message.reply_text("Please enter a valid number!")
        return COINEX_AMOUNT


async def coinex_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Please send a photo!")
        return COINEX_PROOF
    photo = update.message.photo[-1]
    amount = context.user_data.get('coinex_amount', 0)
    user = update.effective_user
    exchange_rate = await get_exchange_rate()
    request_doc = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "method": "coinex",
        "amount": amount,
        "photo_file_id": photo.file_id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.recharge_requests.insert_one(request_doc)
    request_id = str(result.inserted_id)
    usd_amount = amount / exchange_rate
    admin_text = (
        "New Recharge Request (CoinEx)\n\n"
        "User: " + str(user.first_name) + "\n"
        "Username: @" + str(user.username or 'N/A') + "\n"
        "ID: " + str(user.id) + "\n"
        "Amount: " + str(amount) + " SYP ($" + "{:.2f}".format(usd_amount) + ")"
    )
    keyboard = [[
        InlineKeyboardButton("Approve", callback_data="approve_recharge_" + request_id),
        InlineKeyboardButton("Reject", callback_data="reject_recharge_" + request_id),
    ]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo.file_id, caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("Request sent! Waiting for admin approval.", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END


async def approve_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    request_id = query.data.replace("approve_recharge_", "")
    from bson import ObjectId
    request = await db.recharge_requests.find_one({"_id": ObjectId(request_id)})
    if request and request.get("status") == "pending":
        await db.recharge_requests.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"status": "approved", "approved_at": datetime.now(timezone.utc).isoformat()}}
        )
        await update_user_balance(request["user_id"], request["amount"])
        user_balance = await get_user_balance(request["user_id"])
        await context.bot.send_message(
            chat_id=request["user_id"],
            text="Recharge approved!\n\nAmount added: " + str(request['amount']) + " SYP\nNew balance: " + str(user_balance) + " SYP"
        )
        try:
            await query.edit_message_caption(caption=str(query.message.caption or '') + "\n\nApproved")
        except Exception:
            await query.edit_message_text(text=str(query.message.text or '') + "\n\nApproved")
    else:
        await query.answer("Request not found or already processed")


async def reject_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    request_id = query.data.replace("reject_recharge_", "")
    from bson import ObjectId
    request = await db.recharge_requests.find_one({"_id": ObjectId(request_id)})
    if request and request.get("status") == "pending":
        await db.recharge_requests.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"status": "rejected", "rejected_at": datetime.now(timezone.utc).isoformat()}}
        )
        await context.bot.send_message(
            chat_id=request["user_id"],
            text="Recharge request rejected. Please contact support if you believe this is an error."
        )
        try:
            await query.edit_message_caption(caption=str(query.message.caption or '') + "\n\nRejected")
        except Exception:
            await query.edit_message_text(text=str(query.message.text or '') + "\n\nRejected")
    else:
        await query.answer("Request not found or already processed")


async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    balance = await get_user_balance(user.id)
    text = (
        "Your Balance\n\n"
        "Telegram ID: " + str(user.id) + "\n"
        "Name: " + str(user.first_name) + "\n"
        "Username: @" + str(user.username or 'N/A') + "\n\n"
        "Balance: " + str(balance) + " SYP"
    )
    keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = await db.products.find({}, {"_id": 0}).to_list(100)
    keyboard = []
    for product in products:
        keyboard.append([InlineKeyboardButton(
            product.get('emoji', '') + " " + product['name'],
            callback_data="product_" + product['category']
        )])
    keyboard.append([InlineKeyboardButton("Back", callback_data="main_menu")])
    await query.edit_message_text("Choose a product:", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_product_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("product_", "")
    context.user_data['selected_category'] = category
    product = await db.products.find_one({"category": category}, {"_id": 0})
    accounts = await db.accounts.find({"category": category, "sold": False}, {"_id": 0}).to_list(100)
    if not accounts:
        keyboard = [[InlineKeyboardButton("Back", callback_data="products")]]
        await query.edit_message_text("No accounts available for " + product['name'], reply_markup=InlineKeyboardMarkup(keyboard))
        return
    prices = {}
    for acc in accounts:
        price = acc.get('price', 0)
        prices[price] = prices.get(price, 0) + 1
    text = product.get('emoji', '') + " " + product['name'] + "\n\nAvailable accounts:\n"
    for price, count in prices.items():
        text += str(count) + " accounts at " + str(price) + " SYP\n"
    keyboard = [
        [InlineKeyboardButton("Buy", callback_data="buy_" + category)],
        [InlineKeyboardButton("Back", callback_data="products")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def start_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("buy_", "")
    context.user_data['buy_category'] = category
    accounts = await db.accounts.find({"category": category, "sold": False}, {"_id": 0}).to_list(100)
    if not accounts:
        await query.answer("No accounts available!")
        return ConversationHandler.END
    context.user_data['available_count'] = len(accounts)
    context.user_data['account_price'] = accounts[0].get('price', 0)
    await query.edit_message_text(
        "How many accounts do you want to buy?\n\n"
        "Available: " + str(len(accounts)) + "\n"
        "Price: " + str(accounts[0].get('price', 0)) + " SYP each"
    )
    return BUY_QUANTITY


async def process_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        quantity = int(update.message.text)
        available = context.user_data.get('available_count', 0)
        price = context.user_data.get('account_price', 0)
        category = context.user_data.get('buy_category')
        user = update.effective_user
        if quantity <= 0:
            await update.message.reply_text("Please enter a number greater than 0!")
            return BUY_QUANTITY
        if quantity > available:
            await update.message.reply_text("Requested quantity (" + str(quantity) + ") exceeds available (" + str(available) + ")!")
            return BUY_QUANTITY
        total_price = quantity * price
        user_balance = await get_user_balance(user.id)
        if user_balance < total_price:
            await update.message.reply_text(
                "Insufficient balance!\n\nYour balance: " + str(user_balance) + " SYP\nRequired: " + str(total_price) + " SYP",
                reply_markup=get_main_menu_keyboard(user.id)
            )
            return ConversationHandler.END
        from bson import ObjectId
        accounts = await db.accounts.find({"category": category, "sold": False}).limit(quantity).to_list(quantity)
        if len(accounts) < quantity:
            await update.message.reply_text("An error occurred, please try again later.")
            return ConversationHandler.END
        account_ids = [acc['_id'] for acc in accounts]
        await db.accounts.update_many(
            {"_id": {"$in": account_ids}},
            {"$set": {"sold": True, "sold_to": user.id, "sold_at": datetime.now(timezone.utc).isoformat()}}
        )
        await update_user_balance(user.id, -total_price)
        text = "Purchase successful!\n\nAccounts (" + str(quantity) + "):\n\n"
        for i, acc in enumerate(accounts, 1):
            text += str(i) + ". " + str(acc.get('data', 'N/A')) + "\n"
        text += "\nTotal paid: " + str(total_price) + " SYP"
        await db.purchases.insert_one({
            "user_id": user.id,
            "category": category,
            "quantity": quantity,
            "total_price": total_price,
            "account_ids": [str(aid) for aid in account_ids],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await update.message.reply_text(text, reply_markup=get_main_menu_keyboard(user.id))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Please enter a valid number!")
        return BUY_QUANTITY


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "Support\n\nContact admin:\n@km0997055"
    keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    exchange_rate = await get_exchange_rate()
    products = await db.products.find({}, {"_id": 0}).to_list(100)
    text = "Prices\n\nExchange Rate:\n1 USD = " + str(exchange_rate) + " SYP\n\nProducts:\n"
    for product in products:
        accounts = await db.accounts.find({"category": product['category'], "sold": False}, {"_id": 0}).to_list(1)
        if accounts:
            text += "\n" + product.get('emoji', '') + " " + product['name'] + ": " + str(accounts[0].get('price', 'N/A')) + " SYP"
        else:
            text += "\n" + product.get('emoji', '') + " " + product['name'] + ": Not available"
    keyboard = []
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("Edit Exchange Rate", callback_data="edit_exchange_rate")])
        keyboard.append([InlineKeyboardButton("Edit Product Prices", callback_data="edit_product_prices")])
    keyboard.append([InlineKeyboardButton("Back", callback_data="main_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def edit_exchange_rate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    current_rate = await get_exchange_rate()
    await query.edit_message_text("Current rate: 1 USD = " + str(current_rate) + " SYP\n\nEnter new exchange rate:")
    return EDIT_EXCHANGE_RATE


async def edit_exchange_rate_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_rate = int(update.message.text)
        if new_rate <= 0:
            await update.message.reply_text("Please enter a number greater than 0!")
            return EDIT_EXCHANGE_RATE
        await set_exchange_rate(new_rate)
        await update.message.reply_text("Exchange rate updated!\n\nNew rate: 1 USD = " + str(new_rate) + " SYP", reply_markup=get_main_menu_keyboard(ADMIN_ID))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Please enter a valid number!")
        return EDIT_EXCHANGE_RATE


async def edit_product_prices_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    products = await db.products.find({}, {"_id": 0}).to_list(100)
    keyboard = []
    for product in products:
        keyboard.append([InlineKeyboardButton(
            product.get('emoji', '') + " " + product['name'],
            callback_data="edit_price_" + product['category']
        )])
    keyboard.append([InlineKeyboardButton("Back", callback_data="prices")])
    await query.edit_message_text("Choose product to edit price:", reply_markup=InlineKeyboardMarkup(keyboard))


async def edit_product_price_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    category = query.data.replace("edit_price_", "")
    context.user_data['edit_price_category'] = category
    product = await db.products.find_one({"category": category}, {"_id": 0})
    accounts = await db.accounts.find({"category": category, "sold": False}, {"_id": 0}).to_list(1)
    current_price = accounts[0].get('price', 'N/A') if accounts else 'N/A'
    await query.edit_message_text(
        product['name'] + "\nCurrent price: " + str(current_price) + " SYP\n\nEnter new price:"
    )
    return EDIT_PRODUCT_PRICE_VALUE


async def edit_product_price_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_price = int(update.message.text)
        if new_price <= 0:
            await update.message.reply_text("Please enter a number greater than 0!")
            return EDIT_PRODUCT_PRICE_VALUE
        category = context.user_data.get('edit_price_category')
        result = await db.accounts.update_many({"category": category, "sold": False}, {"$set": {"price": new_price}})
        product = await db.products.find_one({"category": category}, {"_id": 0})
        await update.message.reply_text(
            "Price updated!\n\n" + product['name'] + "\nNew price: " + str(new_price) + " SYP\nUpdated: " + str(result.modified_count) + " accounts",
            reply_markup=get_main_menu_keyboard(ADMIN_ID)
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Please enter a valid number!")
        return EDIT_PRODUCT_PRICE_VALUE


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    keyboard = [
        [InlineKeyboardButton("Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("Add Accounts", callback_data="admin_add_accounts")],
        [InlineKeyboardButton("Add Product", callback_data="admin_add_product")],
        [InlineKeyboardButton("Add Balance Manually", callback_data="admin_manual_balance")],
        [InlineKeyboardButton("Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("Back", callback_data="main_menu")],
    ]
    await query.edit_message_text("Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    await query.edit_message_text("Write the message to send to all users:")
    return BROADCAST_MESSAGE


async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    users = await db.users.find({}, {"_id": 0, "user_id": 1}).to_list(10000)
    sent = 0
    failed = 0
    for user in users:
        try:
            await context.bot.send_message(chat_id=user['user_id'], text=message)
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text("Message sent!\n\nSuccess: " + str(sent) + "\nFailed: " + str(failed), reply_markup=get_main_menu_keyboard(ADMIN_ID))
    return ConversationHandler.END


async def admin_add_accounts_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    products = await db.products.find({}, {"_id": 0}).to_list(100)
    keyboard = []
    for product in products:
        keyboard.append([InlineKeyboardButton(
            product.get('emoji', '') + " " + product['name'],
            callback_data="admin_acc_cat_" + product['category']
        )])
    keyboard.append([InlineKeyboardButton("Back", callback_data="admin_panel")])
    await query.edit_message_text("Choose category to add account:", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    category = query.data.replace("admin_acc_cat_", "")
    context.user_data['admin_acc_category'] = category
    await query.edit_message_text("Enter account data:")
    return ADD_ACCOUNT_DATA


async def admin_receive_account_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['admin_acc_data'] = update.message.text
    await update.message.reply_text("Enter account price (in SYP):")
    return ADD_ACCOUNT_PRICE


async def admin_receive_account_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
        category = context.user_data.get('admin_acc_category')
        data = context.user_data.get('admin_acc_data')
        await db.accounts.insert_one({
            "category": category,
            "data": data,
            "price": price,
            "sold": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await update.message.reply_text("Account added!\n\nCategory: " + str(category) + "\nPrice: " + str(price) + " SYP", reply_markup=get_main_menu_keyboard(ADMIN_ID))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Please enter a valid number!")
        return ADD_ACCOUNT_PRICE


async def admin_add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    await query.edit_message_text("Enter the new product name:")
    return ADD_PRODUCT_NAME


async def admin_receive_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    category = name.lower().replace(" ", "_")
    await db.products.insert_one({
        "name": name,
        "category": category,
        "emoji": "📦",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await update.message.reply_text("Product added!\n\nName: " + str(name), reply_markup=get_main_menu_keyboard(ADMIN_ID))
    return ConversationHandler.END


async def admin_manual_balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    await query.edit_message_text("Enter user Telegram ID:")
    return MANUAL_BALANCE_USER_ID


async def admin_receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        context.user_data['manual_balance_user_id'] = user_id
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not user:
            await update.message.reply_text("User not found!", reply_markup=get_main_menu_keyboard(ADMIN_ID))
            return ConversationHandler.END
        await update.message.reply_text(
            "User: " + str(user.get('first_name', 'N/A')) + "\nCurrent balance: " + str(user.get('balance', 0)) + " SYP\n\nEnter amount to add:"
        )
        return MANUAL_BALANCE_AMOUNT
    except ValueError:
        await update.message.reply_text("Please enter a valid number!")
        return MANUAL_BALANCE_USER_ID


async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        user_id = context.user_data.get('manual_balance_user_id')
        await update_user_balance(user_id, amount)
        new_balance = await get_user_balance(user_id)
        await context.bot.send_message(chat_id=user_id, text="Balance added to your account!\n\nAdded: " + str(amount) + " SYP\nNew balance: " + str(new_balance) + " SYP")
        await update.message.reply_text("Balance added!\n\nAmount: " + str(amount) + " SYP\nNew balance: " + str(new_balance) + " SYP", reply_markup=get_main_menu_keyboard(ADMIN_ID))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Please enter a valid number!")
        return MANUAL_BALANCE_AMOUNT


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    users_count = await db.users.count_documents({})
    accounts_count = await db.accounts.count_documents({"sold": False})
    sold_count = await db.accounts.count_documents({"sold": True})
    pending_recharges = await db.recharge_requests.count_documents({"status": "pending"})
    text = (
        "Bot Statistics\n\n"
        "Users: " + str(users_count) + "\n"
        "Available accounts: " + str(accounts_count) + "\n"
        "Sold accounts: " + str(sold_count) + "\n"
        "Pending recharges: " + str(pending_recharges)
    )
    keyboard = [[InlineKeyboardButton("Back", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text("Cancelled", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END


def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        return
    if not ADMIN_ID:
        logger.error("ADMIN_TELEGRAM_ID not found!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    async def post_init(application):
        await init_default_products()

    application.post_init = post_init

    syriatel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(syriatel_confirm, pattern="^syriatel_confirm$")],
        states={
            SYRIATEL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, syriatel_amount_received)],
            SYRIATEL_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, syriatel_code_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    sham_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(sham_start, pattern="^recharge_sham$")],
        states={
            SHAM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sham_amount_received)],
            SHAM_PROOF: [MessageHandler(filters.PHOTO, sham_proof_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    cwallet_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cwallet_start, pattern="^recharge_cwallet$")],
        states={
            CWALLET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cwallet_amount_received)],
            CWALLET_PROOF: [MessageHandler(filters.PHOTO, cwallet_proof_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    coinex_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(coinex_start, pattern="^recharge_coinex$")],
        states={
            COINEX_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, coinex_amount_received)],
            COINEX_PROOF: [MessageHandler(filters.PHOTO, coinex_proof_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_buy, pattern="^buy_")],
        states={
            BUY_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_buy)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    add_accounts_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_select_category, pattern="^admin_acc_cat_")],
        states={
            ADD_ACCOUNT_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_account_data)],
            ADD_ACCOUNT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_account_price)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    add_product_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_product_start, pattern="^admin_add_product$")],
        states={
            ADD_PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_product_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    manual_balance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_manual_balance_start, pattern="^admin_manual_balance$")],
        states={
            MANUAL_BALANCE_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_user_id)],
            MANUAL_BALANCE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_balance)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    edit_exchange_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_exchange_rate_start, pattern="^edit_exchange_rate$")],
        states={
            EDIT_EXCHANGE_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_exchange_rate_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    edit_price_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_product_price_select, pattern="^edit_price_")],
        states={
            EDIT_PRODUCT_PRICE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_product_price_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(syriatel_conv)
    application.add_handler(sham_conv)
    application.add_handler(cwallet_conv)
    application.add_handler(coinex_conv)
    application.add_handler(buy_conv)
    application.add_handler(broadcast_conv)
    application.add_handler(add_accounts_conv)
    application.add_handler(add_product_conv)
    application.add_handler(manual_balance_conv)
    application.add_handler(edit_exchange_conv)
    application.add_handler(edit_price_conv)
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(recharge_menu, pattern="^recharge$"))
    application.add_handler(CallbackQueryHandler(syriatel_info, pattern="^recharge_syriatel$"))
    application.add_handler(CallbackQueryHandler(show_balance, pattern="^my_balance$"))
    application.add_handler(CallbackQueryHandler(show_products, pattern="^products$"))
    application.add_handler(CallbackQueryHandler(show_product_accounts, pattern="^product_"))
    application.add_handler(CallbackQueryHandler(show_support, pattern="^support$"))
    application.add_handler(CallbackQueryHandler(show_prices, pattern="^prices$"))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(admin_add_accounts_start, pattern="^admin_add_accounts$"))
    application.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(approve_recharge, pattern="^approve_recharge_"))
    application.add_handler(CallbackQueryHandler(reject_recharge, pattern="^reject_recharge_"))
    application.add_handler(CallbackQueryHandler(edit_product_prices_start, pattern="^edit_product_prices$"))

    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
