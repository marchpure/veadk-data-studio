"""PDF service for generating dashboard exports via Cloudflare Worker."""

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


class PDFServiceError(Exception):
    """Raised when PDF generation fails."""

    pass


class PDFService:
    """Service for generating PDF exports of dashboards via Cloudflare Worker."""

    TIMEOUT_SECONDS = 60

    @classmethod
    async def generate(cls, session: AsyncSession, dashboard_id: UUID, version: int | None = None) -> bytes:
        """
        Generate a PDF export of a dashboard via Cloudflare Worker.

        Args:
            session: Database session
            dashboard_id: UUID of the dashboard/notebook to export
            version: Optional specific version to export (defaults to latest)

        Returns:
            PDF file as bytes

        Raises:
            PDFServiceError: If PDF generation fails or worker is unavailable
        """
        try:
            logger.info(f"Starting PDF generation for dashboard {dashboard_id}")

            api_key_setting = await SettingsService.get_setting_by_key(session, "api_key")
            if not api_key_setting:
                raise PDFServiceError("API key not configured. Cannot authenticate with worker.")

            compiled_html = await CompiledHtmlExportService.generate_compiled_html(
                session=session, notebook_id=str(dashboard_id), version=version, disable_animations=True
            )

            logger.info(f"Generated compiled HTML ({len(compiled_html)} bytes), sending to worker")

            pdf_bytes = await cls._send_to_worker(compiled_html, api_key_setting.setting_value)

            logger.info(f"PDF generated successfully ({len(pdf_bytes)} bytes)")
            return pdf_bytes

        except PDFServiceError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to generate PDF: {str(e)}",
                exc_info=True,
                posthog_context={
                    "function": "PDFService.generate",
                    "dashboard_id": str(dashboard_id),
                },
            )
            raise PDFServiceError(f"PDF generation failed: {str(e)}") from e

    @classmethod
    async def _send_to_worker(cls, html_content: str, api_key: str) -> bytes:
        """
        Send HTML to Cloudflare Worker and receive PDF.

        Args:
            html_content: Self-contained HTML with embedded data
            api_key: API key for worker authentication

        Returns:
            PDF file bytes

        Raises:
            PDFServiceError: If worker request fails
        """
        try:
            worker_url = get_worker_url()
            async with httpx.AsyncClient(timeout=cls.TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{worker_url}/api/pdf",
                    json={"html": html_content},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                )

                if response.status_code == 401:
                    raise PDFServiceError("Unauthorized: Invalid API key for worker")

                if response.status_code == 408:
                    raise PDFServiceError("PDF generation timed out. Dashboard may have failed to load or render.")

                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Worker returned status {response.status_code}: {error_detail}")
                    raise PDFServiceError(f"PDF service error: {error_detail}")

                return response.content

        except httpx.TimeoutException as e:
            logger.error(f"Timeout calling PDF worker: {e}")
            raise PDFServiceError(f"PDF service timed out after {cls.TIMEOUT_SECONDS} seconds") from e
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to PDF worker at {worker_url}: {e}")
            raise PDFServiceError(f"PDF service unavailable at {worker_url}. Check worker deployment.") from e
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling PDF worker: {e}")
            raise PDFServiceError(f"PDF service communication error: {str(e)}") from e
