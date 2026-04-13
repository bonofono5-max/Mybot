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
                "name": product["name"],
                "category": product["category"],
                "emoji": product["emoji"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })


def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Get main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("➕ شحن الرصيد", callback_data="recharge")],
        [InlineKeyboardButton("💰 رصيدي", callback_data="my_balance")],
        [InlineKeyboardButton("🛒 المنتجات", callback_data="products")],
        [InlineKeyboardButton("📞 تواصل مع الدعم", callback_data="support")],
        [InlineKeyboardButton("💵 أسعار الخدمات والصرف", callback_data="prices")],
    ]
    
    # Add admin button if user is admin
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ إدارة خدمات البوت", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    await ensure_user_exists(user.id, user.username, user.first_name)
    
    welcome_text = f"""
مرحباً {user.first_name}! 👋

أهلاً بك في بوت الخدمات المتكاملة

اختر من القائمة أدناه:
"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard(user.id)
    )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu button press"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    await query.edit_message_text(
        text="اختر من القائمة أدناه:",
        reply_markup=get_main_menu_keyboard(user.id)
    )


# ==================== RECHARGE HANDLERS ====================

async def recharge_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recharge options"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📱 سيريتل كاش", callback_data="recharge_syriatel")],
        [InlineKeyboardButton("💵 شام كاش", callback_data="recharge_sham")],
        [InlineKeyboardButton("👛 محفظة CWallet", callback_data="recharge_cwallet")],
        [InlineKeyboardButton("🔸 محفظة CoinEx", callback_data="recharge_coinex")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ]
    
    await query.edit_message_text(
        "💳 اختر وسيلة الشحن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==================== SYRIATEL CASH ====================

async def syriatel_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Syriatel cash info"""
    query = update.callback_query
    await query.answer()
    
    text = """
💳 شحن الرصيد عبر سيريتل كاش (تحويل يدوي)

📱 أرقام سيريتل كاش:
0934595626
0935579034

📌 الخطوات:
1️⃣ قم بتحويل المبلغ المراد شحنه إلى أحد الأرقام أعلاه
2️⃣ بعد التحويل اضغط على زر تأكيد التحويل أدناه
⚠️ تأكد من حفظ رقم التحويلة (الكود)
"""
    
    keyboard = [
        [
            InlineKeyboardButton("✅ تأكيد", callback_data="syriatel_confirm"),
            InlineKeyboardButton("❌ إلغاء", callback_data="recharge"),
        ],
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def syriatel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for amount"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "💵 قم بإدخال المبلغ الذي حولته؟ بالليرة السورية (أدخل الرقم فقط)"
    )
    
    return SYRIATEL_AMOUNT


async def syriatel_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive amount and ask for code"""
    try:
        amount = int(update.message.text)
        context.user_data['syriatel_amount'] = amount
        
        await update.message.reply_text(
            "🔢 أدخل رقم عملية التحويل (الكود):"
        )
        
        return SYRIATEL_CODE
    except ValueError:
        await update.message.reply_text(
            "❌ يرجى إدخال رقم صحيح فقط!\n\n💵 قم بإدخال المبلغ الذي حولته؟ بالليرة السورية (أدخل الرقم فقط)"
        )
        return SYRIATEL_AMOUNT


async def syriatel_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive code and send to admin"""
    code = update.message.text
    amount = context.user_data.get('syriatel_amount', 0)
    user = update.effective_user
    
    # Save request to database
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
    
    # Notify admin
    admin_text = f"""
📥 طلب شحن رصيد جديد (سيريتل كاش)

👤 المستخدم: {user.first_name}
🆔 المعرف: @{user.username or 'N/A'}
🔑 ID: {user.id}
💰 المبلغ: {amount} ل.س
🔢 كود التحويل: {code}
"""
    
    keyboard = [
        [
            InlineKeyboardButton("✅ قبول", callback_data=f"approve_recharge_{request_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_recharge_{request_id}"),
        ],
    ]
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await update.message.reply_text(
        "✅ تم إرسال طلبك بنجاح!\n⏳ يرجى انتظار تأكيد الأدمن.",
        reply_markup=get_main_menu_keyboard(user.id)
    )
    
    return ConversationHandler.END


# ==================== SHAM CASH ====================

