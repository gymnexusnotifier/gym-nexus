import re
from typing import Any

from app.data.chatbot_questions import CHATBOT_QUESTIONS, FALLBACK_MESSAGE


def _normalize(question: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()


def suggested_questions() -> list[dict[str, str]]:
    return [{"id": item.id, "question": item.question} for item in CHATBOT_QUESTIONS]


def ask_chatbot(question: str, facts: dict[str, Any]) -> dict[str, Any]:
    normalized_question = _normalize(question)
    for item in CHATBOT_QUESTIONS:
        if normalized_question == _normalize(item.question):
            return {"message": item.answer(facts), "suggestions": []}

    return {"message": FALLBACK_MESSAGE, "suggestions": suggested_questions()}
