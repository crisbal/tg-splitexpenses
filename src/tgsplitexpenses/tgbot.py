from enum import StrEnum
import logging
import typing as t

from datetime import datetime
from functools import wraps

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
)
from telegram.ext import filters
from pydantic import create_model, Field

from .config import AppConfig
from . import models
from .gsheet import GSheet
from openai import OpenAI
from .utils import is_float, make_keyboard, find_in_list, get_suggested_category


class UserState(StrEnum):
    START = "START"
    GET_TOTAL = "GET_TOTAL"
    GET_TITLE = "GET_TITLE"
    GET_CATEGORY = "GET_CATEGORY"
    GET_SPLIT_TYPE = "GET_SPLIT_TYPE"
    GET_PAID_BY = "GET_PAID_BY"
    END = "END"


def restricted_by_chat_id(f):
    @wraps(f)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        app_config: AppConfig = context.bot_data["app_config"]
        if str(update.message.chat.id) not in app_config.telegram_bot.allowed_chats:
            logging.warning(
                f"Attempted message in {update.message.chat.id} by {update.message.from_user.username}. Not in allowed chats. Rejected."
            )
            return
        return await f(update, context)

    return wrapper


@restricted_by_chat_id
async def _handler_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_parts = [
        "Hello! 👋",
        "/add or /new to add a transaction",
        "/aiadd to add a transaction with AI",
        "/status to show debt status",
        "/stats NOT IMPLEMENTED",
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

    logging.info(
        f"Handling: {update.message.from_user.name} ({update.message.from_user.id}) | {current_state} | {update.message.text} | {update.message.chat.id}"
    )

    if current_state is None or current_state not in UserState._value2member_map_:
        await update.message.reply_text(
            "⚠️ Unknown state. Reset with /new",
            reply_markup=ReplyKeyboardRemove(),
            quote=True,
        )
        return

    if current_state == UserState.START:
        context.user_data["TRANSACTION"] = {}
        context.user_data["STATE"] = UserState.GET_TOTAL
        await update.message.reply_text(
            "🆕 New transaction\n💲 Total:",
            reply_markup=ReplyKeyboardRemove(),
            quote=True,
        )
        return

    if current_state == UserState.GET_TOTAL:
        total_text = update.message.text
        assert total_text
        if not is_float(total_text):
            await update.message.reply_text("Not a number. Total:", quote=True)
            return
        total = float(total_text)
        context.user_data["TRANSACTION"]["total"] = total
        context.user_data["STATE"] = UserState.GET_TITLE
        await update.message.reply_text(f"Total: {total}\n✏️ Title:", quote=True)
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
        await update.message.reply_text(
            f"Title: {title}\n🏷 Category:", reply_markup=categories_keyboard, quote=True
        )
        return

    if current_state == UserState.GET_CATEGORY:
        category_text = update.message.text
        assert category_text
        category: models.ExpenseCategory = find_in_list(
            category_text, app_config.expenses.categories, "displayname"
        )
        if not category:
            categories_keyboard = make_keyboard(
                [c.displayname for c in app_config.expenses.categories], 3, "Category"
            )
            await update.message.reply_text(
                "Not a valid category. Category:",
                reply_markup=categories_keyboard,
                quote=True,
            )
            return
        context.user_data["TRANSACTION"]["category"] = category
        context.user_data["STATE"] = UserState.GET_PAID_BY
        paid_by_keyboard = make_keyboard([u.displayname for u in app_config.expenses.users], 1, "Paid by")
        await update.message.reply_text(
            f"Category: {category.displayname}\n👤 Paid by:",
            reply_markup=paid_by_keyboard,
            quote=True,
        )
        return

    if current_state == UserState.GET_PAID_BY:
        paid_by_text = update.message.text
        assert paid_by_text
        paid_by: models.ExpenseUser = find_in_list(paid_by_text, app_config.expenses.users, "displayname")
        if not paid_by:
            paid_by_keyboard = make_keyboard([u.displayname for u in app_config.expenses.users], 1, "Paid by")
            await update.message.reply_text(
                "Not a valid paid by. Paid by:",
                reply_markup=paid_by_keyboard,
                quote=True,
            )
            return
        context.user_data["TRANSACTION"]["paid_by"] = paid_by
        context.user_data["STATE"] = UserState.GET_SPLIT_TYPE
        split_type_keybaord = make_keyboard(
            [s.name for s in app_config.expenses.split_types], 1, "Split Type"
        )
        await update.message.reply_text(
            f"Paid by: {paid_by.displayname}\n🔀 Split type:",
            reply_markup=split_type_keybaord,
            quote=True,
        )
        return

    if current_state == UserState.GET_SPLIT_TYPE:
        split_type_text = update.message.text
        assert split_type_text
        split_type: models.ExpenseSplitType = find_in_list(
            split_type_text, app_config.expenses.split_types, "name"
        )
        if not split_type:
            split_type_keybaord = make_keyboard(
                [s.name for s in app_config.expenses.split_types], 1, "Split Type"
            )
            await update.message.reply_text(
                "Not a valid split type. Split type:",
                reply_markup=split_type_keybaord,
                quote=True,
            )
            return
        context.user_data["TRANSACTION"]["split_type"] = split_type
        all_done = await update.message.reply_text(
            f"Split type: {split_type.name}\n⭐️ All done!",
            reply_markup=ReplyKeyboardRemove(),
            quote=True,
        )

        transaction_dict = context.user_data["TRANSACTION"]
        transaction_dict["date"] = datetime.now()
        transaction = models.Transaction(**context.user_data["TRANSACTION"])

        gsheet: GSheet = context.bot_data["gsheet"]
        try:
            user_in_debt, amount_to_repay = gsheet.insert_transaction(transaction, app_config)
            context.user_data["STATE"] = UserState.END
            await update.message.reply_text(
                f"✅ Saved to cloud.\n\nUser in debt: {user_in_debt}\nAmount to repay: {amount_to_repay}\n\nUse /add to add more\n\n🆕 Try /aiadd",
                reply_to_message_id=all_done.message_id,
            )
        except Exception as e:
            logging.error(e)
            await update.message.reply_text(
                f"❌ Error saving to cloud.\n\n{str(e)}\n\nUse /add to try again.",
                reply_to_message_id=all_done.message_id,
            )
        return


@restricted_by_chat_id
async def _handler_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app_config: AppConfig = context.bot_data["app_config"]
    gsheet: GSheet = context.bot_data["gsheet"]
    user_in_debt, amount_to_repay = gsheet.get_debtor(app_config)
    await update.message.reply_text(
        f"\n\nUser in debt: {user_in_debt}\nAmount to repay: {amount_to_repay}",
        quote=True,
    )
    return


@restricted_by_chat_id
async def _handler_aiadd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    context.user_data["STATE"] = UserState.START
    user_text = update.message.text
    assert user_text
    user_text = user_text.replace("/aiadd", "").strip()
    if not len(user_text):
        await update.message.reply_text("Please provide a description of the transaction", quote=True)
        return

    # The following will generate a dynamic Pydantic model based on app_config, so we can give it to OpenAI to parse the response
    app_config: AppConfig = context.bot_data["app_config"]
    category_enum = StrEnum("Category", {c.name: c.name for c in app_config.expenses.categories})
    user_enum = StrEnum("User", {u.name: u.name for u in app_config.expenses.users})
    split_type_enum = StrEnum("SplitType", {s.name: s.name for s in app_config.expenses.split_types})
    transaction_model = create_model(
        "Transaction",
        total=(float, Field(..., description="Total amount of the transaction. Must be greater than 0")),
        title=(
            str,
            Field(..., description="Title of the transaction, usually a description of what was bought"),
        ),
        category=(
            category_enum,
            Field(..., description="Category of the transaction. Guess based on the title"),
        ),
        paid_by=(user_enum, Field(..., description="User who paid the transaction")),
        split_type=(
            split_type_enum,
            Field(
                description="How the transaction should be split between the users",
                default=app_config.expenses.split_types[0].name,
            ),
        ),
    )
    response_model = create_model(
        "Response",
        error=(
            t.Optional[str],
            Field(
                ...,
                description="Human readable message in case the transaction could not be completely parsed",
            ),
        ),
        missing_fields=(
            t.Optional[t.List[str]],
            Field(
                ..., description="Transaction fields that could not be found or guessed from the user input"
            ),
        ),
        transaction=(
            t.Optional[transaction_model],
            Field(
                ...,
                description="Transaction as parsed from the user input. If all fields could not be parsed or guessed correctly, this will be null",
            ),
        ),
    )
    messages = [
        {"role": "system", "content": "Extract the information about this transaction"},
        {"role": "user", "content": f"Transaction was paid by: {update.message.from_user.full_name}"},
        {"role": "user", "content": f"Transaction description: {user_text}"},
    ]

    openai: OpenAI = context.bot_data["openai"]
    completion = openai.beta.chat.completions.parse(
        model=app_config.openai.model,
        messages=messages,
        response_format=response_model,
    )
    response_model = completion.choices[0].message.parsed
    if response_model.error:
        await update.message.reply_text(
            f"{response_model.error}\n{response_model.missing_fields}", quote=True
        )
        return

    transaction = models.Transaction(
        total=response_model.transaction.total,
        title=response_model.transaction.title,
        category=find_in_list(
            response_model.transaction.category.value, app_config.expenses.categories, "name"
        ),
        paid_by=find_in_list(response_model.transaction.paid_by.value, app_config.expenses.users, "name"),
        split_type=find_in_list(
            response_model.transaction.split_type.value, app_config.expenses.split_types, "name"
        ),
        date=datetime.now(),
    )
    await update.message.reply_text(f"Transaction extracted by AI:\n\n{transaction}", quote=True)

    gsheet: GSheet = context.bot_data["gsheet"]
    try:
        user_in_debt, amount_to_repay = gsheet.insert_transaction(transaction, app_config)
        context.user_data["STATE"] = UserState.END
        await update.message.reply_text(
            f"✅ Saved to cloud.\n\nUser in debt: {user_in_debt}\nAmount to repay: {amount_to_repay}\n\nUse /add to add more\n\n🆕 Try /aiadd",
            quote=True,
        )
    except Exception as e:
        logging.error(e)
        await update.message.reply_text(
            f"❌ Error saving to cloud.\n\n{str(e)}\n\nUse /add to try again.", quote=True
        )
    return


def make_app(app_config: AppConfig, gsheet: GSheet, openai: OpenAI):
    async def _post_init(application):
        await application.bot.set_my_commands(
            [
                ("add", "Add a new transaction (or start over)"),
                ("aiadd", "Add a new transaction (AI)"),
                ("status", "Debt status"),
                ("start", "Starts the bot"),
                ("help", "Get help"),
            ]
        )

    app = ApplicationBuilder().token(app_config.telegram_bot.token).post_init(_post_init).build()
    app.bot_data = {
        "app_config": app_config,
        "gsheet": gsheet,
        "openai": openai,
    }
    app.add_handler(CommandHandler("start", _handler_start))
    app.add_handler(CommandHandler("help", _handler_start))
    app.add_handler(CommandHandler("new", _handler_new))
    app.add_handler(CommandHandler("add", _handler_new))
    app.add_handler(CommandHandler("aiadd", _handler_aiadd))
    app.add_handler(CommandHandler("status", _handler_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handler_text))
    return app
