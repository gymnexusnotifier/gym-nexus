import json
import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.core.deps import require_role, get_current_gym_id
from app.core.razorpay_client import get_razorpay_client
from app.models.gym import Gym
from app.models.platform_plan import PlatformPlan
from app.schemas.billing import (
    PlatformPlanResponse, SubscribeRequest, SubscribeResponse, BillingStatusResponse,
)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=List[PlatformPlanResponse])
def list_platform_plans(db: Session = Depends(get_db)):
    return db.query(PlatformPlan).order_by(PlatformPlan.price).all()


@router.post("/subscribe", response_model=SubscribeResponse)
def subscribe(
    payload: SubscribeRequest,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    plan = db.query(PlatformPlan).filter(PlatformPlan.id == payload.platform_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Platform plan not found")

    gym = db.query(Gym).filter(Gym.id == gym_id).first()
    client = get_razorpay_client()

    if client is None:
        # Simulated mode - no live Razorpay account configured yet.
        razorpay_subscription_id = f"sim_sub_{uuid.uuid4().hex[:12]}"
        status = "active"
        checkout_url = None
    else:
        if not plan.razorpay_plan_id:
            raise HTTPException(status_code=400, detail="This plan has no Razorpay plan_id configured yet")
        subscription = client.subscription.create({
            "plan_id": plan.razorpay_plan_id,
            "customer_notify": 1,
            "total_count": 120,
        })
        razorpay_subscription_id = subscription["id"]
        status = subscription["status"]
        checkout_url = subscription.get("short_url")

    gym.platform_plan_id = plan.id
    gym.razorpay_subscription_id = razorpay_subscription_id
    gym.subscription_status = status
    db.commit()

    return SubscribeResponse(
        razorpay_subscription_id=razorpay_subscription_id,
        status=status,
        checkout_url=checkout_url,
    )


@router.get("/status", response_model=BillingStatusResponse)
def billing_status(
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner", "staff")),
):
    gym = db.query(Gym).filter(Gym.id == gym_id).first()
    plan = (
        db.query(PlatformPlan).filter(PlatformPlan.id == gym.platform_plan_id).first()
        if gym.platform_plan_id else None
    )

    return BillingStatusResponse(
        plan_name=plan.name if plan else None,
        subscription_status=gym.subscription_status,
        trial_ends_at=gym.trial_ends_at,
        current_period_end=gym.current_period_end,
    )


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    payload_bytes = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    client = get_razorpay_client()
    if client is not None and app_settings.razorpay_webhook_secret:
        try:
            client.utility.verify_webhook_signature(
                payload_bytes.decode(), signature, app_settings.razorpay_webhook_secret
            )
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = json.loads(payload_bytes)
    event_type = event.get("event", "")
    subscription_entity = event.get("payload", {}).get("subscription", {}).get("entity", {})
    razorpay_subscription_id = subscription_entity.get("id")

    if not razorpay_subscription_id:
        return {"status": "ignored"}

    gym = db.query(Gym).filter(Gym.razorpay_subscription_id == razorpay_subscription_id).first()
    if not gym:
        return {"status": "ignored"}

    if event_type == "subscription.activated":
        gym.subscription_status = "active"
    elif event_type == "subscription.charged":
        gym.subscription_status = "active"
        current_end = subscription_entity.get("current_end")
        if current_end:
            gym.current_period_end = date.fromtimestamp(current_end)
    elif event_type in ("subscription.cancelled", "subscription.completed"):
        gym.subscription_status = "cancelled"
    elif event_type in ("subscription.halted", "subscription.pending"):
        gym.subscription_status = "past_due"

    db.commit()
    return {"status": "processed"}
