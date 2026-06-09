import sqlite3
import logging
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# فعال‌سازی سیستم لاگ پیشرفته برای دیدن ارورهای احتمالی
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 🔴 توکن اختصاصی خودت را این‌جا بگذار
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# تنظیمات پروکسی برای عبور از فیلترینگ ایران
PROXY_URL = "http://127.0.0.1:10809" 

# متغیر موقت برای ذخیره وضعیت انتخاب دکمه‌ها
PENDING_POSTS = {}

def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            twitter_id TEXT,
            last_tweet_link TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            debtor_id INTEGER,
            creditor_id INTEGER,
            action_type TEXT,
            status TEXT DEFAULT 'pending'
        )
    ''')
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

async def delete_message_delayed(bot, chat_id, message_id, delay_seconds=15):
    await asyncio.sleep(delay_seconds)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass 

async def auto_approve_post_delayed(bot, chat_id, message_id, delay_seconds=15):
    await asyncio.sleep(delay_seconds)
    if message_id in PENDING_POSTS:
        post_data = PENDING_POSTS[message_id]
        if post_data.get("status") == "pending":
            post_data["status"] = "deployed"
            data_to_deploy = PENDING_POSTS.pop(message_id, None)
            if data_to_deploy:
                await deploy_final_post(bot, chat_id, message_id, data_to_deploy, forced_all=True)

# 🔥 تابع با فرمت فوق‌العاده پایدار HTML و چیدمان استاندارد دکمه‌ها
async def deploy_final_post(bot, chat_id, original_msg_id, post_data, forced_all=False):
    creator_id = post_data["creator_id"]
    telegram_username = post_data["username"]
    twitter_handle = post_data["twitter"]
    tweet_link = post_data["tweet_link"]
    options = post_data["options"]

    keyboard_buttons = []
    available_actions = ["follow", "like", "rt", "comment"]
    labels = {"follow": "👥 Follow", "like": "❤️ Like", "rt": "🔁 Retweet", "comment": "💬 Comment"}

    for action in available_actions:
        if forced_all or options[action]:
            keyboard_buttons.append(InlineKeyboardButton(labels[action], callback_data=f"support_{action}_{creator_id}"))
    
    if not keyboard_buttons:
        for action in available_actions:
            keyboard_buttons.append(InlineKeyboardButton(labels[action], callback_data=f"support_{action}_{creator_id}"))

    fixed_keyboard = []
    row = []
    for btn in keyboard_buttons:
        row.append(btn)
        if len(row) == 2:
            fixed_keyboard.append(row)
            row = []
    if row:
        fixed_keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(fixed_keyboard)

    # تغییر فرمت به HTML برای جلوگیری از کراش کاراکترهای خاص
    group_post_text = (
        f"🚀 <b>New Support Request!</b>\n\n"
        f"👤 <b>User:</b> @{telegram_username}\n"
        f"🐦 <b>X (Twitter):</b> @{twitter_handle}\n\n"
        f"🔗 <b>Link:</b> {tweet_link}\n\n"
        f"👇 Please support and click the buttons below:"
    )
    
    try:
        # تغییر پارامترها به حالت ساده‌تر و پایدارتر
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=original_msg_id,
            text=group_post_text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        print(f"✅ [موفقیت] پست حمایت شماره {original_msg_id} با موفقیت مستقر شد.")
    except Exception as e:
        # حالا اگر مشکلی باشه دقیقاً توی ترمینال برات چاپ می‌کنه چه خبره
        print(f"❌ [خطا در فرستادن پست نهایی]: {e}")
        logging.error(f"Error deploying final post: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    telegram_username = update.effective_user.username
    chat_type = update.effective_chat.type

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
                if telegram_username:
                    user_mention = f"@{telegram_username}"
                else:
                    first_name_clean = update.effective_user.first_name.replace('<', '').replace('>', '')
                    user_mention = f'<a href="tg://user?id={user_id}">{first_name_clean}</a>'
                
                alert_link_text = (
                    f"❌ کاربر {user_mention}، لینک شما حذف شد!\n"
                    f"برای فعالیت در گروه، ابتدا باید وارد پی‌وی ربات شده و آیدی توییتر خود را ثبت کنید.\n\n"
                    f"🔗 <b><a href='t.me/XengageRobot'>ورود و ثبت‌نام در ربات</a></b>\n\n"
                    f"⏱ <i>این پیام طی ۱۵ ثانیه حذف می‌شود.</i>"
                )
                alert_link_msg = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=alert_link_text,
                    parse_mode="HTML"
                )
                asyncio.create_task(delete_message_delayed(context.bot, update.effective_chat.id, alert_link_msg.message_id, 15))
                conn.close()
                return

            twitter_handle = user_data[0]
            cursor.execute('UPDATE users SET last_tweet_link = ? WHERE user_id = ?', (tweet_link, user_id))
            conn.commit()
            conn.close()

            await update.message.delete()

            display_name = telegram_username if telegram_username else update.effective_user.first_name

            setup_keyboard = [
                [
                    InlineKeyboardButton("👥 Follow ❌", callback_data="config_follow"),
                    InlineKeyboardButton("❤️ Like ❌", callback_data="config_like")
                ],
                [
                    InlineKeyboardButton("🔁 Retweet ❌", callback_data="config_rt"),
                    InlineKeyboardButton("💬 Comment ❌", callback_data="config_comment")
                ],
                [
                    InlineKeyboardButton("🚀 تایید و ارسال به گروه", callback_data="config_approve")
                ]
            ]
            
            menu_text = (
                f"🛠 <b>تنظیمات پست حمایت جدید</b>\n\n"
                f"👤 کاربر: <b>{display_name}</b>\n"
                f"نوع حمایت‌های مورد نیاز برای این توییت را تیک بزنید. اگر تا ۱۵ ثانیه دیگر انتخابی نکنید، ربات به صورت خودکار تمام گزینه‌ها را فعال می‌کند:\n\n"
                f"⏱ <i>مهلت زمان انتخاب: ۱۵ ثانیه</i>"
            )

            menu_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=menu_text,
                reply_markup=InlineKeyboardMarkup(setup_keyboard),
                parse_mode="HTML"
            )

            PENDING_POSTS[menu_msg.message_id] = {
                "creator_id": user_id,
                "username": display_name,
                "twitter": twitter_handle,
                "tweet_link": tweet_link,
                "status": "pending",
                "options": {"follow": False, "like": False, "rt": False, "comment": False}
            }

            asyncio.create_task(auto_approve_post_delayed(context.bot, update.effective_chat.id, menu_msg.message_id, 15))
            return

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

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    clicker_id = query.from_user.id
    clicker_username = query.from_user.username
    message_id = query.message.message_id
    data = query.data

    # ۱. مدیریت منوی تنظیمات قبل ارسال
    if data.startswith("config_"):
        if message_id not in PENDING_POSTS:
            await query.answer("⚠️ زمان مجاز این منو به پایان رسیده است یا پست ثبت شده است.", show_alert=True)
            return
        
        post_data = PENDING_POSTS[message_id]
        
        if post_data.get("status") != "pending":
            await query.answer("⚠️ این پست قبلاً ارسال شده است.", show_alert=True)
            return
        
        if clicker_id != post_data["creator_id"]:
            await query.answer("❌ این منو اختصاصی است. شما نمی‌توانید تنظیمات پست دیگران را تغییر دهید!", show_alert=True)
            return

        action_type = data.split('_')[1]

        if action_type == "approve":
            post_data["status"] = "deployed"
            final_data = PENDING_POSTS.pop(message_id, None)
            await query.answer("🚀 در حال فرستادن پست به گروه...")
            if final_data:
                await deploy_final_post(context.bot, update.effective_chat.id, message_id, final_data, forced_all=False)
            return

        post_data["options"][action_type] = not post_data["options"][action_type]
        
        opts = post_data["options"]
        f_tick = "✅" if opts["follow"] else "❌"
        l_tick = "✅" if opts["like"] else "❌"
        r_tick = "✅" if opts["rt"] else "❌"
        c_tick = "✅" if opts["comment"] else "❌"

        updated_keyboard = [
            [
                InlineKeyboardButton(f"👥 Follow {f_tick}", callback_data="config_follow"),
                InlineKeyboardButton(f"❤️ Like {l_tick}", callback_data="config_like")
            ],
            [
                InlineKeyboardButton(f"🔁 Retweet {r_tick}", callback_data="config_rt"),
                InlineKeyboardButton(f"💬 Comment {c_tick}", callback_data="config_comment")
            ],
            [
                InlineKeyboardButton("🚀 تایید و ارسال به گروه", callback_data="config_approve")
            ]
        ]
        
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(updated_keyboard))
        except Exception as e:
            print(f"❌ [خطا در ادیت منو تیک‌ها]: {e}")
        await query.answer()
        return

    # ۲. مدیریت دکمه‌های اصلی حمایت گروه
    if data.startswith("support_"):
        data_parts = data.split('_')
        action = data_parts[1]
        creator_id = int(data_parts[2])

        if clicker_id == creator_id:
            await query.answer("❌ شما نمی‌توانید پست خودتان را حمایت کنید!", show_alert=True)
            return

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        cursor.execute('SELECT twitter_id, last_tweet_link FROM users WHERE user_id = ?', (clicker_id,))
        clicker_data = cursor.fetchone()

        if not clicker_data:
            await query.answer() 
            if clicker_username:
                user_mention = f"@{clicker_username}"
            else:
                first_name_clean = query.from_user.first_name.replace('<', '').replace('>', '')
                user_mention = f'<a href="tg://user?id={clicker_id}">{first_name_clean}</a>'
            
            alert_btn_text = (
                f"⚠️ کاربر {user_mention}، برای ثبت حمایت خود ابتدا باید در پی‌وی ربات ثبت‌نام کنید!\n\n"
                f"🔗 <b><a href='t.me/XengageRobot'>ورود و ثبت‌نام در ربات</a></b>\n\n"
                f"⏱ <i>این پیام طی ۱۵ ثانیه حذف می‌شود.</i>"
            )
            alert_btn_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=alert_btn_text,
                parse_mode="HTML"
            )
            asyncio.create_task(delete_message_delayed(context.bot, update.effective_chat.id, alert_btn_msg.message_id, 15))
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
            f"👤 کاربر @{clicker_username if clicker_username else query.from_user.first_name} (آیدی توییتر: @{clicker_twitter}) پست شما را [{action_fa}] کرد.\n\n"
            f"تعهد شما: حالا نوبت شماست که او را حمایت کنید!\n"
            f"🔗 آخرین لینک این کاربر: {clicker_last_link}"
        )
        
        try:
            await context.bot.send_message(chat_id=creator_id, text=alert_text)
        except Exception as e:
            logging.error(f"Could not send notification to {creator_id}: {e}")

def main():
    init_db()
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
    print("ربات Xengage با موفقیت راه‌اندازی شد...")
    application.run_polling()

if __name__ == '__main__':
    main()
