try:
    import razorpay
except ImportError:
    razorpay = None

from app.core.config import settings


def get_razorpay_client():
    """Returns a configured Razorpay client, or None if no real API keys
    are set yet - callers should fall back to simulated billing so the
    whole flow can be built and tested before you have a live account."""
    if razorpay is None or not settings.razorpay_key_id or not settings.razorpay_key_secret:
        return None
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
