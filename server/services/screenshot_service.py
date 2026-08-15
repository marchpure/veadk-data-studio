"""Screenshot service for generating dashboard images via Cloudflare Worker."""

from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from server.services.export_service import CompiledHtmlExportService
from server.services.settings import SettingsService
from server.utils.config_loader import get_waitlist_config
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


def get_worker_url() -> str:
    """Get worker URL from environment configuration."""
    config = get_waitlist_config()
    worker_url = config.get("worker_url")
    if not worker_url:
        raise ValueError("WORKER_URL environment variable is not configured")
    return worker_url


class ScreenshotServiceError(Exception):
    """Raised when screenshot generation fails."""

    pass


class ScreenshotService:
    """Service for generating PNG screenshots of dashboards via Cloudflare Worker."""

    TIMEOUT_SECONDS = 60

    @classmethod
    async def capture(cls, session: AsyncSession, dashboard_id: UUID, version: int | None = None) -> bytes:
        """
        Generate a PNG screenshot of a dashboard via Cloudflare Worker.

        Args:
            session: Database session
            dashboard_id: UUID of the dashboard/notebook to capture
            version: Optional specific version to capture (defaults to latest)

        Returns:
            PNG image as bytes

        Raises:
            ScreenshotServiceError: If screenshot generation fails or worker is unavailable
        """
        try:
            logger.info(f"Starting screenshot capture for dashboard {dashboard_id}")

            api_key_setting = await SettingsService.get_setting_by_key(session, "api_key")
            if not api_key_setting:
                raise ScreenshotServiceError("API key not configured. Cannot authenticate with worker.")

            compiled_html = await CompiledHtmlExportService.generate_compiled_html(
                session=session, notebook_id=str(dashboard_id), version=version, disable_animations=True
            )

            logger.info(f"Generated compiled HTML ({len(compiled_html)} bytes), sending to worker")

            png_bytes = await cls._send_to_worker(compiled_html, api_key_setting.setting_value)

            logger.info(f"Screenshot captured successfully ({len(png_bytes)} bytes)")
            return png_bytes

        except ScreenshotServiceError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to capture screenshot: {str(e)}",
                exc_info=True,
                posthog_context={
                    "function": "ScreenshotService.capture",
                    "dashboard_id": str(dashboard_id),
                },
            )
            raise ScreenshotServiceError(f"Screenshot generation failed: {str(e)}") from e

    @classmethod
    async def _send_to_worker(cls, html_content: str, api_key: str) -> bytes:
        """
        Send HTML to Cloudflare Worker and receive PNG.

        Args:
            html_content: Self-contained HTML with embedded data
            api_key: API key for worker authentication

        Returns:
            PNG image bytes

        Raises:
            ScreenshotServiceError: If worker request fails
        """
        try:
            worker_url = get_worker_url()
            async with httpx.AsyncClient(timeout=cls.TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{worker_url}/api/screenshot",
                    json={"html": html_content},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                )

                if response.status_code == 401:
                    raise ScreenshotServiceError("Unauthorized: Invalid API key for worker")

                if response.status_code == 408:
                    raise ScreenshotServiceError(
                        "Screenshot generation timed out. Dashboard may have failed to load or render."
                    )

                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Worker returned status {response.status_code}: {error_detail}")
                    raise ScreenshotServiceError(f"Screenshot service error: {error_detail}")

                return response.content

        except httpx.TimeoutException as e:
            logger.error(f"Timeout calling screenshot worker: {e}")
            raise ScreenshotServiceError(f"Screenshot service timed out after {cls.TIMEOUT_SECONDS} seconds") from e
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to screenshot worker at {worker_url}: {e}")
            raise ScreenshotServiceError(
                f"Screenshot service unavailable at {worker_url}. Check worker deployment."
            ) from e
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling screenshot worker: {e}")
            raise ScreenshotServiceError(f"Screenshot service communication error: {str(e)}") from e

    @classmethod
    async def health_check(cls, session: AsyncSession) -> dict:
        """
        Check if the screenshot service is available and healthy.

        Args:
            session: Database session for API key retrieval

        Returns:
            Dict with status and details
        """
        try:
            api_key_setting = await SettingsService.get_setting_by_key(session, "api_key")
            if not api_key_setting:
                return {"available": False, "reason": "API key not configured"}

            worker_url = get_worker_url()
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{worker_url}/")
                if response.status_code == 200:
                    return {"available": True, "url": worker_url, "worker_status": response.json()}
                return {"available": False, "reason": f"Worker returned status {response.status_code}"}
        except Exception as e:
            return {"available": False, "reason": f"Connection failed: {str(e)}"}
