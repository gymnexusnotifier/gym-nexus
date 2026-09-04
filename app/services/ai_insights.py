from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.member import Member


def build_ai_snapshot(db: Session, gym_id):
    today = date.today()
    recent_start = today - timedelta(days=7)

    recent_rows = db.query(Attendance).filter(
        Attendance.gym_id == gym_id,
        Attendance.date >= recent_start,
    ).all()

    hour_counts = {}
    for row in recent_rows:
        if not row.check_in_time:
            continue
        hour = int(row.check_in_time.split(":")[0])
        hour_counts[hour] = hour_counts.get(hour, 0) + 1

    peak_hour = None
    peak_volume = 0
    if hour_counts:
        peak_hour, peak_volume = max(hour_counts.items(), key=lambda item: item[1])

    active_members = db.query(Member).filter(Member.gym_id == gym_id, Member.status == "active").count()
    today_checkins = db.query(Attendance).filter(
        Attendance.gym_id == gym_id,
        Attendance.date == today,
    ).count()

    attendance_health = "Strong"
    if today_checkins == 0:
        attendance_health = "Needs attention"
    elif active_members and today_checkins / max(active_members, 1) < 0.2:
        attendance_health = "Watchlist"

    actions = []
    if peak_hour is not None:
        actions.append(f"Prime staff coverage around {peak_hour}:00 when traffic is strongest.")
    if today_checkins == 0:
        actions.append("Launch a motivational re-engagement message for inactive members.")
    else:
        actions.append("Keep the scanner ready for quick check-ins during the busiest hour.")

    summary = (
        f"Attendance health is {attendance_health.lower()}. "
        f"The strongest recent pattern is around {peak_hour}:00 with {peak_volume} check-ins in the last 7 days."
        if peak_hour is not None else f"Attendance health is {attendance_health.lower()}."
    )

    return {
        "attendance_health": attendance_health,
        "peak_hour": peak_hour,
        "peak_volume": peak_volume,
        "today_checkins": today_checkins,
        "summary": summary,
        "actions": actions,
    }
