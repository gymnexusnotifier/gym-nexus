from collections.abc import Mapping
from typing import Any

from app.core.config import settings


ASCENDING = 1
DESCENDING = -1


_client: Any | None = None


_INDEXES: Mapping[str, tuple[tuple[Any, bool], ...]] = {
    "users": ((("email", ASCENDING), True),),
    "platform_plans": ((("name", ASCENDING), True),),
    "support_tickets": ((("ticket_code", ASCENDING), True),),
    "attendance": (
        ((("gym_id", ASCENDING), ("member_id", ASCENDING), ("date", ASCENDING)), True),
        ((("gym_id", ASCENDING), ("date", DESCENDING)), False),
    ),
    "class_bookings": (
        ((("class_id", ASCENDING), ("member_id", ASCENDING)), True),
        ((("class_id", ASCENDING),), False),
    ),
    "members": ((("gym_id", ASCENDING), ("status", ASCENDING)),),
    "payments": ((("gym_id", ASCENDING), ("payment_date", DESCENDING)),),
    "inquiries": ((("gym_id", ASCENDING), ("next_followup", ASCENDING)),),
}


def get_mongo_client() -> Any:
    global _client
    if not settings.mongodb_url:
        raise RuntimeError("MONGODB_URL is required when DB_BACKEND=mongo")
    if _client is None:
        from pymongo import MongoClient

        _client = MongoClient(settings.mongodb_url, serverSelectionTimeoutMS=5000)
    return _client


def get_mongo_database() -> Any:
    return get_mongo_client()[settings.mongodb_database]


def initialize_mongodb() -> None:
    database = get_mongo_database()
    get_mongo_client().admin.command("ping")

    for collection_name, indexes in _INDEXES.items():
        collection = database[collection_name]
        for keys, unique in indexes:
            collection.create_index(list(keys), unique=unique)


def close_mongodb() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def mongo_health() -> dict[str, Any]:
    if not settings.mongodb_url:
        return {"configured": False, "connected": False}
    try:
        get_mongo_client().admin.command("ping")
    except Exception as exc:
        return {"configured": True, "connected": False, "error": str(exc)}
    return {"configured": True, "connected": True}