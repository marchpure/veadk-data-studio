from fastapi import APIRouter

from server.auth.config import fastapi_users
from server.schemas.user import UserRead, UserUpdate

router = APIRouter()

router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)
