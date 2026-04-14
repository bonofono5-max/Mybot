```python
#!/usr/bin/env python3
"""
Telegram Bot for Payment Gateway and Product Management
Built from scratch with all fixes applied
"""

import os
import logging
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
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
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===========================================
# CONFIGURATION
# ===========================================

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8605010753:AAGXyDjCwVBOFABTHq47DTqn4AUni_-6Dk0')
ADMIN_ID = int(os.environ.get('ADMIN_TELEGRAM_ID', '8672429812'))
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb+srv://admin:admin123@cluster0.6gautxn.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
DB_NAME = os.environ.get('DB_NAME', 'telegram_bot')

# MongoDB connection
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Default exchange rate
DEFAULT_EXCHANGE_RATE = 120

# ===========================================
# CONVERSATION STATES
# ===========================================

(
    SYRIATEL_AMOUNT, SYRIATEL_CODE,
    SHAM_AMOUNT, SHAM_PROOF,
    CWALLET_AMOUNT, CWALLET_PROOF,
    COINEX_AMOUNT, COINEX_PROOF,
    BROADCAST_MESSAGE,
    ADD_PRODUCT_NAME,
    ADD_ACCOUNT_PRICE, ADD_ACCOUNT_DATA,
    MANUAL_BALANCE_USER_ID, MANUAL_BALANCE_AMOUNT,
    EDIT_EXCHANGE_RATE,
    EDIT_PRODUCT_PRICE_VALUE,
    BUY_QUANTITY,
    SUBSCRIBER_LOOKUP_ID,
) = range(18)

# ===========================================
# DEFAULT PRODUCTS
# ===========================================

DEFAULT_PRODUCTS = [
    {"name": "حسابات iCloud", "category": "icloud", "emoji": "☁️"},
    {"name": "حسابات Gmail", "category": "gmail", "emoji": "📧"},
    {"name": "حسابات Outlook", "category": "outlook", "emoji": "📬"},
    {"name": "حسابات PayPal", "category": "paypal", "emoji": "💳"},
    {"name": "بطاقات SSN", "category": "ssn", "emoji": "🪪"},
    {"name": "بطاقات Visa", "category": "visa", "emoji": "💎"},
    {"name": "حسابات تواصل اجتماعي", "category": "social", "emoji": "📱"},
    {"name": "تصميم و برمجة بوتات تلجرام", "category": "telegram_dev", "emoji": "🤖"},
    {"name": "تصميم تطبيقات ومواقع ويب", "category": "web_dev", "emoji": "🌐"},
]

# ===========================================
# DATABASE HELPERS
# ===========================================

async def get_exchange_rate():
    settings = await db.settings.find_one({"key": "exchange_rate"})
    if settings:
        return settings.get("value", DEFAULT_EXCHANGE_RATE)
    return DEFAULT_EXCHANGE_RATE

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
    user = await db.users.find_one({"user_id": user_id})
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

# ===========================================
# KEYBOARD HELPERS
# ===========================================

def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("➕ شحن الرصيد", callback_data="recharge")],
        [InlineKeyboardButton("💰 رصيدي", callback_data="my_balance")],
        [InlineKeyboardButton("🛒 المنتجات", callback_data="products")],
        [InlineKeyboardButton("📞 تواصل مع الدعم", callback_data="support")],
        [InlineKeyboardButton("💵 أسعار الخدمات والصرف", callback_data="prices")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ إدارة خدمات البوت", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

# ===========================================
# START COMMAND
# ===========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_exists(user.id, user.username, user.first_name)
    welcome_text = f"مرحباً {user.first_name}! 👋\n\nأهلاً بك في بوت الخدمات المتكاملة\n\nاختر من القائمة أدناه:"
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(user.id))

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    await query.edit_message_text(text="اختر من القائمة أدناه:", reply_markup=get_main_menu_keyboard(user.id))

# ===========================================
# RECHARGE MENU
# ===========================================

async def recharge_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📱 سيريتل كاش", callback_data="recharge_syriatel")],
        [InlineKeyboardButton("💵 شام كاش", callback_data="recharge_sham")],
        [InlineKeyboardButton("👛 محفظة CWallet", callback_data="recharge_cwallet")],
        [InlineKeyboardButton("🔸 محفظة CoinEx", callback_data="recharge_coinex")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ]
    await query.edit_message_text("💳 اختر وسيلة الشحن:", reply_markup=InlineKeyboardMarkup(keyboard))

# ===========================================
# SYRIATEL CASH
# ===========================================

async def syriatel_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = """💳 شحن الرصيد عبر سيريتل كاش (تحويل يدوي)

📱 أرقام سيريتل كاش:
0934595626
0935579034

📌 الخطوات:
1️⃣ قم بتحويل المبلغ المراد شحنه إلى أحد الأرقام أعلاه
2️⃣ بعد التحويل اضغط على زر تأكيد التحويل أدناه
⚠️ تأكد من حفظ رقم التحويلة (الكود)"""
    keyboard = [[
        InlineKeyboardButton("✅ تأكيد", callback_data="syriatel_confirm"),
        InlineKeyboardButton("❌ إلغاء", callback_data="recharge"),
    ]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def syriatel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💵 قم بإدخال المبلغ الذي حولته؟ بالليرة السورية (أدخل الرقم فقط)")
    return SYRIATEL_AMOUNT

async def syriatel_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        context.user_data['syriatel_amount'] = amount
        await update.message.reply_text("🔢 أدخل رقم عملية التحويل (الكود):")
        return SYRIATEL_CODE
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح فقط!")
        return SYRIATEL_AMOUNT

async def syriatel_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text
    amount = context.user_data.get('syriatel_amount', 0)
    user = update.effective_user
    
    request_doc = {
        "user_id": user.id, "username": user.username, "first_name": user.first_name,
        "method": "syriatel", "amount": amount, "code": code, "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.recharge_requests.insert_one(request_doc)
    request_id = str(result.inserted_id)

    admin_text = f"📥 طلب شحن رصيد جديد (سيريتل كاش)\n\n👤 المستخدم: {user.first_name}\n🆔 المعرف: @{user.username or 'N/A'}\n🔑 ID: {user.id}\n💰 المبلغ: {amount} ل.س\n🔢 كود التحويل: {code}"
    keyboard = [[
        InlineKeyboardButton("✅ قبول", callback_data=f"approve_recharge_{request_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject_recharge_{request_id}"),
    ]]
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("✅ تم إرسال طلبك بنجاح!\n⏳ يرجى انتظار تأكيد الأدمن.", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END

# ===========================================
# SHAM CASH
# ===========================================

async def sham_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💵 كم المبلغ المراد شحنه؟ (بالليرة السورية)")
    return SHAM_AMOUNT

async def sham_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        context.user_data['sham_amount'] = amount
        text = "💳 اشحن الرصيد عبر شام كاش\nعلى معرف شام كاش حول عليه👇\nbc9d9b41336308e2a4f9e0ffe86f48a0\n\nيرجى إرسال إثبات الدفع (صورة فقط)\nسيتم مراجعة الطلب من الأدمن قريباً"
        await update.message.reply_text(text)
        return SHAM_PROOF
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح فقط!")
        return SHAM_AMOUNT

async def sham_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ يرجى إرسال صورة فقط!")
        return SHAM_PROOF
    
    photo = update.message.photo[-1]
    amount = context.user_data.get('sham_amount', 0)
    user = update.effective_user

    request_doc = {
        "user_id": user.id, "username": user.username, "first_name": user.first_name,
        "method": "sham_cash", "amount": amount, "photo_file_id": photo.file_id,
        "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.recharge_requests.insert_one(request_doc)
    request_id = str(result.inserted_id)

    admin_text = f"📥 طلب شحن رصيد جديد (شام كاش)\n\n👤 المستخدم: {user.first_name}\n🆔 المعرف: @{user.username or 'N/A'}\n🔑 ID: {user.id}\n💰 المبلغ: {amount} ل.س"
    keyboard = [[
        InlineKeyboardButton("✅ قبول", callback_data=f"approve_recharge_{request_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject_recharge_{request_id}"),
    ]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo.file_id, caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("✅ تم إرسال طلبك بنجاح!\n⏳ يرجى انتظار تأكيد الأدمن.", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END

# ===========================================
# CWALLET
# ===========================================

async def cwallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    exchange_rate = await get_exchange_rate()
    await query.edit_message_text(f"💵 كم المبلغ المراد شحنه؟ أدخل المبلغ بالليرة السورية\n\n📝 ملاحظة: كل 1$ تساوي {exchange_rate} ليرة سورية")
    return CWALLET_AMOUNT

async def cwallet_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        context.user_data['cwallet_amount'] = amount
        exchange_rate = await get_exchange_rate()
        usd_amount = amount / exchange_rate
        text = f"💳 اشحن الرصيد عبر CWallet\nعلى معرف محفظة CWallet حول عليه👇\nTHEaoFQmETNbxiouYCBhKkaYZT4Zoo8GwJ\n\n💰 المبلغ بالدولار: ${usd_amount:.2f}\n📝 1$ = {exchange_rate} ليرة سورية\n\nيرجى إرسال إثبات الدفع (صورة فقط)"
        await update.message.reply_text(text)
        return CWALLET_PROOF
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح فقط!")
        return CWALLET_AMOUNT

async def cwallet_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ يرجى إرسال صورة فقط!")
        return CWALLET_PROOF
    
    photo = update.message.photo[-1]
    amount = context.user_data.get('cwallet_amount', 0)
    user = update.effective_user
    exchange_rate = await get_exchange_rate()

    request_doc = {
        "user_id": user.id, "username": user.username, "first_name": user.first_name,
        "method": "cwallet", "amount": amount, "photo_file_id": photo.file_id,
        "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.recharge_requests.insert_one(request_doc)
    request_id = str(result.inserted_id)

    admin_text = f"📥 طلب شحن رصيد جديد (CWallet)\n\n👤 المستخدم: {user.first_name}\n🆔 المعرف: @{user.username or 'N/A'}\n🔑 ID: {user.id}\n💰 المبلغ: {amount} ل.س (${amount/exchange_rate:.2f})"
    keyboard = [[
        InlineKeyboardButton("✅ قبول", callback_data=f"approve_recharge_{request_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject_recharge_{request_id}"),
    ]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo.file_id, caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("✅ تم إرسال طلبك بنجاح!\n⏳ يرجى انتظار تأكيد الأدمن.", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END

# ===========================================
# COINEX
# ===========================================

async def coinex_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    exchange_rate = await get_exchange_rate()
    await query.edit_message_text(f"💵 كم المبلغ المراد شحنه بالليرة السورية؟\n\n📝 ملاحظة: كل 1$ تساوي {exchange_rate} ليرة سورية")
    return COINEX_AMOUNT

async def coinex_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        context.user_data['coinex_amount'] = amount
        exchange_rate = await get_exchange_rate()
        usd_amount = amount / exchange_rate
        text = f"💳 اشحن الرصيد عبر CoinEx\nعلى معرف محفظة CoinEx حول عليه👇\n0xaace6d4956b27c293018556bedba49a5074d6020\n\n💰 المبلغ بالدولار: ${usd_amount:.2f}\n📝 1$ = {exchange_rate} ليرة سورية\n\nيرجى إرسال إثبات الدفع (صورة فقط)"
        await update.message.reply_text(text)
        return COINEX_PROOF
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح فقط!")
        return COINEX_AMOUNT

async def coinex_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ يرجى إرسال صورة فقط!")
        return COINEX_PROOF
    
    photo = update.message.photo[-1]
    amount = context.user_data.get('coinex_amount', 0)
    user = update.effective_user
    exchange_rate = await get_exchange_rate()

    request_doc = {
        "user_id": user.id, "username": user.username, "first_name": user.first_name,
        "method": "coinex", "amount": amount, "photo_file_id": photo.file_id,
        "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.recharge_requests.insert_one(request_doc)
    request_id = str(result.inserted_id)

    admin_text = f"📥 طلب شحن رصيد جديد (CoinEx)\n\n👤 المستخدم: {user.first_name}\n🆔 المعرف: @{user.username or 'N/A'}\n🔑 ID: {user.id}\n💰 المبلغ: {amount} ل.س (${amount/exchange_rate:.2f})"
    keyboard = [[
        InlineKeyboardButton("✅ قبول", callback_data=f"approve_recharge_{request_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject_recharge_{request_id}"),
    ]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo.file_id, caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("✅ تم إرسال طلبك بنجاح!\n⏳ يرجى انتظار تأكيد الأدمن.", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END

# ===========================================
# RECHARGE APPROVAL/REJECTION
# ===========================================

async def approve_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    
    request_id = query.data.replace("approve_recharge_", "")
    try:
        request = await db.recharge_requests.find_one({"_id": ObjectId(request_id)})
        if request and request.get("status") == "pending":
            await db.recharge_requests.update_one({"_id": ObjectId(request_id)}, {"$set": {"status": "approved", "approved_at": datetime.now(timezone.utc).isoformat()}})
            await update_user_balance(request["user_id"], request["amount"])
            user_balance = await get_user_balance(request["user_id"])
            await context.bot.send_message(chat_id=request["user_id"], text=f"✅ تم قبول طلب شحن الرصيد!\n\n💰 المبلغ المضاف: {request['amount']} ل.س\n💳 رصيدك الحالي: {user_balance} ل.س")
            try:
                if query.message.caption:
                    await query.edit_message_caption(caption=f"{query.message.caption}\n\n✅ تم القبول")
                else:
                    await query.edit_message_text(text=f"{query.message.text}\n\n✅ تم القبول")
            except:
                pass
        else:
            await query.answer("❌ الطلب غير موجود أو تمت معالجته مسبقاً")
    except Exception as e:
        logger.error(f"Error: {e}")

async def reject_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    
    request_id = query.data.replace("reject_recharge_", "")
    try:
        request = await db.recharge_requests.find_one({"_id": ObjectId(request_id)})
        if request and request.get("status") == "pending":
            await db.recharge_requests.update_one({"_id": ObjectId(request_id)}, {"$set": {"status": "rejected"}})
            await context.bot.send_message(chat_id=request["user_id"], text="❌ تم رفض طلب شحن الرصيد.\n\nإذا كنت تعتقد أن هذا خطأ، يرجى التواصل مع الدعم.")
            try:
                if query.message.caption:
                    await query.edit_message_caption(caption=f"{query.message.caption}\n\n❌ تم الرفض")
                else:
                    await query.edit_message_text(text=f"{query.message.text}\n\n❌ تم الرفض")
            except:
                pass
    except Exception as e:
        logger.error(f"Error: {e}")

# ===========================================
# BALANCE
# ===========================================

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    balance = await get_user_balance(user.id)
    text = f"💰 رصيدك الحالي\n\n🆔 معرف تلجرام: {user.id}\n👤 الاسم: {user.first_name}\n📛 المعرف: @{user.username or 'غير محدد'}\n\n💳 الرصيد: {balance} ل.س"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===========================================
# PRODUCTS
# ===========================================

async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = await db.products.find({}).to_list(100)
    keyboard = []
    for product in products:
        keyboard.append([InlineKeyboardButton(f"{product.get('emoji', '📦')} {product['name']}", callback_data=f"product_{product['category']}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    await query.edit_message_text("🛒 اختر المنتج:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_product_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("product_", "")
    context.user_data['selected_category'] = category
    product = await db.products.find_one({"category": category})
    accounts = await db.accounts.find({"category": category, "sold": False}).to_list(100)
    
    if not accounts:
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="products")]]
        await query.edit_message_text(f"❌ لا توجد حسابات متاحة حالياً لـ {product['name']}", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    prices = {}
    for acc in accounts:
        price = acc.get('price', 0)
        prices[price] = prices.get(price, 0) + 1
    
    text = f"📦 {product.get('emoji', '')} {product['name']}\n\nالحسابات المتاحة:\n"
    for price, count in prices.items():
        text += f"• {count} حساب بسعر {price} ل.س\n"
    
    keyboard = [
        [InlineKeyboardButton("🛒 شراء", callback_data=f"buy_{category}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="products")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("buy_", "")
    context.user_data['buy_category'] = category
    accounts = await db.accounts.find({"category": category, "sold": False}).to_list(100)
    
    if not accounts:
        await query.answer("❌ لا توجد حسابات متاحة!")
        return ConversationHandler.END
    
    context.user_data['available_count'] = len(accounts)
    context.user_data['account_price'] = accounts[0].get('price', 0)
    await query.edit_message_text(f"🛒 كم عدد الحسابات المراد شرائها؟\n\n📊 المتاح: {len(accounts)} حساب\n💰 السعر: {accounts[0].get('price', 0)} ل.س للحساب")
    return BUY_QUANTITY

async def process_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        quantity = int(update.message.text)
        available = context.user_data.get('available_count', 0)
        price = context.user_data.get('account_price', 0)
        category = context.user_data.get('buy_category')
        user = update.effective_user

        if quantity <= 0:
            await update.message.reply_text("❌ يرجى إدخال رقم أكبر من صفر!")
            return BUY_QUANTITY
        if quantity > available:
            await update.message.reply_text(f"❌ الكمية المطلوبة ({quantity}) أكبر من المتاح ({available})!")
            return BUY_QUANTITY

        total_price = quantity * price
        user_balance = await get_user_balance(user.id)

        if user_balance < total_price:
            await update.message.reply_text(f"❌ رصيدك غير كافٍ!\n\n💰 رصيدك: {user_balance} ل.س\n💳 المطلوب: {total_price} ل.س", reply_markup=get_main_menu_keyboard(user.id))
            return ConversationHandler.END

        accounts = await db.accounts.find({"category": category, "sold": False}).limit(quantity).to_list(quantity)
        account_ids = [acc['_id'] for acc in accounts]
        await db.accounts.update_many({"_id": {"$in": account_ids}}, {"$set": {"sold": True, "sold_to": user.id, "sold_at": datetime.now(timezone.utc).isoformat()}})
        await update_user_balance(user.id, -total_price)

        text = f"✅ تم الشراء بنجاح!\n\n📦 الحسابات المشتراة ({quantity}):\n\n"
        for i, acc in enumerate(accounts, 1):
            text += f"━━━━━━━━━━━━\n{i}. {acc.get('data', 'N/A')}\n"
        text += f"\n━━━━━━━━━━━━\n💰 المبلغ المدفوع: {total_price} ل.س"

        await db.purchases.insert_one({"user_id": user.id, "category": category, "quantity": quantity, "total_price": total_price, "account_ids": [str(aid) for aid in account_ids], "created_at": datetime.now(timezone.utc).isoformat()})
        await update.message.reply_text(text, reply_markup=get_main_menu_keyboard(user.id))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return BUY_QUANTITY

# ===========================================
# SUPPORT
# ===========================================

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "📞 تواصل مع الدعم\n\nللتواصل مع الدعم اضغط على معرف الأدمن\n@km0997055"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===========================================
# PRICES
# ===========================================

async def show_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    exchange_rate = await get_exchange_rate()
    products = await db.products.find({}).to_list(100)

    text = f"💵 أسعار الخدمات والصرف\n\n📈 سعر الصرف:\n• 1 دولار = {exchange_rate} ليرة سورية\n\n📋 أسعار الخدمات:"
    for product in products:
        accounts = await db.accounts.find({"category": product['category'], "sold": False}).to_list(1)
        if accounts:
            text += f"\n{product.get('emoji', '📦')} {product['name']}: {accounts[0].get('price', 'غير محدد')} ل.س"
        else:
            text += f"\n{product.get('emoji', '📦')} {product['name']}: غير متوفر حالياً"

    keyboard = []
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("✏️ تعديل سعر الصرف", callback_data="edit_exchange_rate")])
        keyboard.append([InlineKeyboardButton("✏️ تعديل أسعار المنتجات", callback_data="edit_product_prices")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===========================================
# EDIT EXCHANGE RATE
# ===========================================

async def edit_exchange_rate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    current_rate = await get_exchange_rate()
    await query.edit_message_text(f"📈 سعر الصرف الحالي: 1$ = {current_rate} ل.س\n\n✏️ أدخل سعر الصرف الجديد (رقم فقط):")
    return EDIT_EXCHANGE_RATE

async def edit_exchange_rate_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_rate = int(update.message.text)
        if new_rate <= 0:
            await update.message.reply_text("❌ يرجى إدخال رقم أكبر من صفر!")
            return EDIT_EXCHANGE_RATE
        await set_exchange_rate(new_rate)
        await update.message.reply_text(f"✅ تم تحديث سعر الصرف!\n\n📈 السعر الجديد: 1$ = {new_rate} ل.س", reply_markup=get_main_menu_keyboard(ADMIN_ID))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return EDIT_EXCHANGE_RATE

# ===========================================
# EDIT PRODUCT PRICES
# ===========================================

async def edit_product_prices_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    products = await db.products.find({}).to_list(100)
    keyboard = []
    for product in products:
        keyboard.append([InlineKeyboardButton(f"{product.get('emoji', '📦')} {product['name']}", callback_data=f"editprice_{product['category']}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="prices")])
    await query.edit_message_text("✏️ اختر المنتج لتعديل سعره:", reply_markup=InlineKeyboardMarkup(keyboard))

async def edit_product_price_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    category = query.data.replace("editprice_", "")
    context.user_data['edit_price_category'] = category
    product = await db.products.find_one({"category": category})
    accounts = await db.accounts.find({"category": category, "sold": False}).to_list(1)
    current_price = accounts[0].get('price', 'غير محدد') if accounts else 'غير محدد'
    await query.edit_message_text(f"📦 {product['name']}\n💰 السعر الحالي: {current_price} ل.س\n\n✏️ أدخل السعر الجديد (بالليرة السورية):")
    return EDIT_PRODUCT_PRICE_VALUE

async def edit_product_price_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_price = int(update.message.text)
        if new_price <= 0:
            await update.message.reply_text("❌ يرجى إدخال رقم أكبر من صفر!")
            return EDIT_PRODUCT_PRICE_VALUE
        category = context.user_data.get('edit_price_category')
        result = await db.accounts.update_many({"category": category, "sold": False}, {"$set": {"price": new_price}})
        product = await db.products.find_one({"category": category})
        await update.message.reply_text(f"✅ تم تحديث السعر!\n\n📦 {product['name']}\n💰 السعر الجديد: {new_price} ل.س\n📊 تم تحديث {result.modified_count} حساب", reply_markup=get_main_menu_keyboard(ADMIN_ID))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return EDIT_PRODUCT_PRICE_VALUE

# ===========================================
# ADMIN PANEL
# ===========================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ غير مصرح لك!")
        return
    keyboard = [
        [InlineKeyboardButton("📢 إرسال رسالة عامة", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 المشتركين", callback_data="admin_subscribers")],
        [InlineKeyboardButton("➕ إضافة حسابات", callback_data="admin_add_accounts")],
        [InlineKeyboardButton("📦 إضافة منتجات", callback_data="admin_add_product")],
        [InlineKeyboardButton("💰 إضافة رصيد يدوي", callback_data="admin_manual_balance")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ]
    await query.edit_message_text("⚙️ لوحة إدارة البوت", reply_markup=InlineKeyboardMarkup(keyboard))

# ===========================================
# ADMIN - BROADCAST
# ===========================================

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await query.edit_message_text("📢 اكتب الرسالة المراد إرسالها لجميع المستخدمين:")
    return BROADCAST_MESSAGE

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    users = await db.users.find({}).to_list(10000)
    sent, failed = 0, 0
    for user in users:
        try:
            await context.bot.send_message(chat_id=user['user_id'], text=message)
            sent += 1
        except:
            failed += 1
    await update.message.reply_text(f"✅ تم إرسال الرسالة!\n\n📤 نجح: {sent}\n❌ فشل: {failed}", reply_markup=get_main_menu_keyboard(ADMIN_ID))
    return ConversationHandler.END

# ===========================================
# ADMIN - ADD ACCOUNTS
# ===========================================

async def admin_add_accounts_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    products = await db.products.find({}).to_list(100)
    keyboard = []
    for product in products:
        keyboard.append([InlineKeyboardButton(f"{product.get('emoji', '📦')} {product['name']}", callback_data=f"addacc_{product['category']}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    await query.edit_message_text("➕ اختر القسم لإضافة حساب:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    category = query.data.replace("addacc_", "")
    context.user_data['admin_acc_category'] = category
    product = await db.products.find_one({"category": category})
    await query.edit_message_text(f"📦 القسم: {product['name']}\n\n💰 أدخل سعر الحساب (بالليرة السورية):")
    return ADD_ACCOUNT_PRICE

async def admin_receive_account_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
        if price <= 0:
            await update.message.reply_text("❌ يرجى إدخال رقم أكبر من صفر!")
            return ADD_ACCOUNT_PRICE
        context.user_data['admin_acc_price'] = price
        await update.message.reply_text(f"💰 السعر: {price} ل.س\n\n📝 أدخل بيانات الحساب:")
        return ADD_ACCOUNT_DATA
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return ADD_ACCOUNT_PRICE

async def admin_receive_account_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.text
    category = context.user_data.get('admin_acc_category')
    price = context.user_data.get('admin_acc_price')
    product = await db.products.find_one({"category": category})
    await db.accounts.insert_one({"category": category, "data": data, "price": price, "sold": False, "created_at": datetime.now(timezone.utc).isoformat()})
    await update.message.reply_text(f"✅ تم إضافة الحساب بنجاح!\n\n📦 القسم: {product['name']}\n💰 السعر: {price} ل.س\n📝 البيانات: {data}", reply_markup=get_main_menu_keyboard(ADMIN_ID))
    return ConversationHandler.END

# ===========================================
# ADMIN - ADD PRODUCT
# ===========================================

async def admin_add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await query.edit_message_text("📦 أدخل اسم المنتج الجديد:")
    return ADD_PRODUCT_NAME

async def admin_receive_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    category = name.lower().replace(" ", "_").replace(".", "").replace("-", "_")
    existing = await db.products.find_one({"category": category})
    if existing:
        await update.message.reply_text("❌ المنتج موجود مسبقاً!\n\n📦 أدخل اسم منتج آخر:")
        return ADD_PRODUCT_NAME
    await db.products.insert_one({"name": name, "category": category, "emoji": "📦", "created_at": datetime.now(timezone.utc).isoformat()})
    await update.message.reply_text(f"✅ تم إضافة المنتج بنجاح!\n\n📦 الاسم: {name}", reply_markup=get_main_menu_keyboard(ADMIN_ID))
    return ConversationHandler.END

# ===========================================
# ADMIN - MANUAL BALANCE
# ===========================================

async def admin_manual_balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await query.edit_message_text("🆔 أدخل ID المستخدم:")
    return MANUAL_BALANCE_USER_ID

async def admin_receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        context.user_data['manual_balance_user_id'] = user_id
        user = await db.users.find_one({"user_id": user_id})
        if not user:
            await update.message.reply_text("❌ المستخدم غير موجود!\n\n🆔 أدخل ID المستخدم:")
            return MANUAL_BALANCE_USER_ID
        context.user_data['manual_balance_user_info'] = {"first_name": user.get('first_name', 'N/A'), "username": user.get('username'), "balance": user.get('balance', 0)}
        await update.message.reply_text(f"👤 المستخدم: {user.get('first_name', 'N/A')}\n📛 المعرف: @{user.get('username', 'غير محدد')}\n💰 الرصيد الحالي: {user.get('balance', 0)} ل.س\n\n💵 أدخل المبلغ المراد إضافته:")
        return MANUAL_BALANCE_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!\n\n🆔 أدخل ID المستخدم:")
        return MANUAL_BALANCE_USER_ID

async def admin_receive_balance_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount == 0:
            await update.message.reply_text("❌ يرجى إدخال مبلغ غير صفر!")
            return MANUAL_BALANCE_AMOUNT
        user_id = context.user_data.get('manual_balance_user_id')
        user_info = context.user_data.get('manual_balance_user_info', {})
        await update_user_balance(user_id, amount)
        new_balance = await get_user_balance(user_id)
        try:
            await context.bot.send_message(chat_id=user_id, text=f"✅ تم إضافة رصيد لحسابك!\n\n💰 المبلغ المضاف: {amount} ل.س\n💳 رصيدك الجديد: {new_balance} ل.س")
        except:
            pass
        await update.message.reply_text(f"✅ تم إضافة الرصيد بنجاح!\n\n👤 المستخدم: {user_info.get('first_name', 'N/A')}\n🆔 ID: {user_id}\n💰 المبلغ المضاف: {amount} ل.س\n💳 الرصيد الجديد: {new_balance} ل.س", reply_markup=get_main_menu_keyboard(ADMIN_ID))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return MANUAL_BALANCE_AMOUNT

# ===========================================
# ADMIN - STATS
# ===========================================

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    users_count = await db.users.count_documents({})
    accounts_count = await db.accounts.count_documents({"sold": False})
    sold_count = await db.accounts.count_documents({"sold": True})
    pending_recharges = await db.recharge_requests.count_documents({"status": "pending"})
    text = f"📊 إحصائيات البوت\n\n👥 عدد المستخدمين: {users_count}\n📦 الحسابات المتاحة: {accounts_count}\n✅ الحسابات المباعة: {sold_count}\n⏳ طلبات الشحن المعلقة: {pending_recharges}"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===========================================
# ADMIN - SUBSCRIBERS
# ===========================================

async def admin_subscribers_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    await query.edit_message_text("👥 البحث عن مشترك\n\n🆔 أدخل ID المستخدم للبحث عنه:")
    return SUBSCRIBER_LOOKUP_ID

async def admin_lookup_subscriber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        user = await db.users.find_one({"user_id": user_id})
        if not user:
            keyboard = [[InlineKeyboardButton("🔍 بحث آخر", callback_data="admin_subscribers")], [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
            await update.message.reply_text("❌ المستخدم غير موجود!", reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END
        
        purchases = await db.purchases.find({"user_id": user_id}).to_list(100)
        recharges = await db.recharge_requests.find({"user_id": user_id}).to_list(100)
        
        total_purchases = len(purchases)
        total_accounts_bought = sum(p.get('quantity', 0) for p in purchases)
        total_spent = sum(p.get('total_price', 0) for p in purchases)
        approved_recharges = len([r for r in recharges if r.get('status') == 'approved'])
        total_recharged = sum(r.get('amount', 0) for r in recharges if r.get('status') == 'approved')

        text = f"👤 تفاصيل المشترك\n\n🆔 ID: {user_id}\n👤 الاسم: {user.get('first_name', 'غير محدد')}\n📛 المعرف: @{user.get('username', 'غير محدد')}\n💰 الرصيد: {user.get('balance', 0)} ل.س\n\n🛒 المشتريات: {total_purchases}\n📦 الحسابات: {total_accounts_bought}\n💵 المدفوع: {total_spent} ل.س\n\n💳 الشحنات المقبولة: {approved_recharges}\n💰 إجمالي الشحن: {total_recharged} ل.س"
        keyboard = [[InlineKeyboardButton("🔍 بحث آخر", callback_data="admin_subscribers")], [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return SUBSCRIBER_LOOKUP_ID

# ===========================================
# CANCEL
# ===========================================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text("❌ تم الإلغاء.", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END

# ===========================================
# MAIN
# ===========================================

def main():
    async def init():
        await init_default_products()
    asyncio.get_event_loop().run_until_complete(init())

    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))

    # CONVERSATION HANDLERS FIRST (ORDER MATTERS!)
    
    # Syriatel
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(syriatel_confirm, pattern="^syriatel_confirm$")],
        states={
            SYRIATEL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, syriatel_amount_received)],
            SYRIATEL_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, syriatel_code_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Sham Cash
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(sham_start, pattern="^recharge_sham$")],
        states={
            SHAM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sham_amount_received)],
            SHAM_PROOF: [MessageHandler(filters.PHOTO, sham_proof_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # CWallet
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(cwallet_start, pattern="^recharge_cwallet$")],
        states={
            CWALLET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cwallet_amount_received)],
            CWALLET_PROOF: [MessageHandler(filters.PHOTO, cwallet_proof_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # CoinEx
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(coinex_start, pattern="^recharge_coinex$")],
        states={
            COINEX_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, coinex_amount_received)],
            COINEX_PROOF: [MessageHandler(filters.PHOTO, coinex_proof_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Buy
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_buy, pattern="^buy_")],
        states={
            BUY_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_buy)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Admin Broadcast
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Admin Add Account
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_select_category, pattern="^addacc_")],
        states={
            ADD_ACCOUNT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_account_price)],
            ADD_ACCOUNT_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_account_data)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Admin Add Product
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_product_start, pattern="^admin_add_product$")],
        states={
            ADD_PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_product_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Admin Manual Balance
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_manual_balance_start, pattern="^admin_manual_balance$")],
        states={
            MANUAL_BALANCE_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_user_id)],
            MANUAL_BALANCE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_balance_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Admin Edit Exchange Rate
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_exchange_rate_start, pattern="^edit_exchange_rate$")],
        states={
            EDIT_EXCHANGE_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_exchange_rate_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Admin Edit Product Price
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_product_price_select, pattern="^editprice_")],
        states={
            EDIT_PRODUCT_PRICE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_product_price_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Admin Subscribers
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_subscribers_start, pattern="^admin_subscribers$")],
        states={
            SUBSCRIBER_LOOKUP_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_lookup_subscriber)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # REGULAR CALLBACK HANDLERS (AFTER CONVERSATION HANDLERS)
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(recharge_menu, pattern="^recharge$"))
    application.add_handler(CallbackQueryHandler(syriatel_info, pattern="^recharge_syriatel$"))
    application.add_handler(CallbackQueryHandler(show_balance, pattern="^my_balance$"))
    application.add_handler(CallbackQueryHandler(show_products, pattern="^products$"))
    application.add_handler(CallbackQueryHandler(show_product_accounts, pattern="^product_"))
    application.add_handler(CallbackQueryHandler(show_support, pattern="^support$"))
    application.add_handler(CallbackQueryHandler(show_prices, pattern="^prices$"))
    application.add_handler(CallbackQueryHandler(edit_product_prices_start, pattern="^edit_product_prices$"))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(admin_add_accounts_start, pattern="^admin_add_accounts$"))
    application.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(approve_recharge, pattern="^approve_recharge_"))
    application.add_handler(CallbackQueryHandler(reject_recharge, pattern="^reject_recharge_"))

    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main
