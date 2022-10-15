"""
This example demonstrates most basic operations with single model
"""
import asyncio
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Dict, Any, Optional, List

from tortoise import Tortoise, fields, run_async
from tortoise.models import Model
from datetime import datetime

from tortoise.signals import post_delete, pre_delete, post_save, pre_save
from tortoise.transactions import in_transaction


class Chat(Model):
    id = fields.BigIntField(pk=True, generated=False)
    name = fields.CharField(128)
    target = fields.BigIntField()
    target_name = fields.CharField(128)
    number = fields.CharField(16)


class MessageMeta(Model):
    id = fields.BigIntField(pk=True)
    source_id = fields.BigIntField()
    target_id = fields.BigIntField()
    source_chat = fields.ForeignKeyField("models.Chat", "source_messages")
    source_chat_id: int
    target_chat_id = fields.BigIntField()

    class Meta:
        table = "message"
        unique_together = [("source_chat_id", "source_id"), ("target_chat_id", "target_id")]
        indexes = [("source_chat_id", "source_id"), ("target_chat_id", "target_id")]


async def run():
    try:
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["__main__"]})
        await Tortoise.generate_schemas()
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    run_async(run())
