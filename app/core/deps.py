import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.models.user_permission import UserPermission

ROLE_PERMISSIONS = {
    "staff": {"dashboard", "members", "attendance", "payments", "classes", "inquiries", "notifications"},
    "trainer": {"dashboard", "attendance", "classes"},
}


def has_permission(db: Session, user: User, permission: str) -> bool:
    if user.role.value == "gym_owner":
        return True
    override = db.query(UserPermission).filter(
        UserPermission.user_id == user.id,
        UserPermission.permission == permission,
    ).first()
    return override.allowed if override is not None else permission in ROLE_PERMISSIONS.get(user.role.value, set())


def require_permission(permission: str):
    def permission_checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if not has_permission(db, user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This privilege is not enabled for your account")
        return user
    return permission_checker

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if user is None:
        raise credentials_exception
    return user


def require_role(*allowed_roles: str):
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        return user
    return role_checker


def get_current_gym_id(user: User = Depends(get_current_user)) -> uuid.UUID:
    if user.gym_id is None:
        raise HTTPException(status_code=400, detail="User is not associated with a gym")
    return user.gym_id