async def sham_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start Sham cash recharge"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("💵 كم المبلغ المراد شحنه؟ (بالليرة السورية)")
    
    return SHAM_AMOUNT


async def sham_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive amount and show payment info"""
    try:
        amount = int(update.message.text)
        context.user_data['sham_amount'] = amount
        
        text = """
💳 اشحن الرصيد عبر شام كاش
على معرف شام كاش حول عليه👇
bc9d9b41336308e2a4f9e0ffe86f48a0

يرجى إرسال إثبات الدفع (صورة فقط)
سيتم مراجعة الطلب من الأدمن قريباً يرجى الانتظار
"""
        await update.message.reply_text(text)
        
        return SHAM_PROOF
    except ValueError:
        await update.message.reply_text(
            "❌ يرجى إدخال رقم صحيح فقط!\n\n💵 كم المبلغ المراد شحنه؟ (بالليرة السورية)"
        )
        return SHAM_AMOUNT


async def sham_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive payment proof image"""
    if not update.message.photo:
        await update.message.reply_text("❌ يرجى إرسال صورة فقط!")
        return SHAM_PROOF
    
    photo = update.message.photo[-1]
    amount = context.user_data.get('sham_amount', 0)
    user = update.effective_user
    
    # Save request
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
    
    # Notify admin
    admin_text = f"""
📥 طلب شحن رصيد جديد (شام كاش)

👤 المستخدم: {user.first_name}
🆔 المعرف: @{user.username or 'N/A'}
🔑 ID: {user.id}
💰 المبلغ: {amount} ل.س
"""
    
    keyboard = [
        [
            InlineKeyboardButton("✅ قبول", callback_data=f"approve_recharge_{request_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_recharge_{request_id}"),
        ],
    ]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await update.message.reply_text(
        "✅ تم إرسال طلبك بنجاح!\n⏳ يرجى انتظار تأكيد الأدمن.",
        reply_markup=get_main_menu_keyboard(user.id)
    )
    
    return ConversationHandler.END


# ==================== CWALLET ====================

async def cwallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start CWallet recharge"""
    query = update.callback_query
    await query.answer()
    
    exchange_rate = await get_exchange_rate()
    await query.edit_message_text(
        f"💵 كم المبلغ المراد شحنه؟ أدخل المبلغ بالليرة السورية\n\n📝 ملاحظة: كل 1$ تساوي {exchange_rate} ليرة سورية"
    )
    
    return CWALLET_AMOUNT


async def cwallet_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive amount and show payment info"""
    try:
        amount = int(update.message.text)
        context.user_data['cwallet_amount'] = amount
        exchange_rate = await get_exchange_rate()
        usd_amount = amount / exchange_rate
        
        text = f"""
💳 اشحن الرصيد عبر CWallet
على معرف محفظة CWallet حول عليه👇
THEaoFQmETNbxiouYCBhKkaYZT4Zoo8GwJ

💰 المبلغ بالدولار: ${usd_amount:.2f}
📝 1$ = {exchange_rate} ليرة سورية

يرجى إرسال إثبات الدفع (صورة فقط)
"""
        await update.message.reply_text(text)
        
        return CWALLET_PROOF
    except ValueError:
        exchange_rate = await get_exchange_rate()
        await update.message.reply_text(
            f"❌ يرجى إدخال رقم صحيح فقط!\n\n💵 كم المبلغ المراد شحنه؟ أدخل المبلغ بالليرة السورية\n\n📝 ملاحظة: كل 1$ تساوي {exchange_rate} ليرة سورية"
        )
        return CWALLET_AMOUNT


async def cwallet_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive payment proof image"""
    if not update.message.photo:
        await update.message.reply_text("❌ يرجى إرسال صورة فقط!")
        return CWALLET_PROOF
    
    photo = update.message.photo[-1]
    amount = context.user_data.get('cwallet_amount', 0)
    user = update.effective_user
    
    # Save request
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
    
    # Notify admin
    admin_text = f"""
📥 طلب شحن رصيد جديد (CWallet)

