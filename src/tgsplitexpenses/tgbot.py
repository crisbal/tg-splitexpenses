from enum import StrEnum
import logging
import pydantic
import typing

from datetime import datetime

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes
from telegram.ext import filters

from .config import AppConfig
from . import models
from .gsheet import GSheet

class UserState(StrEnum):
    START = "START"
    GET_TOTAL = "GET_TOTAL"
    GET_TITLE = "GET_TITLE"
    GET_CATEGORY = "GET_CATEGORY"
    GET_SPLIT_TYPE = "GET_SPLIT_TYPE"
    GET_PAID_BY = "GET_PAID_BY"
    END = "END"


def is_float(string: str):
    try:
        float(string)
        return True
    except ValueError:
        return False

def make_keyboard(options: list[str], cols: int, placeholder: str) -> ReplyKeyboardMarkup:
    keyboard = []
    for n in range(0, len(options), cols):
        row = options[n:n+cols]
        row_buttons = [KeyboardButton(opt) for opt in row]
        keyboard.append(row_buttons)
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, input_field_placeholder=placeholder)

def find_in_list(to_find: str, lst: list[pydantic.BaseModel], key: str):
    for elem in lst:
        if getattr(elem, key) == to_find:
            return elem
    return None

def get_suggested_category(title: str, categories: list[models.ExpenseCategory]) -> models.ExpenseCategory|None:
    keyword_to_category = {}
    for cat in categories:
        for kw in cat.keywords:
            keyword_to_category[kw.lower()] = cat
    suggested_category = None
    for word in title.lower().split(" "):
        if word in keyword_to_category:
            suggested_category = keyword_to_category[word]
            break
    return suggested_category

from functools import wraps
def restricted_by_chat_id(f):
    @wraps(f)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        app_config: AppConfig = context.bot_data["app_config"]
        if str(update.message.chat.id) not in app_config.telegram_bot.allowed_chats:
            logging.warning(f"Attempted message in {update.message.chat.id} by {update.message.from_user.username}. Not in allowed chats. Rejected.")
            return
        return await f(update, context)
    return wrapper

@restricted_by_chat_id
async def _handler_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_parts = [
        "Hello! 👋",
        "/add or /new to add a transaction",
        "/status to show debt status",
        "/stats NOT IMPLEMENTED"
    ]
    message = "\n".join(message_parts)
    await update.message.reply_text(message, quote=True)

@restricted_by_chat_id
async def _handler_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    context.user_data["STATE"] = UserState.START
    await _handler_text(update, context)

