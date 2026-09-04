from pydantic import BaseModel


class NotificationResult(BaseModel):
    sent: int
    skipped_no_email: int
    failed: int