👤 المستخدم: {user.first_name}
🆔 المعرف: @{user.username or 'N/A'}
🔑 ID: {user.id}
💰 المبلغ: {amount} ل.س (${amount/120:.2f})
"""
    
    keyboard = [
        [
            InlineKeyboardButton("✅ قبول", callback_data=f"approve_recharge_{request_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_recharge_{request_id}"),
        ],
    ]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await update.message.reply_text(
        "✅ تم إرسال طلبك بنجاح!\n⏳ يرجى انتظار تأكيد الأدمن.",
        reply_markup=get_main_menu_keyboard(user.id)
    )
    
    return ConversationHandler.END


# ==================== COINEX ====================

async def coinex_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start CoinEx recharge"""
    query = update.callback_query
    await query.answer()
    
    exchange_rate = await get_exchange_rate()
    await query.edit_message_text(
        f"💵 كم المبلغ المراد شحنه بالليرة السورية؟\n\n📝 ملاحظة: كل 1$ تساوي {exchange_rate} ليرة سورية"
    )
    
    return COINEX_AMOUNT


async def coinex_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive amount and show payment info"""
    try:
        amount = int(update.message.text)
        context.user_data['coinex_amount'] = amount
        exchange_rate = await get_exchange_rate()
        usd_amount = amount / exchange_rate
        
        text = f"""
💳 اشحن الرصيد عبر CoinEx
على معرف محفظة CoinEx حول عليه👇
0xaace6d4956b27c293018556bedba49a5074d6020

💰 المبلغ بالدولار: ${usd_amount:.2f}
📝 1$ = {exchange_rate} ليرة سورية

يرجى إرسال إثبات الدفع (صورة فقط)
"""
        await update.message.reply_text(text)
        
        return COINEX_PROOF
    except ValueError:
        exchange_rate = await get_exchange_rate()
        await update.message.reply_text(
            f"❌ يرجى إدخال رقم صحيح فقط!\n\n💵 كم المبلغ المراد شحنه بالليرة السورية؟\n\n📝 ملاحظة: كل 1$ تساوي {exchange_rate} ليرة سورية"
        )
        return COINEX_AMOUNT


async def coinex_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive payment proof image"""
    if not update.message.photo:
        await update.message.reply_text("❌ يرجى إرسال صورة فقط!")
        return COINEX_PROOF
    
    photo = update.message.photo[-1]
    amount = context.user_data.get('coinex_amount', 0)
    user = update.effective_user
    
    # Save request
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
    
    # Notify admin
    admin_text = f"""
📥 طلب شحن رصيد جديد (CoinEx)

👤 المستخدم: {user.first_name}
🆔 المعرف: @{user.username or 'N/A'}
🔑 ID: {user.id}
💰 المبلغ: {amount} ل.س (${amount/120:.2f})
"""
    
    keyboard = [
        [
            InlineKeyboardButton("✅ قبول", callback_data=f"approve_recharge_{request_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_recharge_{request_id}"),
        ],
    ]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await update.message.reply_text(
        "✅ تم إرسال طلبك بنجاح!\n⏳ يرجى انتظار تأكيد الأدمن.",
        reply_markup=get_main_menu_keyboard(user.id)
    )
    
    return ConversationHandler.END


# ==================== RECHARGE APPROVAL/REJECTION ====================

async def approve_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve recharge request"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    request_id = query.data.replace("approve_recharge_", "")
    
    from bson import ObjectId
    request = await db.recharge_requests.find_one({"_id": ObjectId(request_id)})
    
    if request and request.get("status") == "pending":
        # Update request status
        await db.recharge_requests.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"status": "approved", "approved_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        # Add balance to user
        await update_user_balance(request["user_id"], request["amount"])
        
        # Notify user
        user_balance = await get_user_balance(request["user_id"])
        await context.bot.send_message(
            chat_id=request["user_id"],
            text=f"✅ تم قبول طلب شحن الرصيد!\n\n💰 المبلغ المضاف: {request['amount']} ل.س\n💳 رصيدك الحالي: {user_balance} ل.س"
        )
        
        await query.edit_message_caption(
            caption=f"{query.message.caption or query.message.text}\n\n✅ تم القبول"
        )
    else:
        await query.answer("❌ الطلب غير موجود أو تمت معالجته مسبقاً")


