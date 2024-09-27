from pydantic import BaseModel
from datetime import datetime


class ExpenseUser(BaseModel):
    id: str
    emoji: str
    name: str

    @property
    def displayname(self):
        return f"{self.emoji} {self.name}"


class ExpenseSplitType(BaseModel):
    name: str
    split: dict[str, float]  # user-id to percentange


class ExpenseCategory(BaseModel):
    name: str
    emoji: str
    keywords: list[str]

    @property
    def displayname(self):
        return f"{self.emoji} {self.name}"


class Transaction(BaseModel):
    date: datetime
    total: float
    title: str
    category: ExpenseCategory
    paid_by: ExpenseUser
    split_type: ExpenseSplitType

    def __str__(self):
        return f"{self.date.strftime('%Y-%m-%d %H:%M')} - {self.title} - {self.total} - {self.paid_by.displayname} - {self.category.displayname} - {self.split_type.name}"
