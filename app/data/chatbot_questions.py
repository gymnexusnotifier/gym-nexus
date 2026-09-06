from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ChatbotQuestion:
    id: str
    question: str
    answer: Callable[[dict], str]


def _money(value) -> str:
    return f"Rs. {float(value or 0):,.0f}"


CHATBOT_QUESTIONS = (
    ChatbotQuestion(
        "active_members",
        "How many active members do we have?",
        lambda facts: f"You currently have {facts['active_members']} active members.",
    ),
    ChatbotQuestion(
        "new_members",
        "How many new members joined this month?",
        lambda facts: f"{facts['new_members']} new members joined this month.",
    ),
    ChatbotQuestion(
        "expiring_memberships",
        "How many memberships are expiring soon?",
        lambda facts: f"{facts['expiring_memberships']} memberships are expiring in the next 30 days.",
    ),
    ChatbotQuestion(
        "expired_memberships",
        "How many expired memberships do we have?",
        lambda facts: f"{facts['expired_members']} members currently have expired memberships.",
    ),
    ChatbotQuestion(
        "monthly_revenue",
        "What is our revenue this month?",
        lambda facts: f"Your total revenue this month is {_money(facts['monthly_revenue'])}.",
    ),
    ChatbotQuestion(
        "today_checkins",
        "How many check-ins did we have today?",
        lambda facts: f"You have {facts['today_checkins']} check-ins today.",
    ),
    ChatbotQuestion(
        "inactive_members",
        "How many members are currently inactive?",
        lambda facts: f"You currently have {facts['inactive_members']} inactive members.",
    ),
    ChatbotQuestion(
        "popular_plans",
        "What are the most popular membership plans?",
        lambda facts: f"The most popular plans are {facts['popular_plans']}." if facts['popular_plans'] else "No membership plans have been assigned yet.",
    ),
)

FALLBACK_MESSAGE = (
    "I'm still learning! I can currently help with member counts, memberships, "
    "revenue, and check-ins. Please select one of the suggested questions."
)