async def reject_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject recharge request"""
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
        
        # Notify user
        await context.bot.send_message(
            chat_id=request["user_id"],
            text="❌ تم رفض طلب شحن الرصيد.\n\nإذا كنت تعتقد أن هذا خطأ، يرجى التواصل مع الدعم."
        )
        
        await query.edit_message_caption(
            caption=f"{query.message.caption or query.message.text}\n\n❌ تم الرفض"
        )
    else:
        await query.answer("❌ الطلب غير موجود أو تمت معالجته مسبقاً")


# ==================== BALANCE ====================

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user balance"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    balance = await get_user_balance(user.id)
    
    text = f"""
💰 رصيدك الحالي

🆔 معرف تلجرام: {user.id}
👤 الاسم: {user.first_name}
📛 المعرف: @{user.username or 'غير محدد'}

💳 الرصيد: {balance} ل.س
"""
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ==================== PRODUCTS ====================

async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show products list"""
    query = update.callback_query
    await query.answer()
    
    products = await db.products.find({}, {"_id": 0}).to_list(100)
    
    keyboard = []
    for product in products:
        keyboard.append([
            InlineKeyboardButton(
                f"{product.get('emoji', '📦')} {product['name']}",
                callback_data=f"product_{product['category']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    
    await query.edit_message_text(
        "🛒 اختر المنتج:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_product_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available accounts for a product"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("product_", "")
    context.user_data['selected_category'] = category
    
    product = await db.products.find_one({"category": category}, {"_id": 0})
    accounts = await db.accounts.find({"category": category, "sold": False}, {"_id": 0}).to_list(100)
    
    if not accounts:
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="products")]]
        await query.edit_message_text(
            f"❌ لا توجد حسابات متاحة حالياً لـ {product['name']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Group by price
    prices = {}
    for acc in accounts:
        price = acc.get('price', 0)
        if price not in prices:
            prices[price] = 0
        prices[price] += 1
    
    text = f"📦 {product.get('emoji', '')} {product['name']}\n\n"
    text += "الحسابات المتاحة:\n"
    for price, count in prices.items():
        text += f"• {count} حساب بسعر {price} ل.س\n"
    
    keyboard = [
        [InlineKeyboardButton("🛒 شراء", callback_data=f"buy_{category}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="products")],
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def start_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start buying process"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("buy_", "")
    context.user_data['buy_category'] = category
    
    accounts = await db.accounts.find({"category": category, "sold": False}, {"_id": 0}).to_list(100)
    
    if not accounts:
        await query.answer("❌ لا توجد حسابات متاحة!")
        return ConversationHandler.END
    
    context.user_data['available_count'] = len(accounts)
    context.user_data['account_price'] = accounts[0].get('price', 0)
    
    await query.edit_message_text(
        f"🛒 كم عدد الحسابات المراد شرائها؟\n\n📊 المتاح: {len(accounts)} حساب\n💰 السعر: {accounts[0].get('price', 0)} ل.س للحساب"
    )
    
    return BUY_QUANTITY


async def process_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process purchase"""
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
            await update.message.reply_text(
                f"❌ رصيدك غير كافٍ!\n\n💰 رصيدك: {user_balance} ل.س\n💳 المطلوب: {total_price} ل.س",
                reply_markup=get_main_menu_keyboard(user.id)
            )
            return ConversationHandler.END
        
        # Get accounts
        from bson import ObjectId
        accounts = await db.accounts.find({"category": category, "sold": False}).limit(quantity).to_list(quantity)
        
        if len(accounts) < quantity:
            await update.message.reply_text("❌ حدث خطأ، يرجى المحاولة لاحقاً.")
            return ConversationHandler.END
        
        # Mark accounts as sold
        account_ids = [acc['_id'] for acc in accounts]
        await db.accounts.update_many(
            {"_id": {"$in": account_ids}},
            {"$set": {"sold": True, "sold_to": user.id, "sold_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        # Deduct balance
        await update_user_balance(user.id, -total_price)
        
        # Send accounts to user
        text = f"✅ تم الشراء بنجاح!\n\n📦 الحسابات المشتراة ({quantity}):\n\n"
        for i, acc in enumerate(accounts, 1):
            text += f"━━━━━━━━━━━━\n{i}. {acc.get('data', 'N/A')}\n"
        
        text += f"\n━━━━━━━━━━━━\n💰 المبلغ المدفوع: {total_price} ل.س"
        
        # Save purchase record
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
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return BUY_QUANTITY


# ==================== SUPPORT ====================

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show support contact"""
    query = update.callback_query
    await query.answer()
    
    text = """
📞 تواصل مع الدعم

للتواصل مع الدعم اضغط على معرف الأدمن
@km0997055
"""
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ==================== PRICES ====================

async def show_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show prices and exchange rate"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    exchange_rate = await get_exchange_rate()
    products = await db.products.find({}, {"_id": 0}).to_list(100)
    
    text = f"""
💵 أسعار الخدمات والصرف

📈 سعر الصرف:
• 1 دولار = {exchange_rate} ليرة سورية

📋 أسعار الخدمات:
"""
    
    for product in products:
        accounts = await db.accounts.find({"category": product['category'], "sold": False}, {"_id": 0}).to_list(1)
        if accounts:
            text += f"\n{product.get('emoji', '📦')} {product['name']}: {accounts[0].get('price', 'غير محدد')} ل.س"
        else:
            text += f"\n{product.get('emoji', '📦')} {product['name']}: غير متوفر حالياً"
    
    keyboard = []
    
    # Add edit buttons for admin only
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("✏️ تعديل سعر الصرف", callback_data="edit_exchange_rate")])
        keyboard.append([InlineKeyboardButton("✏️ تعديل أسعار المنتجات", callback_data="edit_product_prices")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ==================== EDIT EXCHANGE RATE ====================

async def edit_exchange_rate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start editing exchange rate"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    current_rate = await get_exchange_rate()
    await query.edit_message_text(
        f"📈 سعر الصرف الحالي: 1$ = {current_rate} ل.س\n\n✏️ أدخل سعر الصرف الجديد (رقم فقط):"
    )
    
    return EDIT_EXCHANGE_RATE


async def edit_exchange_rate_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save new exchange rate"""
    try:
        new_rate = int(update.message.text)
        if new_rate <= 0:
            await update.message.reply_text("❌ يرجى إدخال رقم أكبر من صفر!")
            return EDIT_EXCHANGE_RATE
        
        await set_exchange_rate(new_rate)
        
        await update.message.reply_text(
            f"✅ تم تحديث سعر الصرف!\n\n📈 السعر الجديد: 1$ = {new_rate} ل.س",
            reply_markup=get_main_menu_keyboard(ADMIN_ID)
        )
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return EDIT_EXCHANGE_RATE


# ==================== EDIT PRODUCT PRICES ====================

async def edit_product_prices_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show products to edit their prices"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    products = await db.products.find({}, {"_id": 0}).to_list(100)
    
    keyboard = []
    for product in products:
        keyboard.append([
            InlineKeyboardButton(
                f"{product.get('emoji', '📦')} {product['name']}",
                callback_data=f"edit_price_{product['category']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="prices")])
    
    await query.edit_message_text(
        "✏️ اختر المنتج لتعديل سعره:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def edit_product_price_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select product to edit price"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    category = query.data.replace("edit_price_", "")
    context.user_data['edit_price_category'] = category
    
    product = await db.products.find_one({"category": category}, {"_id": 0})
    accounts = await db.accounts.find({"category": category, "sold": False}, {"_id": 0}).to_list(1)
    
    current_price = accounts[0].get('price', 'غير محدد') if accounts else 'غير محدد'
    
    await query.edit_message_text(
        f"📦 {product['name']}\n💰 السعر الحالي: {current_price} ل.س\n\n✏️ أدخل السعر الجديد (بالليرة السورية):"
    )
    
    return EDIT_PRODUCT_PRICE_VALUE


async def edit_product_price_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save new product price"""
    try:
        new_price = int(update.message.text)
        if new_price <= 0:
            await update.message.reply_text("❌ يرجى إدخال رقم أكبر من صفر!")
            return EDIT_PRODUCT_PRICE_VALUE
        
        category = context.user_data.get('edit_price_category')
        
        # Update all unsold accounts in this category
        result = await db.accounts.update_many(
            {"category": category, "sold": False},
            {"$set": {"price": new_price}}
        )
        
        product = await db.products.find_one({"category": category}, {"_id": 0})
        
        await update.message.reply_text(
            f"✅ تم تحديث السعر!\n\n📦 {product['name']}\n💰 السعر الجديد: {new_price} ل.س\n📊 تم تحديث {result.modified_count} حساب",
            reply_markup=get_main_menu_keyboard(ADMIN_ID)
        )
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return EDIT_PRODUCT_PRICE_VALUE


# ==================== ADMIN PANEL ====================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ غير مصرح لك!")
        return
    
    keyboard = [
        [InlineKeyboardButton("📢 إرسال رسالة عامة", callback_data="admin_broadcast")],
        [InlineKeyboardButton("➕ إضافة حسابات", callback_data="admin_add_accounts")],
        [InlineKeyboardButton("📦 إضافة منتجات", callback_data="admin_add_product")],
        [InlineKeyboardButton("💰 إضافة رصيد يدوي", callback_data="admin_manual_balance")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ]
    
    await query.edit_message_text(
        "⚙️ لوحة إدارة البوت",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==================== ADMIN - BROADCAST ====================

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start broadcast"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    await query.edit_message_text("📢 اكتب الرسالة المراد إرسالها لجميع المستخدمين:")
    
    return BROADCAST_MESSAGE


async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send broadcast message"""
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
    
    await update.message.reply_text(
        f"✅ تم إرسال الرسالة!\n\n📤 نجح: {sent}\n❌ فشل: {failed}",
        reply_markup=get_main_menu_keyboard(ADMIN_ID)
    )
    
    return ConversationHandler.END


# ==================== ADMIN - ADD ACCOUNTS ====================

async def admin_add_accounts_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding accounts"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    products = await db.products.find({}, {"_id": 0}).to_list(100)
    
    keyboard = []
    for product in products:
        keyboard.append([
            InlineKeyboardButton(
                f"{product.get('emoji', '📦')} {product['name']}",
                callback_data=f"admin_acc_cat_{product['category']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    
    await query.edit_message_text(
        "➕ اختر القسم لإضافة حساب:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select category for adding account"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    category = query.data.replace("admin_acc_cat_", "")
    context.user_data['admin_acc_category'] = category
    
    await query.edit_message_text("📝 أدخل بيانات الحساب:")
    
    return ADD_ACCOUNT_DATA


async def admin_receive_account_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive account data"""
    context.user_data['admin_acc_data'] = update.message.text
    
    await update.message.reply_text("💰 أدخل سعر الحساب (بالليرة السورية):")
    
    return ADD_ACCOUNT_PRICE


async def admin_receive_account_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive account price and save"""
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
        
        await update.message.reply_text(
            f"✅ تم إضافة الحساب بنجاح!\n\n📦 القسم: {category}\n💰 السعر: {price} ل.س",
            reply_markup=get_main_menu_keyboard(ADMIN_ID)
        )
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return ADD_ACCOUNT_PRICE


# ==================== ADMIN - ADD PRODUCT ====================

async def admin_add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding new product"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    await query.edit_message_text("📦 أدخل اسم المنتج الجديد:")
    
    return ADD_PRODUCT_NAME


async def admin_receive_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive product name and save"""
    name = update.message.text
    category = name.lower().replace(" ", "_")
    
    await db.products.insert_one({
        "name": name,
        "category": category,
        "emoji": "📦",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    
    await update.message.reply_text(
        f"✅ تم إضافة المنتج بنجاح!\n\n📦 الاسم: {name}",
        reply_markup=get_main_menu_keyboard(ADMIN_ID)
    )
    
    return ConversationHandler.END


# ==================== ADMIN - MANUAL BALANCE ====================

async def admin_manual_balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start manual balance addition"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    await query.edit_message_text("🆔 أدخل ID المستخدم:")
    
    return MANUAL_BALANCE_USER_ID


async def admin_receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive user ID"""
    try:
        user_id = int(update.message.text)
        context.user_data['manual_balance_user_id'] = user_id
        
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not user:
            await update.message.reply_text(
                "❌ المستخدم غير موجود!",
                reply_markup=get_main_menu_keyboard(ADMIN_ID)
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            f"👤 المستخدم: {user.get('first_name', 'N/A')}\n💰 الرصيد الحالي: {user.get('balance', 0)} ل.س\n\n💵 أدخل المبلغ المراد إضافته:"
        )
        
        return MANUAL_BALANCE_AMOUNT
        
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return MANUAL_BALANCE_USER_ID


async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add balance to user"""
    try:
        amount = int(update.message.text)
        user_id = context.user_data.get('manual_balance_user_id')
        
        await update_user_balance(user_id, amount)
        
        new_balance = await get_user_balance(user_id)
        
        # Notify user
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ تم إضافة رصيد لحسابك!\n\n💰 المبلغ المضاف: {amount} ل.س\n💳 رصيدك الجديد: {new_balance} ل.س"
        )
        
        await update.message.reply_text(
            f"✅ تم إضافة الرصيد بنجاح!\n\n💰 المبلغ: {amount} ل.س\n💳 الرصيد الجديد: {new_balance} ل.س",
            reply_markup=get_main_menu_keyboard(ADMIN_ID)
        )
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح!")
        return MANUAL_BALANCE_AMOUNT


# ==================== ADMIN - STATS ====================

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin statistics"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    users_count = await db.users.count_documents({})
    accounts_count = await db.accounts.count_documents({"sold": False})
    sold_count = await db.accounts.count_documents({"sold": True})
    pending_recharges = await db.recharge_requests.count_documents({"status": "pending"})
    
    text = f"""
📊 إحصائيات البوت

👥 عدد المستخدمين: {users_count}
📦 الحسابات المتاحة: {accounts_count}
✅ الحسابات المباعة: {sold_count}
⏳ طلبات الشحن المعلقة: {pending_recharges}
"""
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ==================== CANCEL HANDLER ====================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    user = update.effective_user
    await update.message.reply_text(
        "❌ تم الإلغاء",
        reply_markup=get_main_menu_keyboard(user.id)
    )
    return ConversationHandler.END


def main():
    """Main function to run the bot"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment!")
        return
    
    if not ADMIN_ID:
        logger.error("ADMIN_TELEGRAM_ID not found in environment!")
        return
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Initialize default products on startup
    async def post_init(application):
        await init_default_products()
    
    application.post_init = post_init
    
    # Syriatel conversation handler
    syriatel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(syriatel_confirm, pattern="^syriatel_confirm$")],
        states={
            SYRIATEL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, syriatel_amount_received)],
            SYRIATEL_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, syriatel_code_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Sham cash conversation handler
    sham_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(sham_start, pattern="^recharge_sham$")],
        states={
            SHAM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sham_amount_received)],
            SHAM_PROOF: [MessageHandler(filters.PHOTO, sham_proof_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # CWallet conversation handler
    cwallet_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cwallet_start, pattern="^recharge_cwallet$")],
        states={
            CWALLET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cwallet_amount_received)],
            CWALLET_PROOF: [MessageHandler(filters.PHOTO, cwallet_proof_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # CoinEx conversation handler
    coinex_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(coinex_start, pattern="^recharge_coinex$")],
        states={
            COINEX_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, coinex_amount_received)],
            COINEX_PROOF: [MessageHandler(filters.PHOTO, coinex_proof_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Buy conversation handler
    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_buy, pattern="^buy_")],
        states={
            BUY_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_buy)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Admin broadcast conversation handler
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Admin add accounts conversation handler
    add_accounts_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_select_category, pattern="^admin_acc_cat_")],
        states={
            ADD_ACCOUNT_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_account_data)],
            ADD_ACCOUNT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_account_price)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Admin add product conversation handler
    add_product_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_product_start, pattern="^admin_add_product$")],
        states={
            ADD_PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_product_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Admin manual balance conversation handler
    manual_balance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_manual_balance_start, pattern="^admin_manual_balance$")],
        states={
            MANUAL_BALANCE_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_user_id)],
            MANUAL_BALANCE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_balance)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Edit exchange rate conversation handler
    edit_exchange_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_exchange_rate_start, pattern="^edit_exchange_rate$")],
        states={
            EDIT_EXCHANGE_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_exchange_rate_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Edit product price conversation handler
    edit_price_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_product_price_select, pattern="^edit_price_")],
        states={
            EDIT_PRODUCT_PRICE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_product_price_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    
    # Add conversation handlers
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
    
    # Add callback query handlers
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
    
    # Run the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
