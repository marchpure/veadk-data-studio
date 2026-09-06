import os
from types import SimpleNamespace

from fastapi import FastAPI

os.environ.setdefault("DATA_WORKSHOP_BACKEND_MODE", "TEST")
os.environ.setdefault("OPENCONNECTOR_TEST_RUNTIME_TOKEN", "test-runtime-token")
os.environ.setdefault(
    "OPENCONNECTOR_PUBLIC_URL",
    "https://s4j054gh1e125mqsipi2e.apigateway-cn-beijing.volceapi.com",
)

from server.data_workshop import api
from server.schemas.standard_response import success_response

app = FastAPI(title="Data Workshop browser verification BFF")
app.include_router(api.router, prefix="/api")
app.include_router(api.console_router)
test_admin = SimpleNamespace(
    tenant_id="00000000-0000-0000-0000-000000000001",
    user_id="00000000-0000-0000-0000-000000000001",
    is_admin=True,
    has_scope=lambda _: True,
)


app.dependency_overrides[api.require_workshop_member] = lambda: test_admin
app.dependency_overrides[api.require_workshop_admin] = lambda: test_admin


@app.get("/api/app/config")
async def app_config():
    return success_response(
        data={
            "features": {
                "worker_features_enabled": False,
                "external_sharing_enabled": False,
                "notebook_import_enabled": False,
                "public_registration_enabled": False,
                "local_auth_enabled": True,
                "invitation_only": False,
                "google_oauth_enabled": False,
                "enterprise_licensed": False,
                "team_sharing_enabled": False,
            }
        }
    )


@app.get("/health")
async def health():
    return {"status": "healthy"}
