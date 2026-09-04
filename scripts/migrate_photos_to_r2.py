"""Copy existing local member photos to the configured R2 bucket."""

import os

from app.core.database import SessionLocal
from app.core.storage import save_member_photo
from app.models.member import Member


def main() -> None:
    db = SessionLocal()
    migrated = 0
    skipped = 0
    try:
        members = db.query(Member).filter(Member.photo_path.isnot(None)).all()
        for member in members:
            path = member.photo_path
            if not path or path.startswith("r2://") or not os.path.exists(path):
                skipped += 1
                continue
            extension = os.path.splitext(path)[1].lstrip(".") or "jpg"
            with open(path, "rb") as photo:
                member.photo_path = save_member_photo(str(member.gym_id), str(member.id), photo.read(), extension)
            migrated += 1
        db.commit()
        print(f"Migrated {migrated} photo(s); skipped {skipped}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
