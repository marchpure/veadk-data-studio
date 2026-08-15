"""Service for downloading files from public URLs."""

from __future__ import annotations

import io
import ipaddress
import logging
import socket
import zipfile
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class URLDownloadService:
    """Service for downloading files from public URLs."""

    # Supported file extensions by type
    ALLOWED_EXTENSIONS = {"csv": [".csv"], "excel": [".xlsx", ".xls"], "parquet": [".parquet"], "json": [".json"]}

    @staticmethod
    def detect_file_type(filename: str) -> str | None:
        """
        Detect file type from filename extension.

        Args:
            filename: File name to detect type from

        Returns:
            File type (csv, excel, parquet, json) or None if unknown
        """
        filename_lower = filename.lower()

        for file_type, extensions in URLDownloadService.ALLOWED_EXTENSIONS.items():
            if any(filename_lower.endswith(ext) for ext in extensions):
                return file_type

        return None

    @staticmethod
    async def download_file_from_url(url: str, expected_file_type: str | None = None) -> tuple[bytes, str]:
        """
        Download file from URL and optionally validate type.

        Args:
            url: Public URL to download from
            expected_file_type: Optional expected file type (csv, excel, parquet, json).
                               If None, no validation is performed and type is auto-detected.

        Returns:
            Tuple of (file_content, filename)

        Raises:
            ValueError: If URL is invalid or file validation fails
            httpx.HTTPError: If download fails
        """
        # Validate URL
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Invalid URL scheme. Only HTTP/HTTPS supported: {url}")

        # Security: Block private/local IPs with DNS rebinding protection
        hostname = parsed.netloc.split(":")[0]
        URLDownloadService._resolve_and_validate_hostname(hostname)

        filename = parsed.path.split("/")[-1] or "downloaded_file"

        if expected_file_type:
            allowed_extensions = URLDownloadService.ALLOWED_EXTENSIONS.get(expected_file_type, [])
            is_zip = filename.lower().endswith(".zip")
            is_valid_file = any(filename.lower().endswith(ext) for ext in allowed_extensions)

            if not is_zip and not is_valid_file:
                raise ValueError(
                    f"URL must point to a valid {expected_file_type.upper()} file or ZIP archive. "
                    f"Allowed: {', '.join(allowed_extensions)} or .zip. "
                    f"Found: {filename}"
                )

        verify_ssl = URLDownloadService._get_ssl_verify_setting()
        async with httpx.AsyncClient(follow_redirects=True, verify=verify_ssl) as client:
            try:
                logger.info(f"Starting download from URL: {url}")

                # Stream download with no size limit (can handle GBs)
                file_content = bytearray()
                async with client.stream("GET", url, timeout=None) as response:
                    response.raise_for_status()

                    # Download in chunks
                    chunk_count = 0
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):  # 1MB chunks
                        file_content.extend(chunk)
                        chunk_count += 1
                        if chunk_count % 100 == 0:  # Log progress every 100MB
                            logger.info(f"Downloaded {len(file_content) / (1024 * 1024):.1f} MB from {url}")

                if len(file_content) == 0:
                    raise ValueError("Downloaded file is empty")

                logger.info(
                    f"Successfully downloaded file from {url}: {len(file_content) / (1024 * 1024):.2f} MB ({filename})"
                )
                return bytes(file_content), filename

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error downloading from {url}: {e}")
                raise ValueError(f"Failed to download file: HTTP {e.response.status_code} - {e.response.reason_phrase}")
            except httpx.RequestError as e:
                logger.error(f"Request error downloading from {url}: {e}")
                raise ValueError(f"Failed to download file: {str(e)}")

    @staticmethod
    def extract_zip_files(zip_content: bytes, expected_file_type: str | None = None) -> list[tuple[bytes, str]]:
        """
        Extract all files from a ZIP archive.

        Args:
            zip_content: ZIP file content as bytes
            expected_file_type: Optional expected file type (csv, excel, parquet, json).
                               If None, all supported file types are extracted.

        Returns:
            List of tuples: (file_content, filename)

        Raises:
            ValueError: If ZIP is invalid or contains incompatible files
        """
        try:
            zip_buffer = io.BytesIO(zip_content)
            extracted_files = []

            with zipfile.ZipFile(zip_buffer, "r") as zip_file:
                file_list = [f for f in zip_file.namelist() if not f.endswith("/")]

                if len(file_list) == 0:
                    raise ValueError("ZIP file is empty")

                if expected_file_type:
                    allowed_extensions = URLDownloadService.ALLOWED_EXTENSIONS.get(expected_file_type, [])
                else:
                    allowed_extensions = [
                        ext for exts in URLDownloadService.ALLOWED_EXTENSIONS.values() for ext in exts
                    ]

                for file_name in file_list:
                    # Skip macOS metadata files
                    if file_name.startswith("__MACOSX/") or file_name.startswith("."):
                        logger.info(f"Skipping metadata file: {file_name}")
                        continue

                    if not any(file_name.lower().endswith(ext) for ext in allowed_extensions):
                        if expected_file_type:
                            raise ValueError(
                                f"File '{file_name}' in ZIP does not match expected type {expected_file_type.upper()}. "
                                f"All files must be {', '.join(URLDownloadService.ALLOWED_EXTENSIONS.get(expected_file_type, []))}"
                            )
                        else:
                            logger.warning(f"Skipping unsupported file in ZIP: {file_name}")
                            continue

                    # Extract file content
                    file_content = zip_file.read(file_name)

                    if len(file_content) == 0:
                        logger.warning(f"Skipping empty file in ZIP: {file_name}")
                        continue

                    clean_filename = file_name.split("/")[-1]
                    extracted_files.append((file_content, clean_filename))

                    logger.info(f"Extracted from ZIP: {clean_filename} ({len(file_content) / (1024 * 1024):.2f} MB)")

            if len(extracted_files) == 0:
                raise ValueError("No valid files found in ZIP archive")

            logger.info(f"Successfully extracted {len(extracted_files)} file(s) from ZIP")
            return extracted_files

        except zipfile.BadZipFile:
            raise ValueError("Invalid ZIP file format")
        except Exception as e:
            logger.error(f"Error extracting ZIP file: {str(e)}")
            raise ValueError(f"Failed to extract ZIP file: {str(e)}")

    @staticmethod
    def _is_private_url(hostname: str) -> bool:
        """Check if hostname points to private/local network."""
        # Block localhost variations
        if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
            return True

        # Block private IP ranges
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            return False

    @staticmethod
    def _resolve_and_validate_hostname(hostname: str) -> str:
        """
        Resolve hostname to IP and validate it's not a private address.

        This provides DNS rebinding protection by checking the resolved IP
        before making the actual request.

        Args:
            hostname: The hostname to resolve and validate

        Returns:
            The resolved IP address if valid

        Raises:
            ValueError: If the resolved IP is private/local
        """
        if URLDownloadService._is_private_url(hostname):
            raise ValueError(f"Access to private/local URLs not allowed: {hostname}")

        try:
            resolved_ip = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(resolved_ip)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise ValueError(f"DNS resolved to private IP: {resolved_ip}")
            return resolved_ip
        except socket.gaierror:
            pass

        return hostname

    @staticmethod
    def _get_ssl_verify_setting() -> bool:
        """
        Determine SSL verification setting based on deployment mode.

        Desktop/Community modes can skip SSL verify for development convenience.
        Self-hosted should always verify SSL.
        """
        from server.utils.config_loader import is_self_hosted

        return is_self_hosted()
