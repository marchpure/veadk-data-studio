from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy

from server.utils.config_loader import get_auth_secret, get_token_config

bearer_transport = BearerTransport(tokenUrl="auth/login")


def get_jwt_strategy() -> JWTStrategy:
    token_config = get_token_config()
    return JWTStrategy(secret=get_auth_secret(), lifetime_seconds=token_config["access_token_lifetime_seconds"])


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)
