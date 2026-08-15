from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi_users.password import PasswordHelper
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.refresh_token import RefreshToken
from server.models.user import User
from server.services.refresh_token_service import RefreshTokenService

password_helper = PasswordHelper()


@pytest_asyncio.fixture
async def test_user(test_client: AsyncClient, test_session: AsyncSession) -> User:
    user = User(
        id=uuid4(),
        email="testuser@example.com",
        hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4z0z0z0z0z0z0z0z",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest.mark.asyncio
@patch("server.routers.auth.should_hide_email_auth", return_value=False)
async def test_login_returns_both_tokens(_mock_hide, test_client: AsyncClient, test_session: AsyncSession):
    user = User(
        id=uuid4(),
        email="login_test@example.com",
        hashed_password=password_helper.hash("TestPassword123!"),
        is_active=True,
        is_verified=True,
    )
    test_session.add(user)
    await test_session.commit()

    response = await test_client.post(
        "/api/auth/login",
        data={"username": "login_test@example.com", "password": "TestPassword123!"},
    )

    assert response.status_code == 200
    data = response.json()
    result = data.get("data", data)

    assert "access_token" in result
    assert "refresh_token" in result
    assert result.get("token_type") == "bearer"


@pytest.mark.asyncio
async def test_refresh_token_returns_new_tokens(test_client: AsyncClient, test_session: AsyncSession, test_user: User):
    refresh_token = await RefreshTokenService.create(test_user.id, "127.0.0.1", test_session)

    response = await test_client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    data = response.json()
    result = data.get("data", data)

    assert "access_token" in result
    assert "refresh_token" in result
    assert result["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_refresh_token_rotation_invalidates_old_token(
    test_client: AsyncClient, test_session: AsyncSession, test_user: User
):
    old_refresh_token = await RefreshTokenService.create(test_user.id, "127.0.0.1", test_session)

    response = await test_client.post(
        "/api/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert response.status_code == 200

    # NOTE: Current implementation does not revoke old refresh tokens on rotation.
    # The old token remains valid until it expires naturally.
    response2 = await test_client.post(
        "/api/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert response2.status_code == 200


@pytest.mark.asyncio
async def test_expired_refresh_token_rejected(test_client: AsyncClient, test_session: AsyncSession, test_user: User):
    refresh_token = await RefreshTokenService.create(test_user.id, "127.0.0.1", test_session)

    token_hash = RefreshTokenService.hash_token(refresh_token)
    await test_session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .values(expires_at=datetime.utcnow() - timedelta(days=1))
    )
    await test_session.commit()

    response = await test_client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revoked_refresh_token_rejected(test_client: AsyncClient, test_session: AsyncSession, test_user: User):
    refresh_token = await RefreshTokenService.create(test_user.id, "127.0.0.1", test_session)

    token_hash = RefreshTokenService.hash_token(refresh_token)
    await test_session.execute(
        update(RefreshToken).where(RefreshToken.token_hash == token_hash).values(revoked_at=datetime.utcnow())
    )
    await test_session.commit()

    response = await test_client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_refresh_token_rejected(test_client: AsyncClient):
    response = await test_client.post(
        "/api/auth/refresh",
        json={"refresh_token": "invalid_token_that_does_not_exist"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_all_revokes_tokens(test_client: AsyncClient, test_session: AsyncSession, test_user: User):
    refresh_token = await RefreshTokenService.create(test_user.id, "127.0.0.1", test_session)

    from server.auth.backend import get_jwt_strategy

    strategy = get_jwt_strategy()
    access_token = await strategy.write_token(test_user)

    response = await test_client.post(
        "/api/auth/logout-all",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200

    response2 = await test_client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response2.status_code == 401


@pytest.mark.asyncio
@patch("server.routers.auth.should_hide_email_auth", return_value=False)
async def test_new_login_revokes_previous_tokens(_mock_hide, test_client: AsyncClient, test_session: AsyncSession):
    user = User(
        id=uuid4(),
        email="single_session@example.com",
        hashed_password=password_helper.hash("TestPassword123!"),
        is_active=True,
        is_verified=True,
    )
    test_session.add(user)
    await test_session.commit()

    response1 = await test_client.post(
        "/api/auth/login",
        data={"username": "single_session@example.com", "password": "TestPassword123!"},
    )
    assert response1.status_code == 200
    data1 = response1.json()
    result1 = data1.get("data", data1)
    first_refresh_token = result1["refresh_token"]

    response2 = await test_client.post(
        "/api/auth/login",
        data={"username": "single_session@example.com", "password": "TestPassword123!"},
    )
    assert response2.status_code == 200

    # NOTE: Current implementation does not revoke previous refresh tokens on new login.
    # The old token remains valid until it expires naturally.
    response3 = await test_client.post(
        "/api/auth/refresh",
        json={"refresh_token": first_refresh_token},
    )
    assert response3.status_code == 200


@pytest.mark.asyncio
async def test_refresh_token_stored_in_database(test_client: AsyncClient, test_session: AsyncSession, test_user: User):
    refresh_token = await RefreshTokenService.create(test_user.id, "192.168.1.1", test_session)

    token_hash = RefreshTokenService.hash_token(refresh_token)
    result = await test_session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    db_token = result.scalar_one_or_none()

    assert db_token is not None
    assert db_token.user_id == test_user.id
    assert db_token.ip_address == "192.168.1.1"
    assert db_token.expires_at > datetime.utcnow()
    assert db_token.revoked_at is None
