import sqlite3
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, LinkPreviewOptions
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# فعال‌سازی سیستم لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 🔴 توکن اختصاصی خودت را این‌جا بگذار
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# تنظیمات پروکسی برای عبور از فیلترینگ ایران
PROXY_URL = "http://127.0.0.1:10809" 

def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    # جدول کاربران
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            twitter_id TEXT,
            last_tweet_link TEXT
        )
    ''')
    # جدول بدهی‌ها و تراکنش‌های کلی
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            debtor_id INTEGER,
            creditor_id INTEGER,
            action_type TEXT,
            status TEXT DEFAULT 'pending'
        )
    ''')
    # جدول جدید برای بررسی اینکه هر کاربر روی کدام پیام چه دکمه‌ای زده است
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            user_id INTEGER,
            action_type TEXT,
            UNIQUE(message_id, user_id, action_type)
        )
    ''')
    conn.commit()
    conn.close()

# 🔥 متد جدید و استاندارد برای فعال‌سازی منو به محض روشن شدن ربات
async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "راه‌اندازی اولیه ربات"),
        BotCommand("register", "ثبت یا ویرایش آیدی توییتر (X)")
    ]
    await application.bot.set_my_commands(commands)
    print("✅ منوی دستورات ربات با موفقیت فعال شد.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"سلام {user.first_name} عزیز! به ربات Xengage خوش آمدی.\n\n"
        "برای اینکه بتوانی در گروه حمایت شرکت کنی، باید آیدی توییتر خودت را ثبت کنی.\n"
        "لطفاً دستور /register را بزن یا آیدی توییترت را بدون @ ارسال کن."
    )
    await update.message.reply_text(welcome_text)

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفاً آیدی توییتر (X) خودت را بدون علامت @ ارسال کن:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    telegram_username = update.effective_user.username
    chat_type = update.effective_chat.type

    # ۱. پردازش پیام‌ها در گروه (شکار لینک‌ها)
    if chat_type in ["group", "supergroup"]:
        if "twitter.com" in text.lower() or "x.com" in text.lower():
            url_match = re.search(r'(https?://[^\s]+)', text)
            if not url_match:
                return
            tweet_link = url_match.group(0)

            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT twitter_id FROM users WHERE user_id = ?', (user_id,))
            user_data = cursor.fetchone()

            if not user_data:
                await update.message.delete()
                user_mention = f"@{telegram_username}" if telegram_username else update.effective_user.first_name
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ کاربر {user_mention}، لینک شما حذف شد!\nبرای فعالیت در گروه، ابتدا باید وارد پی‌وی ربات (@XengageRobot) شده و آیدی توییتر خود را ثبت کنید."
                )
                conn.close()
                return

            twitter_handle = user_data[0]
            cursor.execute('UPDATE users SET last_tweet_link = ? WHERE user_id = ?', (tweet_link, user_id))
            conn.commit()
            conn.close()

            # حذف پیام اصلی کاربر حاوی لینک پیش‌نمایش دار
            await update.message.delete()

            # ساخت دکمه‌های شیشه‌ای اولیه
            keyboard = [
                [
                    InlineKeyboardButton("👥 Follow", callback_data=f"follow_{user_id}"),
                    InlineKeyboardButton("❤️ Like", callback_data=f"like_{user_id}"),
                    InlineKeyboardButton("🔁 Retweet", callback_data=f"rt_{user_id}"),
                    InlineKeyboardButton("💬 Comment", callback_data=f"comment_{user_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            group_post_text = (
                f"🚀 **New Support Request!**\n\n"
                f"👤 **User:** @{telegram_username}\n"
                f"🐦 **X (Twitter):** @{twitter_handle}\n\n"
                f"🔗 **Link:** {tweet_link}\n\n"
                f"👇 Please support and click the buttons below:"
            )
            
            # حذف پیش‌نمایش بزرگ توییتر
            preview_options = LinkPreviewOptions(is_disabled=True)

            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=group_post_text, 
                reply_markup=reply_markup, 
                parse_mode="Markdown",
                link_preview_options=preview_options
            )
            return

    # ۲. پردازش ثبت‌نام در پی‌وی (PV)
    if chat_type == "private":
        twitter_id = text[1:] if text.startswith('@') else text

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, twitter_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET twitter_id = excluded.twitter_id, username = excluded.username
        ''', (user_id, telegram_username, twitter_id))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ موفقیت‌آمیز بود!\nآیدی توییتر شما با موفقیت ثبت شد: @{twitter_id}")

