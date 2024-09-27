from pathlib import Path
from pydantic import BaseModel
from ruamel.yaml import YAML

from . import models


class AppConfig(BaseModel):
    class _TelegramBotConfig(BaseModel):
        token: str
        allowed_chats: list[str]

    class _ExpensesConfig(BaseModel):
        users: list[models.ExpenseUser]
        categories: list[models.ExpenseCategory]
        split_types: list[models.ExpenseSplitType]

    class _GSheetConfig(BaseModel):
        service_account_file: Path
        file_id: str
        transactions_worksheet_name: str
        summary_worksheet_name: str
        summary_worksheet_cell_user_in_debt: str
        summary_worksheet_cell_amount_to_repay: str

    class _OpenAIConfig(BaseModel):
        model: str
        api_key: str

    telegram_bot: _TelegramBotConfig
    openai: _OpenAIConfig
    expenses: _ExpensesConfig
    gsheet: _GSheetConfig


def load_config(config_file: Path) -> AppConfig:
    config = YAML(typ="safe").load(config_file)
    config = AppConfig(**config)
    return config
