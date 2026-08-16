from fastapi import APIRouter

from server.db.session import AsyncSessionFactory
from server.schemas.standard_response import success_response
from server.services.community_setup import get_local_bootstrap
from server.utils.config_loader import get_self_hosted_config, is_self_hosted
from server.utils.deployment import get_feature_flags

router = APIRouter()


@router.get("/app/config")
async def get_app_config():
    """
    Get public application configuration.
    This endpoint is unauthenticated and exposes only non-sensitive config.
    """
    features = get_feature_flags()

    config = {
        "features": features,
    }

    # Add org name for self-hosted mode
    if is_self_hosted():
        self_hosted_config = get_self_hosted_config()
        config["org_name"] = self_hosted_config["org_name"]

    # Local browser/desktop: include only the non-sensitive identity required
    # to select the already-local workspace. Never expose it in self-hosted mode.
    if not is_self_hosted():
        async with AsyncSessionFactory() as session:
            bootstrap = await get_local_bootstrap(session)
            if bootstrap:
                config["local_bootstrap"] = bootstrap
                config["community_bootstrap"] = bootstrap

    return success_response(data=config, message="App configuration retrieved")
