"""
Authentication Middleware for Backend API
Validates API key for external requests while exempting internal frontend requests.
"""

import logging
from typing import Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import get_settings

logger = logging.getLogger(__name__)


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to authenticate API requests using API key header.

    Exempts requests from internal frontend (via Docker network) and validates
    API key in X-API-Key header for all other requests.
    """

    def __init__(self, app, api_key: str = None):
        super().__init__(app)
        self.api_key = api_key or get_settings().api_key

        # Log warning if no API key is configured
        if not self.api_key:
            logger.warning("⚠️  No API key configured - API authentication is DISABLED")
        else:
            logger.info("🔐 API key authentication enabled")

    async def dispatch(self, request: Request, call_next: Callable):
        """
        Process request and validate API key if required.

        Exempts:
        - Requests from internal Docker network (frontend via service name)
        - Health check endpoints
        """

        # Skip authentication if no API key is configured
        if not self.api_key:
            return await call_next(request)

        # Get client host
        client_host = request.client.host if request.client else None

        # Check if request is from internal Docker network
        is_internal = self._is_internal_request(request, client_host)

        # Exempt internal requests and health endpoints
        if is_internal or self._is_health_endpoint(request.url.path):
            logger.debug(f"Exempting request from {client_host}: {request.method} {request.url.path}")
            return await call_next(request)

        # Validate API key for external requests
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            logger.warning(f"Missing API key from {client_host}: {request.method} {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "detail": "Missing API key. Please provide X-API-Key header.",
                    "error": "unauthorized"
                }
            )

        if api_key != self.api_key:
            logger.warning(f"Invalid API key from {client_host}: {request.method} {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": "Invalid API key",
                    "error": "forbidden"
                }
            )

        # API key is valid
        logger.debug(f"Valid API key from {client_host}: {request.method} {request.url.path}")
        return await call_next(request)

    def _is_internal_request(self, request: Request, client_host: str) -> bool:
        """
        Determine if request is from internal Docker network.

        Checks:
        1. If client is from Docker internal network (172.x.x.x range or localhost)
        2. If Host header contains internal service name
        """
        if not client_host:
            return False

        # Check if client is from Docker internal network
        # Docker default bridge network uses 172.17.0.0/16
        # Docker compose networks typically use 172.18.0.0/16 and up
        is_docker_network = (
            client_host.startswith("172.") or  # Docker networks
            client_host.startswith("127.") or  # Localhost
            client_host == "localhost"
        )

        # Also check Host header for internal service name
        host_header = request.headers.get("host", "")
        is_internal_host = (
            "backend:" in host_header or  # Internal Docker service name
            host_header.startswith("backend") or
            "localhost" in host_header or
            "127.0.0.1" in host_header
        )

        return is_docker_network or is_internal_host

    def _is_health_endpoint(self, path: str) -> bool:
        """Check if the path is a health check endpoint"""
        health_endpoints = ["/", "/health", "/api/health"]
        return path in health_endpoints or path.startswith("/api/health")
