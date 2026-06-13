"""Shared MongoDB connection used by the bot and Flask dashboard."""

import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

_client: MongoClient | None = None
_db = None


def get_db():
    """Return the shared discord_bot database handle (lazy singleton)."""
    global _client, _db
    if _db is not None:
        return _db

    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        return None

    _client = MongoClient(mongo_uri)
    _db = _client["discord_bot"]
    return _db


def get_bot_token() -> str | None:
    """Accept either env var name so bot and dashboard stay in sync."""
    return os.getenv("DISCORD_BOT_TOKEN") or os.getenv("DISCORD_TOKEN")
