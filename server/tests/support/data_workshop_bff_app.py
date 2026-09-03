from fastapi import FastAPI

from server.data_workshop import api
from server.schemas.standard_response import success_response

app = FastAPI(title="Data Workshop browser verification BFF")
app.include_router(api.router, prefix="/api")
app.include_router(api.console_router)


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
