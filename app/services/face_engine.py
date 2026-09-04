import base64
import os
from io import BytesIO
from typing import Any, Dict, List

import numpy as np
from PIL import Image
from app.core.storage import get_member_photo, member_photo_exists

try:
    import face_recognition
except Exception as exc:  # pragma: no cover - dependency may be unavailable in deployment runtimes
    face_recognition = None
    FACE_RECOGNITION_ERROR = str(exc)
else:
    FACE_RECOGNITION_ERROR = None


class FaceRecognitionService:
    @staticmethod
    def available() -> bool:
        return face_recognition is not None

    @staticmethod
    def capability_message() -> str:
        if face_recognition is not None:
            return "Face recognition is active for live attendance scans."
        return (
            "Face recognition is in manual fallback mode because the native face engine could not load "
            "in this deployment. Use manual mark or enable the native library in a GPU-capable runtime."
        )

    @staticmethod
    def decode_frame(image_data: str):
        if not image_data:
            raise ValueError("No image data provided")
        _, encoded = image_data.split(",", 1) if "," in image_data else (None, image_data)
        img_bytes = base64.b64decode(encoded)
        return np.array(Image.open(BytesIO(img_bytes)).convert("RGB"))

    @classmethod
    def build_known_faces(cls, db, gym_id):
        if face_recognition is None:
            return []

        from app.models.member import Member

        members = db.query(Member).filter(Member.gym_id == gym_id).all()
        known = []
        for member in members:
            if not member_photo_exists(member.photo_path):
                continue
            try:
                image = face_recognition.load_image_file(BytesIO(get_member_photo(member.photo_path)))
                encodings = face_recognition.face_encodings(image)
            except Exception:
                continue
            if not encodings:
                continue
            known.append({
                "member_id": member.id,
                "name": member.name,
                "encoding": encodings[0],
            })
        return known

    @classmethod
    def recognize_member(cls, db, gym_id, image_data: str, face_match_tolerance: float = 0.5):
        if face_recognition is None:
            return {"status": "manual_only", "detail": cls.capability_message()}

        try:
            frame = cls.decode_frame(image_data)
        except Exception:
            return {"status": "error", "detail": "Could not decode the image"}

        face_locations = face_recognition.face_locations(frame)
        if not face_locations:
            return {"status": "no_face"}

        known_faces = cls.build_known_faces(db, gym_id)
        if not known_faces:
            return {"status": "no_known_faces"}

        face_encoding = face_recognition.face_encodings(frame, face_locations)[0]
        encodings = [entry["encoding"] for entry in known_faces]
        distances = face_recognition.face_distance(encodings, face_encoding)
        best_idx = int(np.argmin(distances))

        if distances[best_idx] > face_match_tolerance:
            return {"status": "unknown"}

        member = known_faces[best_idx]
        return {"status": "matched", "member": member}