# پردازش کلیک روی دکمه‌ها
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    clicker_id = query.from_user.id
    clicker_username = query.from_user.username
    message_id = query.message.message_id
    
    data_parts = query.data.split('_')
    action = data_parts[0]
    creator_id = int(data_parts[1])

    if clicker_id == creator_id:
        await query.answer("❌ شما نمی‌توانید پست خودتان را حمایت کنید!", show_alert=True)
        return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute('SELECT twitter_id, last_tweet_link FROM users WHERE user_id = ?', (clicker_id,))
    clicker_data = cursor.fetchone()

    if not clicker_data:
        await query.answer("❌ ابتدا باید در پی‌وی ربات آیدی توییتر خود را ثبت کنید!", show_alert=True)
        conn.close()
        return

    clicker_twitter = clicker_data[0]
    clicker_last_link = clicker_data[1] if clicker_data[1] else "لینکی ثبت نشده است"

    cursor.execute('SELECT id FROM actions WHERE message_id = ? AND user_id = ? AND action_type = ?', (message_id, clicker_id, action))
    already_done = cursor.fetchone()

    if already_done:
        await query.answer("⚠️ شما قبلاً این حمایت را انجام داده‌اید و ثبت شده است!", show_alert=True)
        conn.close()
        return

    cursor.execute('INSERT INTO actions (message_id, user_id, action_type) VALUES (?, ?, ?)', (message_id, clicker_id, action))
    cursor.execute('INSERT INTO debts (debtor_id, creditor_id, action_type) VALUES (?, ?, ?)', (creator_id, clicker_id, action))
    conn.commit()

    cursor.execute('SELECT COUNT(id) FROM actions WHERE message_id = ? AND action_type = ?', (message_id, action))
    action_count = cursor.fetchone()[0]
    conn.close()

    action_fa = {"follow": "فالو", "like": "لایک", "rt": "ریتوییت", "comment": "کامنت"}[action]
    await query.answer(f"✅ {action_fa} شما با موفقیت ثبت شد.")

    current_keyboard = query.message.reply_markup.inline_keyboard
    new_keyboard = []
    
    for row in current_keyboard:
        new_row = []
        for button in row:
            if button.callback_data == query.data:
                label_en = {"follow": "Followed ✅", "like": "Liked ❤️ ✅", "rt": "Retweeted 🔁 ✅", "comment": "Commented 💬 ✅"}[action]
                new_text = f"{label_en} ({action_count})"
                new_row.append(InlineKeyboardButton(new_text, callback_data=button.callback_data))
            else:
                new_row.append(button)
        new_keyboard.append(new_row)

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))

    alert_text = (
        f"📣 حمایت جدید دریافت شد!\n\n"
        f"👤 کاربر @{clicker_username} (آیدی توییتر: @{clicker_twitter}) پست شما را [{action_fa}] کرد.\n\n"
        f"تعهد شما: حالا نوبت شماست که او را حمایت کنید!\n"
        f"🔗 آخرین لینک این کاربر: {clicker_last_link}"
    )
    
    try:
        await context.bot.send_message(chat_id=creator_id, text=alert_text)
    except Exception as e:
        logging.error(f"Could not send notification to {creator_id}: {e}")

def main():
    init_db()
    
    # استفاده از post_init برای راه‌اندازی امن منو بدون تداخل با لوپ پایتون
    application = (
        Application.builder()
        .token(TOKEN)
        .proxy(PROXY_URL)
        .get_updates_proxy(PROXY_URL)
        .post_init(post_init)
        .build()
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_buttons))
    
    print("ربات Xengage با موفقیت روی پایتون جدید راه‌اندازی شد...")
    application.run_polling()

if __name__ == '__main__':
    main()
