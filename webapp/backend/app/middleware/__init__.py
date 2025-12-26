"""
Middleware package for FastAPI application
"""

from .auth import APIKeyAuthMiddleware

__all__ = ["APIKeyAuthMiddleware"]
