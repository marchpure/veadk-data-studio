from uuid import UUID

from fastapi_users import FastAPIUsers

from server.auth.backend import auth_backend
from server.auth.manager import get_user_manager
from server.models.user import User

fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_verified_user = fastapi_users.current_user(active=True, verified=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