@restricted_by_chat_id
async def _handler_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app_config: AppConfig = context.bot_data["app_config"]
    current_state = context.user_data.get("STATE")

    logging.info(f"Handling: {update.message.from_user.name} ({update.message.from_user.id}) | {current_state} | {update.message.text} | {update.message.chat.id}")

    if current_state == None or current_state not in UserState._value2member_map_:
        await update.message.reply_text(f'⚠️ Unknown state. Reset with /new', reply_markup=ReplyKeyboardRemove(), quote=True)
        return

    if current_state == UserState.START:
        context.user_data["TRANSACTION"] = {}
        context.user_data["STATE"] = UserState.GET_TOTAL
        await update.message.reply_text(f'🆕 New transaction\n💲 Total:', reply_markup=ReplyKeyboardRemove(), quote=True)
        return

    if current_state == UserState.GET_TOTAL:
        total_text = update.message.text
        assert total_text
        if not is_float(total_text):
            await update.message.reply_text(f'Not a number. Total:', quote=True)
            return
        total = float(total_text)
        context.user_data["TRANSACTION"]["total"] = total
        context.user_data["STATE"] = UserState.GET_TITLE
        await update.message.reply_text(f'Total: {total}\n✏️ Title:', quote=True)
        return

    if current_state == UserState.GET_TITLE:
        title_text = update.message.text
        assert title_text
        title = title_text
        context.user_data["TRANSACTION"]["title"] = title
        context.user_data["STATE"] = UserState.GET_CATEGORY

        all_categories = [c.displayname for c in app_config.expenses.categories]
        # Add a suggested category as first option, based on title
        suggested_category = get_suggested_category(title, app_config.expenses.categories)
        if suggested_category:
            all_categories.insert(0, suggested_category.displayname)

        categories_keyboard = make_keyboard(all_categories, 3, "Category")
        await update.message.reply_text(f'Title: {title}\n🏷 Category:', reply_markup=categories_keyboard, quote=True)
        return

    if current_state == UserState.GET_CATEGORY:
        category_text = update.message.text
        assert category_text
        category: models.ExpenseCategory = find_in_list(category_text, app_config.expenses.categories, "displayname")
        if not category:
            categories_keyboard = make_keyboard([c.displayname for c in app_config.expenses.categories], 3, "Category")
            await update.message.reply_text(f'Not a valid category. Category:', reply_markup=categories_keyboard, quote=True)
            return
        context.user_data["TRANSACTION"]["category"] = category
        context.user_data["STATE"] = UserState.GET_PAID_BY
        paid_by_keyboard = make_keyboard([u.displayname for u in app_config.expenses.users], 1, "Paid by")
        await update.message.reply_text(f'Category: {category.displayname}\n👤 Paid by:', reply_markup=paid_by_keyboard, quote=True)
        return

    if current_state == UserState.GET_PAID_BY:
        paid_by_text = update.message.text
        assert paid_by_text
        paid_by: models.ExpenseUser = find_in_list(paid_by_text, app_config.expenses.users, "displayname")
        if not paid_by:
            paid_by_keyboard = make_keyboard([u.displayname for u in app_config.expenses.users], 1, "Paid by")
            await update.message.reply_text(f'Not a valid paid by. Paid by:', reply_markup=paid_by_keyboard, quote=True)
            return
        context.user_data["TRANSACTION"]["paid_by"] = paid_by
        context.user_data["STATE"] = UserState.GET_SPLIT_TYPE
        split_type_keybaord = make_keyboard([s.name for s in app_config.expenses.split_types], 1, "Split Type")
        await update.message.reply_text(f'Paid by: {paid_by.displayname}\n🔀 Split type:', reply_markup=split_type_keybaord, quote=True)
        return

    if current_state == UserState.GET_SPLIT_TYPE:
        split_type_text = update.message.text
        assert split_type_text
        split_type: models.ExpenseSplitType = find_in_list(split_type_text, app_config.expenses.split_types, "name")
        if not split_type:
            split_type_keybaord = make_keyboard([s.name for s in app_config.expenses.split_types], 1, "Split Type")
            await update.message.reply_text(f'Not a valid split type. Split type:', reply_markup=split_type_keybaord, quote=True)
            return
        context.user_data["TRANSACTION"]["split_type"] = split_type
        all_done = await update.message.reply_text(f'Split type: {split_type.name}\n⭐️ All done!', reply_markup=ReplyKeyboardRemove(), quote=True)

        transaction_dict = context.user_data["TRANSACTION"]
        transaction_dict["date"] = datetime.now()
        transaction = models.Transaction(**context.user_data["TRANSACTION"])

        gsheet: GSheet = context.bot_data["gsheet"]
        user_in_debt, amount_to_repay = gsheet.insert_transaction(transaction, app_config)

        context.user_data["STATE"] = UserState.END
        await update.message.reply_text(f'✅ Saved in cloud.\n\nUser in debt: {user_in_debt}\nAmount to repay: {amount_to_repay}\n\nUse /add to add more', reply_to_message_id=all_done.message_id)
        return

@restricted_by_chat_id
async def _handler_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app_config: AppConfig = context.bot_data["app_config"]
    gsheet: GSheet = context.bot_data["gsheet"]
    user_in_debt, amount_to_repay = gsheet.get_debtor(app_config)
    await update.message.reply_text(f'\n\nUser in debt: {user_in_debt}\nAmount to repay: {amount_to_repay}', quote=True)
    return



def make_app(app_config: AppConfig, gsheet: GSheet):
    async def _post_init(application):
        await application.bot.set_my_commands([
            ('add', 'Add a new transaction (or start over)'),
            ('status', 'Debt status'),
            ('start', 'Starts the bot'),
            ('help', 'Get help'),
        ])

    app = ApplicationBuilder().token(app_config.telegram_bot.token).post_init(_post_init).build()
    app.bot_data = {
        "app_config": app_config,
        "gsheet": gsheet,
    }
    app.add_handler(CommandHandler("start", _handler_start))
    app.add_handler(CommandHandler("help", _handler_start))
    app.add_handler(CommandHandler("new", _handler_new))
    app.add_handler(CommandHandler("add", _handler_new))
    app.add_handler(CommandHandler("status", _handler_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handler_text))
    return app
