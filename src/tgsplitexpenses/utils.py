from telegram import KeyboardButton, ReplyKeyboardMarkup
import pydantic
from . import models


def is_float(string: str):
    try:
        float(string)
        return True
    except ValueError:
        return False


def make_keyboard(options: list[str], cols: int, placeholder: str) -> ReplyKeyboardMarkup:
    keyboard = []
    for n in range(0, len(options), cols):
        row = options[n : n + cols]
        row_buttons = [KeyboardButton(opt) for opt in row]
        keyboard.append(row_buttons)
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, input_field_placeholder=placeholder)


def find_in_list(to_find: str, lst: list[pydantic.BaseModel], key: str):
    for elem in lst:
        if getattr(elem, key) == to_find:
            return elem
    return None


def get_suggested_category(
    title: str, categories: list[models.ExpenseCategory]
) -> models.ExpenseCategory | None:
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
