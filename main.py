# main.py - Power Point Break Bot - Final Fixed Implementation with Search & Stock Alert

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, 
    filters, ConversationHandler, ContextTypes
)
import json
import uuid
import re
import datetime
import os 
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

# Import configuration settings
try:
    from config import BOT_TOKEN, ADMIN_ID, PAYMENT_NUMBER, ADMIN_USERNAME
except ImportError:
    print("FATAL ERROR: config.py not found or incomplete. Exiting.")
    exit()

# --- Conversation States ---
CATEGORY_NAME, CATEGORY_BANNER = range(2)
PRODUCT_CATEGORY, PRODUCT_NAME, PRODUCT_DURATION, PRODUCT_PRICE, PRODUCT_COUNTRY, PRODUCT_RULES, PRODUCT_PHOTO = range(2, 9) 
STOCK_INPUT, STOCK_SELECT_PRODUCT = range(9, 11)
SEARCH_INPUT = 11 # STATE FOR ADMIN SEARCH

# --- Stock Threshold Setting ---
LOW_STOCK_THRESHOLD = 5 # 5টি আইটেমের নিচে নামলে অ্যালার্ট যাবে

# --- Core Utility Functions (Database & Logging) ---

def load_db():
    """Loads data from database.json."""
    try:
        with open('database.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "categories": {}, "products": {}, "stock": {}, "orders": {}, "logs": [], "next_order_id": 100}

def save_db(db):
    """Saves data back to database.json."""
    with open('database.json', 'w') as f:
        json.dump(db, f, indent=2)

def log_activity(db, action):
    """Saves an entry to the activity log."""
    db['logs'].insert(0, f"[{datetime.datetime.now().strftime('%H:%M %d %b')}] {action}")
    if len(db['logs']) > 50:
        db['logs'] = db['logs'][:50]

def is_admin(user_id):
    """Checks if the user ID matches the defined Admin ID."""
    return str(user_id) == str(ADMIN_ID)

# --- KEYBOARD DEFINITIONS (Included here for start_command function) ---

MAIN_MENU_KEYBOARD = [
    [KeyboardButton("🛒 Buy Subscription"), KeyboardButton("📦 My Orders")],
    [KeyboardButton("🆘 Support"), KeyboardButton("🎁 Offers")],
    [KeyboardButton("👤 Profile")]
]

def get_admin_menu_keyboard():
    """Returns the main Admin Panel Inline Keyboard."""
    keyboard = [
        [InlineKeyboardButton("📁 Category Manager", callback_data="ADMIN_MANAGER_CATEGORY"), 
         InlineKeyboardButton("📦 Product Manager (WIP)", callback_data="ADMIN_MANAGER_PRODUCT_DUMMY")],
        [InlineKeyboardButton("📦 Stock Manager", callback_data="ADMIN_MANAGER_STOCK")],
        [InlineKeyboardButton("🧾 Pending Orders", callback_data="ADMIN_ORDERS_PENDING"),
         InlineKeyboardButton("🔍 Search Order/User", callback_data="ADMIN_SEARCH_START")],
        [InlineKeyboardButton("📊 Stats", callback_data="ADMIN_STATS"), 
         InlineKeyboardButton("📜 Activity Logs", callback_data="ADMIN_LOGS")],
        [InlineKeyboardButton("🔔 Notify Pending Users", callback_data="ADMIN_NOTIFY")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- I. USER SIDE FUNCTIONS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command. (FIXED: Shows Admin Panel if admin)."""
    user = update.effective_user
    db = load_db()
    
    # 1. ADMIN CHECK: If user is the admin, show the admin panel immediately.
    if is_admin(user.id):
        await update.message.reply_text(
            "👑 **POWER POINT BREAK — ADMIN PANEL**\n\nPlease choose an option:",
            reply_markup=get_admin_menu_keyboard(),
            parse_mode='Markdown'
        )
        return

    # 2. USER FLOW: If not admin, proceed with user initialization and main menu.
    user_id_str = str(user.id)
    if user_id_str not in db['users']:
        db['users'][user_id_str] = {
            "username": user.username or f"id_{user.id}",
            "name": user.full_name,
            "total_spent": 0,
            "total_orders": 0,
            "completed_orders": 0,
            "pending_orders": 0,
            "rejected_orders": 0,
            "first_order": datetime.datetime.now().isoformat(),
            "last_order": None,
            "level": "NEW"
        }
        save_db(db)
    
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
    
    await update.message.reply_text(
        f"👋 Welcome to **Power Point Break — PREMIUM SUBSCRIPTION STORE!**\n\nPlease choose an option 👇",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles clicks on the main menu Reply Keyboard buttons."""
    text = update.message.text
    
    if text == "🛒 Buy Subscription":
        await show_categories(update, context) 
    elif text == "📦 My Orders":
        await show_user_orders(update, context)
    elif text == "🆘 Support":
        await show_support(update, context)
    elif text == "🎁 Offers":
        await show_offers(update, context)
    elif text == "👤 Profile":
        await show_profile(update, context)

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the list of product categories (Fixed Message/Query handling)."""
    db = load_db()
    keyboard = []
    
    if not db['categories']:
        await update.effective_message.reply_text("📂 No categories available right now. Please check back later.")
        return

    for cat_id, cat_data in db['categories'].items():
        keyboard.append([InlineKeyboardButton(cat_data['name'], callback_data=f"CAT_ID_{cat_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "📂 **Select Category**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "📂 **Select Category**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the list of products in a selected category."""
    query = update.callback_query
    await query.answer()
    
    cat_id = query.data.split('_')[-1] 
    db = load_db()
    
    keyboard = []
    product_list_text = "📦 **Available Products:**\n\n"
    products_found = False
    
    for prod_id, prod_data in db['products'].items():
        if prod_data['cat_id'] == cat_id:
            products_found = True
            product_list_text += f"• {prod_data['name']} – {prod_data['duration']} – {prod_data['price']}৳\n"
            keyboard.append([InlineKeyboardButton(f"{prod_data['name']} ({prod_data['price']}৳)", callback_data=f"PROD_ID_{prod_id}")])

    if not products_found:
        product_list_text += "*No products available in this category.*"

    keyboard.append([InlineKeyboardButton("⬅ Back to Categories", callback_data="BACK_CATEGORIES")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        product_list_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_product_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the details of a selected product."""
    query = update.callback_query
    await query.answer()
    
    prod_id = query.data.split('_')[-1]
    db = load_db()
    product = db['products'].get(prod_id)
    
    if not product:
        await query.edit_message_text("Product not found.")
        return

    context.user_data['current_product_id'] = prod_id

    summary = (
        "🧾 **ORDER SUMMARY**\n\n"
        f"Product: **{product['name']}**\n"
        f"Duration: **{product['duration']}**\n"
        f"Country: **{product['country']}**\n"
        f"Price: **{product['price']}৳**\n\n"
        "📜 **Rules:**\n"
        f"{product['rules']}\n\n"
    )

    keyboard = [
        [InlineKeyboardButton("🛒 Buy Now", callback_data="BUY_NOW")],
        [InlineKeyboardButton("⬅ Back", callback_data=f"BACK_TO_PRODUCTS_{product['cat_id']}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(summary, reply_markup=reply_markup, parse_mode='Markdown')

async def buy_now_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates the order and payment process."""
    query = update.callback_query
    await query.answer()

    prod_id = context.user_data.get('current_product_id')
    user_id = update.effective_user.id
    db = load_db()

    if not prod_id or prod_id not in db['products']:
        await query.edit_message_text("Error: Product selection failed. Please start again from the menu.")
        return

    product = db['products'][prod_id]
    
    order_id_num = db['next_order_id']
    order_id = f"order_{order_id_num}"
    db['next_order_id'] += 1

    db['orders'][order_id] = {
        "user_id": user_id,
        "product_id": prod_id,
        "price": product['price'],
        "status": "waiting_payment",
        "created_at": datetime.datetime.now().isoformat()
    }
    log_activity(db, f"ORDER CREATED — {order_id}")
    save_db(db)

    context.user_data['waiting_payment_for_order'] = order_id
    
    payment_info = (
        f"🧾 **ORDER ID: {order_id}**\n\n"
        f"Product: **{product['name']}**\n"
        f"Price: **{product['price']}৳**\n\n"
        "📤 **Submit payment as:**\n"
        "`TXNID|SENDER_NUMBER|AMOUNT`\n\n"
        f"**Send money to:**\n"
        f"`{PAYMENT_NUMBER}`\n\n"
        "**Please reply to this message with the payment format above after sending money.**"
    )
    
    await query.edit_message_text(payment_info, parse_mode='Markdown')

async def handle_payment_submission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the user's payment submission message (TXNID|NUMBER|AMOUNT)."""
    user = update.effective_user
    message_text = update.message.text.strip()
    order_id = context.user_data.get('waiting_payment_for_order')

    if not order_id: return

    parts = message_text.split('|')
    if len(parts) != 3:
        await update.message.reply_text("❌ **Invalid format.** Please submit payment as: `TXNID|SENDER_NUMBER|AMOUNT` (e.g., `TXN99882|01755667788|250`)")
        return

    txn_id, sender_number, amount_str = parts
    txn_id = txn_id.upper()
    
    db = load_db()
    order = db['orders'].get(order_id)
    
    if not order:
        await update.message.reply_text("Error finding your order. Please contact support.")
        del context.user_data['waiting_payment_for_order']
        return

    try:
        amount = int(amount_str)
    except ValueError:
        await update.message.reply_text("❌ **Amount must be a number.**")
        return

    if amount != order['price']:
         await update.message.reply_text(f"❌ **Amount mismatch.** You submitted {amount}৳ but the required price is {order['price']}৳.")
         return

    order['status'] = "pending_approval"
    order['txn_id'] = txn_id
    order['sender_number'] = sender_number
    order['submitted_amount'] = amount
    log_activity(db, f"PAYMENT SUBMITTED — {order_id}")
    save_db(db)

    del context.user_data['waiting_payment_for_order']

    await update.message.reply_text(
        "✅ **Payment submitted!**\n"
        f"Your order `{order_id}` is now **pending approval**."
    )

    # Admin Notification
    product_name = db['products'][order['product_id']]['name']
    admin_message = (
        f"🔔 **ACTION REQUIRED: NEW PENDING ORDER**\n\n"
        f"**Order ID:** `{order_id}`\n"
        f"**Product:** {product_name}\n"
        f"**User:** @{user.username or user.full_name} (ID: {user.id})\n"
        f"**Price:** {order['price']}৳\n\n"
        f"**Submitted TXN:** `{txn_id}`\n"
        f"**Sender:** `{sender_number}`\n"
        f"**Amount:** {amount}৳"
    )

    admin_keyboard = [
        [InlineKeyboardButton("✔ Approve", callback_data=f"ADMIN_APPROVE_{order_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"ADMIN_REJECT_{order_id}")]
    ]
    
    await context.bot.send_message(
        ADMIN_ID,
        admin_message,
        reply_markup=InlineKeyboardMarkup(admin_keyboard),
        parse_mode='Markdown'
    )

async def show_user_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's order history."""
    user_id = update.effective_user.id
    db = load_db()
    
    user_orders = {k: v for k, v in db['orders'].items() if v['user_id'] == user_id}
    
    if not user_orders:
        await update.effective_message.reply_text("📦 **YOUR ORDERS**\n\nYou have no orders yet.")
        return

    order_list_text = "📦 **YOUR ORDERS**\n\n"
    
    for order_id, order in user_orders.items():
        status_display = order['status'].upper()
        order_list_text += f"`{order_id}` — **{status_display}**\n"

    await update.effective_message.reply_text(order_list_text, parse_mode='Markdown')

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays support information."""
    await update.effective_message.reply_text(
        "🆘 **SUPPORT CENTER**\n\n"
        f"For help contact: **{ADMIN_USERNAME}**\n\n"
        "Send:\n• Your Order ID\n• Problem details\n• Screenshot (optional)",
        parse_mode='Markdown'
    )

async def show_offers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays current offers."""
    await update.effective_message.reply_text("🎁 **OFFERS**\n\nCurrently no offers available.")

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays user profile information."""
    user = update.effective_user
    db = load_db()
    user_data = db['users'].get(str(user.id), {})

    user_orders = [o for o in db['orders'].values() if o['user_id'] == user.id]
    completed = sum(1 for o in user_orders if o['status'] == 'delivered')
    pending = sum(1 for o in user_orders if o['status'] == 'pending_approval' or o['status'] == 'waiting_payment')
    rejected = sum(1 for o in user_orders if o['status'] == 'rejected')
    total_orders = len(user_orders)
        
    first_order_date = user_data.get('first_order', 'N/A')
    try:
        first_order_date = datetime.datetime.fromisoformat(first_order_date).strftime('%d %b %Y')
    except:
        pass
        
    profile_text = (
        "👤 **YOUR PROFILE**\n\n"
        f"🆔 **User ID:** `{user.id}`\n"
        f"👤 **Username:** @{user.username or 'N/A'}\n"
        f"📛 **Name:** {user.full_name}\n\n"
        f"📦 **Total Orders:** {total_orders}\n"
        f"✅ **Completed:** {completed}\n"
        f"⌛ **Pending:** {pending}\n"
        f"❌ **Rejected:** {rejected}\n\n"
        f"💰 **Total Spent:** {user_data.get('total_spent', 0)}৳\n"
        f"🧾 **First Order:** {first_order_date}\n"
        f"⭐ **Customer Level:** {user_data.get('level', 'NEW')}"
    )
    await update.effective_message.reply_text(profile_text, parse_mode='Markdown')

# --- II. ADMIN SIDE FUNCTIONS ---

async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the Admin Panel if the user is the Admin."""
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "👑 **POWER POINT BREAK — ADMIN PANEL**\n\nPlease choose an option:",
        reply_markup=get_admin_menu_keyboard(),
        parse_mode='Markdown'
    )

async def back_to_admin_panel(query, context: ContextTypes.DEFAULT_TYPE):
    """Callback to return to the main admin menu."""
    await query.edit_message_text(
        "👑 **POWER POINT BREAK — ADMIN PANEL**\n\nPlease choose an option:", 
        reply_markup=get_admin_menu_keyboard(), 
        parse_mode='Markdown'
    )

async def handle_admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles main Admin Panel button clicks (routes to specific managers)."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id): return

    action = query.data

    if action == "ADMIN_MANAGER_CATEGORY":
        await show_category_manager(query, context)
    elif action == "ADMIN_MANAGER_STOCK":
        await show_stock_manager(query, context)
    elif action == "ADMIN_ORDERS_PENDING":
        await show_pending_orders(query, context)
    elif action == "ADMIN_STATS":
        await show_stats(query, context)
    elif action == "ADMIN_LOGS":
        await show_logs(query, context)
    elif action == "ADMIN_NOTIFY":
        await notify_pending_users(query, context)
    elif action.endswith("DUMMY"):
        await query.edit_message_text("This feature is currently under construction.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="ADMIN_PANEL_BACK")]]))
    elif action == "ADMIN_SEARCH_START":
        await start_admin_search(query, context) # Route to new search entry point


# --- II.A. Category Management ---

def get_category_manager_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Category", callback_data="ADMIN_CAT_ADD")],
        [InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="ADMIN_PANEL_BACK")]
    ])

async def show_category_manager(query, context: ContextTypes.DEFAULT_TYPE):
    await query.edit_message_text("🟣 **CATEGORY MANAGER**", reply_markup=get_category_manager_keyboard(), parse_mode='Markdown')

async def start_add_category(query, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for ConversationHandler: start adding a category."""
    await query.answer()
    await query.edit_message_text("Send category name:")
    return CATEGORY_NAME

async def get_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: Get category name."""
    context.user_data['new_category_name'] = update.message.text
    await update.message.reply_text("Send banner URL (optional):")
    return CATEGORY_BANNER

async def finish_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: Get banner URL and save to DB."""
    db = load_db()
    cat_name = context.user_data.pop('new_category_name')
    banner = update.message.text if update.message.text else "N/A"
    
    new_cat_id = f"cat_{uuid.uuid4().hex[:4]}"
    db['categories'][new_cat_id] = {"name": cat_name, "banner": banner}
    log_activity(db, f"CATEGORY ADDED — {cat_name}")
    save_db(db)
    
    await update.message.reply_text(f"✅ Category **{cat_name}** added successfully!", parse_mode='Markdown', reply_markup=get_admin_menu_keyboard())
    return ConversationHandler.END

# --- II.B. Stock Management ---

async def show_stock_manager(query, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    
    total_available = sum(len([item for item in stock_list if not item['used']]) for stock_list in db['stock'].values())
    total_used = sum(len([item for item in stock_list if item['used']]) for stock_list in db['stock'].values())
    total_stock = total_available + total_used
    
    summary = (
        "🟢 **STOCK MANAGER**\n\n"
        f"Available: **{total_available}**\n"
        f"Used: **{total_used}**\n"
        f"Total: **{total_stock}**"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Stock", callback_data="ADMIN_STOCK_START_ADD")],
        [InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="ADMIN_PANEL_BACK")]
    ]
    await query.edit_message_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def start_add_stock(query, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for ConversationHandler: Select product for stock."""
    await query.answer()
    db = load_db()
    
    keyboard = []
    if not db['products']:
        await query.edit_message_text("No products defined. Add a product first.", reply_markup=get_admin_menu_keyboard())
        return ConversationHandler.END

    for prod_id, prod_data in db['products'].items():
        keyboard.append([InlineKeyboardButton(prod_data['name'], callback_data=f"STOCK_ADD_PROD_{prod_id}")])

    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="ADMIN_CANCEL_STOCK")])
    
    await query.edit_message_text("Select Product to add stock for:", reply_markup=InlineKeyboardMarkup(keyboard))
    return STOCK_SELECT_PRODUCT

async def get_stock_product_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1.5: Get the product ID from inline button click (Handles the Callback)."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "ADMIN_CANCEL_STOCK":
        await query.edit_message_text("❌ Stock addition cancelled.", reply_markup=get_admin_menu_keyboard())
        return ConversationHandler.END
        
    prod_id = query.data.split('_')[-1]
    db = load_db()
    
    context.user_data['stock_product_id'] = prod_id
    
    await query.edit_message_text(
        f"Adding stock for **{db['products'][prod_id]['name']}**\n\n"
        "Send stock credentials, one per line:\n"
        "`email1|pass1`\n"
        "`email2|pass2`\n"
        "`email3|pass3`",
        parse_mode='Markdown'
    )
    return STOCK_INPUT 

async def get_stock_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: Get stock input and save to DB."""
    db = load_db()
    prod_id = context.user_data.pop('stock_product_id', None)
    
    if not prod_id:
        await update.message.reply_text("Error: Product ID lost. Please restart stock addition.", reply_markup=get_admin_menu_keyboard())
        return ConversationHandler.END
        
    stock_lines = update.message.text.split('\n')
    
    added_count = 0
    
    if prod_id not in db['stock']:
        db['stock'][prod_id] = []
        
    for line in stock_lines:
        line = line.strip()
        if re.match(r'.+\|.+', line): 
            db['stock'][prod_id].append({"credential": line, "used": False})
            added_count += 1
            
    log_activity(db, f"STOCK ADDED — {added_count} items ({db['products'][prod_id]['name']})")
    save_db(db)
    
    await update.message.reply_text(
        f"✅ Added **{added_count}** stock items for **{db['products'][prod_id]['name']}**.",
        parse_mode='Markdown',
        reply_markup=get_admin_menu_keyboard()
    )
    return ConversationHandler.END

async def cancel_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler to cancel any admin Conversation."""
    if update.callback_query:
        await update.callback_query.edit_message_text("❌ Action cancelled.", reply_markup=get_admin_menu_keyboard())
        await update.callback_query.answer()
    else:
        await update.message.reply_text("❌ Action cancelled.", reply_markup=get_admin_menu_keyboard())
        
    context.user_data.clear() 
    return ConversationHandler.END

# --- II.C. Order Management (Pending Orders) ---

async def get_pending_orders_list(db):
    """Helper to retrieve and sort pending orders."""
    pending = [k for k, v in db['orders'].items() if v['status'] == 'pending_approval']
    return pending

async def show_pending_orders(query, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    pending_orders = await get_pending_orders_list(db)
    
    if not pending_orders:
        await query.edit_message_text("🧾 **Pending Orders**\n\nNo orders are currently pending approval.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="ADMIN_PANEL_BACK")]]))
        return
    
    order_id = pending_orders[0]
    await display_single_order_details(query, context, order_id, pending_orders)

async def handle_order_view_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles navigation between pending orders."""
    query = update.callback_query
    await query.answer()
    order_id = query.data.split('_')[-1]
    db = load_db()
    pending_orders = await get_pending_orders_list(db)
    await display_single_order_details(query, context, order_id, pending_orders)

async def display_single_order_details(query, context: ContextTypes.DEFAULT_TYPE, order_id, pending_orders):
    """Formats and displays a single pending order."""
    db = load_db()
    order = db['orders'].get(order_id)
    if not order or order['product_id'] not in db['products']:
        await query.edit_message_text("Error: Order or Product details missing.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="ADMIN_PANEL_BACK")]]))
        return
        
    product = db['products'][order['product_id']]
    user_info = db['users'].get(str(order['user_id']), {'username': 'N/A', 'name': 'N/A'})
    
    try:
        current_index = pending_orders.index(order_id) + 1
    except ValueError:
        current_index = "N/A"
        
    order_details = (
        f"**ORDER {order_id}** ({current_index} of {len(pending_orders)} pending)\n\n"
        f"User: @{user_info['username']} ({user_info['name']})\n"
        f"Product: {product['name']}\n"
        f"Price: {order['price']}৳\n\n"
        f"TXN: `{order.get('txn_id', 'N/A')}`\n"
        f"Sender: `{order.get('sender_number', 'N/A')}`\n"
        f"Amount: {order.get('submitted_amount', 0)}৳\n\n"
        f"Status: **{order['status'].upper()}**"
    )

    keyboard = [
        [InlineKeyboardButton("✔ Approve", callback_data=f"ADMIN_APPROVE_{order_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"ADMIN_REJECT_{order_id}")]
    ]
    
    try:
        order_index = pending_orders.index(order_id)
        nav_buttons = []
        if order_index > 0:
            nav_buttons.append(InlineKeyboardButton("« Prev", callback_data=f"ADMIN_ORDER_VIEW_{pending_orders[order_index-1]}"))
        if order_index < len(pending_orders) - 1:
            nav_buttons.append(InlineKeyboardButton("Next »", callback_data=f"ADMIN_ORDER_VIEW_{pending_orders[order_index+1]}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
    except:
        pass
        
    keyboard.append([InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="ADMIN_PANEL_BACK")])

    await query.edit_message_text(order_details, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_admin_order_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles Approve/Reject action on a pending order."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id): return

    action, order_id = query.data.split('_')[1], query.data.split('_')[2]
    db = load_db()
    order = db['orders'].get(order_id)
    
    if not order or order['status'] != 'pending_approval':
        await query.edit_message_text(f"Order {order_id} is no longer pending or doesn't exist.")
        return

    # --- APPROVE Logic (Auto-Delivery) ---
    if action == "APPROVE":
        prod_id = order['product_id']
        stock_list = db['stock'].get(prod_id, [])
        credential = None
        stock_index = -1
        
        for i, item in enumerate(stock_list):
            if not item['used']:
                credential = item['credential']
                stock_index = i
                break
        
        if credential:
            stock_list[stock_index]['used'] = True
            order['status'] = "delivered"
            order['delivery_credential'] = credential
            
            user_data = db['users'].get(str(order['user_id']))
            if user_data:
                user_data['completed_orders'] = user_data.get('completed_orders', 0) + 1
                user_data['total_spent'] = user_data.get('total_spent', 0) + order['price']
            
            log_activity(db, f"ORDER APPROVED — {order_id}")
            save_db(db)
            
            # Notify User
            username, password = credential.split('|')
            user_message = (
                f"🎉 **Your order {order_id} has been delivered!**\n\n"
                f"📧 **Username:** `{username}`\n"
                f"🔑 **Password:** `{password}`\n\n"
                f"Need help? Contact **{ADMIN_USERNAME}**"
            )
            await context.bot.send_message(order['user_id'], user_message, parse_mode='Markdown')
            
            await query.edit_message_text(f"✔ **Order approved & delivered.**\nDelivery: `{credential}`")
        else:
            await query.edit_message_text(f"❌ **ERROR:** No stock available for Product {db['products'][prod_id]['name']}. Please add stock first.")
            
    # --- REJECT Logic ---
    elif action == "REJECT":
        order['status'] = "rejected"
        user_data = db['users'].get(str(order['user_id']))
        if user_data:
            user_data['rejected_orders'] = user_data.get('rejected_orders', 0) + 1
        
        log_activity(db, f"ORDER REJECTED — {order_id}")
        save_db(db)
        
        await context.bot.send_message(order['user_id'], f"❌ **Your order {order_id} has been rejected.** Please contact support if you believe this is an error.")
        
        await query.edit_message_text(f"❌ **Order rejected.**")

# --- II.D. Analytics & Notifications ---

async def show_stats(query, context: ContextTypes.DEFAULT_TYPE):
    """Displays bot statistics."""
    db = load_db()
    
    total_users = len(db['users'])
    total_orders = len(db['orders'])
    
    completed = sum(1 for o in db['orders'].values() if o['status'] == 'delivered')
    pending_approval = sum(1 for o in db['orders'].values() if o['status'] == 'pending_approval')
    rejected = sum(1 for o in db['orders'].values() if o['status'] == 'rejected')
    
    categories = len(db['categories'])
    products = len(db['products'])
    stock_available = sum(len([item for item in stock_list if not item['used']]) for stock_list in db['stock'].values())
    
    stats_text = (
        "📊 **BOT STATISTICS**\n\n"
        f"👥 **Total Users:** {total_users}\n"
        f"📦 **Total Orders:** {total_orders}\n"
        f"⌛ Pending Approval: {pending_approval}\n"
        f"✔ Completed: {completed}\n"
        f"❌ Rejected: {rejected}\n\n"
        f"📁 **Categories:** {categories}\n"
        f"📦 **Products:** {products}\n"
        f"🔑 **Stock Available:** {stock_available}"
    )

    await query.edit_message_text(stats_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="ADMIN_PANEL_BACK")]]))

async def show_logs(query, context: ContextTypes.DEFAULT_TYPE):
    """Displays recent activity logs."""
    db = load_db()
    logs = "\n".join(db['logs'][:20])
    
    log_text = (
        "📜 **ACTIVITY LOGS**\n\n"
        f"{logs if logs else 'No recent activity.'}"
    )
    
    await query.edit_message_text(log_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="ADMIN_PANEL_BACK")]]))

async def notify_pending_users(query, context: ContextTypes.DEFAULT_TYPE):
    """Sends a reminder to all users with pending approval orders."""
    db = load_db()
    
    pending_orders = {k:v for k,v in db['orders'].items() if v['status'] == 'pending_approval'}
    pending_user_ids = {o['user_id'] for o in pending_orders.values()}
    
    if not pending_user_ids:
        await query.edit_message_text("No users with pending orders to notify.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="ADMIN_PANEL_BACK")]]))
        return

    count = 0
    for user_id in pending_user_ids:
        try:
            order_id = next(k for k,v in pending_orders.items() if v['user_id'] == user_id)
            
            await context.bot.send_message(
                user_id,
                f"⏰ **ORDER REMINDER**\n\nYour order `{order_id}` is still pending approval.\nAdmin will review soon.",
                parse_mode='Markdown'
            )
            count += 1
        except Exception:
            pass 
    
    log_activity(db, f"NOTIFICATION SENT — {count} users reminded of pending orders")
    save_db(db)

    await query.edit_message_text(f"🔔 **Notification Sent.** Sent reminder to **{count}** users with pending orders.", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Admin Panel", callback_data="ADMIN_PANEL_BACK")]]))


# --- II.E. ADMIN SEARCH FUNCTIONALITY (NEW) ---

async def start_admin_search(query, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for Search Conversation."""
    await query.answer()
    await query.edit_message_text(
        "🔍 **ADMIN SEARCH**\n\n"
        "Enter Order ID (e.g., `order_101`), TXN ID, or User ID to search."
    )
    return SEARCH_INPUT

async def process_admin_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes the search input."""
    search_term = update.message.text.strip()
    db = load_db()
    
    results = []
    
    # Search logic: Order ID, TXN ID, or User ID
    for order_id, order in db['orders'].items():
        match_type = None
        if search_term.lower() == order_id.lower():
            match_type = "Order ID"
        elif order.get('txn_id') and search_term.upper() == order['txn_id'].upper():
            match_type = "TXN ID"
        elif search_term.isdigit() and str(order['user_id']) == search_term:
             match_type = "User ID"
             
        if match_type:
            results.append((order_id, order, match_type))
            if match_type != "User ID":
                break # Stop after finding exact match for single entry items (Order/TXN)

    if not results:
        await update.message.reply_text(f"❌ No orders found matching: `{search_term}`", 
                                        reply_markup=get_admin_menu_keyboard(), 
                                        parse_mode='Markdown')
        return ConversationHandler.END

    response = f"✅ **Search Results for:** `{search_term}`\n\n"
    for order_id, order, match_type in results:
        user_info = db['users'].get(str(order['user_id']), {})
        product_name = db['products'].get(order['product_id'], {}).get('name', 'Unknown Product')
        
        response += (
            f"--- Match by {match_type} ---\n"
            f"ID: **{order_id}**\n"
            f"User: @{user_info.get('username', 'N/A')} (ID: {order['user_id']})\n"
            f"Product: {product_name}\n"
            f"Status: **{order['status'].upper()}**\n"
            f"Price: {order['price']}৳\n"
            f"TXN: `{order.get('txn_id', 'N/A')}`\n\n"
        )
        
    await update.message.reply_text(response, 
                                    reply_markup=get_admin_menu_keyboard(), 
                                    parse_mode='Markdown')
    
    return ConversationHandler.END

# --- II.F. STOCK ALERT FUNCTIONALITY (NEW) ---

async def check_low_stock_alert(context: ContextTypes.DEFAULT_TYPE):
    """Checks stock levels and sends an alert if any product is below threshold."""
    db = load_db()
    low_stock_products = []
    
    for prod_id, stock_list in db['stock'].items():
        available_count = sum(1 for item in stock_list if not item['used'])
        
        if available_count <= LOW_STOCK_THRESHOLD:
            product_name = db['products'].get(prod_id, {}).get('name', 'Unknown Product')
            low_stock_products.append(f"• **{product_name}**: {available_count} items left!")

    if low_stock_products:
        alert_message = (
            "⚠️ **LOW STOCK ALERT!** ⚠️\n\n"
            f"The following products have {LOW_STOCK_THRESHOLD} or fewer items in stock:\n"
            + "\n".join(low_stock_products)
        )
        try:
            await context.bot.send_message(ADMIN_ID, alert_message, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"Failed to send stock alert to admin: {e}")


# --- III. MAIN SETUP ---

def main() -> None:
    """Start the bot and register all handlers."""
    application = Application.builder().token(BOT_TOKEN).build()

    # --- Admin Conversation Handlers ---
    
    cat_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_category, pattern=r'^ADMIN_CAT_ADD$')],
        states={
            CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_category_name)],
            CATEGORY_BANNER: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish_add_category)],
        },
        fallbacks=[CommandHandler("cancel", cancel_admin_action),
                   CallbackQueryHandler(cancel_admin_action, pattern=r'^ADMIN_PANEL_BACK$')], 
        allow_reentry=True,
        per_message=False 
    )
    
    stock_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_stock, pattern=r'^ADMIN_STOCK_START_ADD$')],
        states={
            STOCK_SELECT_PRODUCT: [
                CallbackQueryHandler(get_stock_product_selection_callback, pattern=r'^STOCK_ADD_PROD_')
            ],
            STOCK_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_stock_input)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_admin_action),
                   CallbackQueryHandler(cancel_admin_action, pattern=r'^ADMIN_CANCEL_STOCK$')], 
        allow_reentry=True,
        per_message=False
    )
    
    # NEW: Admin Search Conversation Handler
    search_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda update, context: start_admin_search(update.callback_query, context), pattern=r'^ADMIN_SEARCH_START$')],
        states={
            SEARCH_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_search_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_admin_action)],
        allow_reentry=True,
        per_message=False
    )


    application.add_handler(cat_conv_handler)
    application.add_handler(stock_conv_handler)
    application.add_handler(search_conv_handler) 
    
    # --- USER HANDLERS ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("profile", show_profile))
    application.add_handler(CommandHandler("support", show_support))
    
    # ADMIN ONLY: Panel command
    application.add_handler(CommandHandler("panel", admin_panel_command))
    
    # Handles payment submission 
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_payment_submission, block=False))
    
    # Handles main menu button clicks (ReplyKeyboard)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))
    
    # --- USER CALLBACKS (Buy Flow) ---
    application.add_handler(CallbackQueryHandler(show_categories, pattern=r'^BACK_CATEGORIES$'))
    application.add_handler(CallbackQueryHandler(show_products, pattern=r'^CAT_ID_'))
    application.add_handler(CallbackQueryHandler(show_products, pattern=r'^BACK_TO_PRODUCTS_'))
    application.add_handler(CallbackQueryHandler(show_product_details, pattern=r'^PROD_ID_'))
    application.add_handler(CallbackQueryHandler(buy_now_action, pattern=r'^BUY_NOW$'))
    
    # --- ADMIN CALLBACKS (Panel Navigation & Manager Routes) ---
    application.add_handler(CallbackQueryHandler(back_to_admin_panel, pattern=r'^ADMIN_PANEL_BACK$'))
    application.add_handler(CallbackQueryHandler(handle_admin_menu_callback, pattern=r'^ADMIN_'))
    
    # ADMIN CALLBACKS (Order Actions & Navigation)
    application.add_handler(CallbackQueryHandler(handle_admin_order_action, pattern=r'^ADMIN_(APPROVE|REJECT)_'))
    application.add_handler(CallbackQueryHandler(handle_order_view_navigation, pattern=r'^ADMIN_ORDER_VIEW_')) 
    
    # --- Start Job Scheduler for Stock Alert ---
    job_queue = application.job_queue 
    # Check every 6 hours (6 * 3600 seconds), start after 5 mins
    job_queue.run_repeating(check_low_stock_alert, interval=6 * 3600, first=300) 

    print("Bot is running and listening for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Initialize database.json if it doesn't exist
    if not os.path.exists('database.json'):
        print("Creating initial database.json with dummy data.")
        db = {
            "users": {},
            "categories": {"cat_1": {"name": "ChatGPT & AI", "banner": "N/A"}, "cat_2": {"name": "YouTube Premium", "banner": "N/A"}},
            "products": {"prod_1": {"cat_id": "cat_1", "name": "ChatGPT Plus", "duration": "1 Month", "price": 250, "country": "Turkey", "rules": "• Don't change password\n• No refund after delivery", "photo": "N/A"}},
            "stock": {"prod_1": [{"credential": "user@mail.com|pass123", "used": False}, {"credential": "user4@mail.com|pass456", "used": False}]},
            "orders": {},
            "logs": [],
            "next_order_id": 100
        }
        with open('database.json', 'w') as f:
             json.dump(db, f, indent=2)
        
    main()
