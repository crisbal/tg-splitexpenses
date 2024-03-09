import logging

import gspread

from .config import AppConfig
from .models import Transaction

import typing


class GSheet:
    def __init__(self, app_config: AppConfig) -> None:
        gsa = gspread.service_account(filename=app_config.gsheet.service_account_file)
        ss = gsa.open_by_key(app_config.gsheet.file_id)
        self.transactions_worksheet = ss.worksheet(app_config.gsheet.transactions_worksheet_name)
        self.summary_worksheet = ss.worksheet(app_config.gsheet.summary_worksheet_name)

    @staticmethod
    def _create_row_from_transaction(transaction: Transaction, app_config: AppConfig) -> list:
        share_by_user = {}

        for user, percentage in transaction.split_type.split.items():
            share_by_user[user] = transaction.total * percentage / 100

        row = [
            transaction.date.year,
            transaction.date.month,
            transaction.date.day,
            f"{transaction.date.hour}:{transaction.date.minute}",
            transaction.title,
            transaction.category.name,
            transaction.total,
            transaction.paid_by.name,
            transaction.split_type.name,
            *[
                transaction.split_type.split[user.id] / 100 for user in app_config.expenses.users
            ],  # percentage
            *[share_by_user[user.id] for user in app_config.expenses.users],  # money in transaction
            *[
                0 if user.id == transaction.paid_by.id else share_by_user[user.id]
                for user in app_config.expenses.users
            ],  # transaction debt
        ]
        return row

    def insert_transaction(self, transaction: Transaction, app_config: AppConfig) -> typing.Tuple[str, float]:
        logging.info(f"Inserting transaction {transaction}")
        row = GSheet._create_row_from_transaction(transaction, app_config)
        self.transactions_worksheet.insert_row(row, index=2)  # Skip header
        return self.get_debtor(app_config)

    def get_debtor(self, app_config: AppConfig) -> typing.Tuple[str, float]:
        user_in_debt = self.summary_worksheet.acell(
            app_config.gsheet.summary_worksheet_cell_user_in_debt
        ).value
        amount_to_repay = self.summary_worksheet.acell(
            app_config.gsheet.summary_worksheet_cell_amount_to_repay
        ).value
        return user_in_debt, amount_to_repay
