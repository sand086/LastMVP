"""Standardized error codes — MYEXCELLENCE.md sec 7.2 + Bootstrap P0.7.

Every API error response uses one of these codes.
HTTP status mapping is enforced by helpers in ``response.py``.
"""
from __future__ import annotations


class ErrorCode:
    VALIDATION_FAILED = "VALIDATION_FAILED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RBAC_DENIED = "RBAC_DENIED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    TENANT_MAINTENANCE = "TENANT_MAINTENANCE"
    TERMINAL_STATE = "TERMINAL_STATE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Code → HTTP status (sec 7.2)
HTTP_STATUS = {
    ErrorCode.VALIDATION_FAILED: 422,
    ErrorCode.AUTH_REQUIRED: 401,
    ErrorCode.RBAC_DENIED: 403,
    ErrorCode.RESOURCE_NOT_FOUND: 404,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.TENANT_MAINTENANCE: 503,
    ErrorCode.TERMINAL_STATE: 409,
    ErrorCode.INTERNAL_ERROR: 500,
}


class MyEException(Exception):
    """Base exception for MyExcellence with a typed error code."""

    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


class TerminalStateException(MyEException):
    def __init__(self, message: str = "El recurso está en estado terminal y no puede modificarse.") -> None:
        super().__init__(ErrorCode.TERMINAL_STATE, message)


class RbacDeniedException(MyEException):
    def __init__(self, message: str = "No tiene permisos para acceder a este recurso.") -> None:
        super().__init__(ErrorCode.RBAC_DENIED, message)


class AuthRequiredException(MyEException):
    def __init__(self, message: str = "Autenticación requerida.") -> None:
        super().__init__(ErrorCode.AUTH_REQUIRED, message)


class ResourceNotFoundException(MyEException):
    def __init__(self, message: str = "Recurso no encontrado.") -> None:
        super().__init__(ErrorCode.RESOURCE_NOT_FOUND, message)


class TenantMaintenanceException(MyEException):
    def __init__(self, message: str = "El tenant se encuentra en mantenimiento.") -> None:
        super().__init__(ErrorCode.TENANT_MAINTENANCE, message)


class NotImplementedStubException(Exception):
    """Raised by service stubs during bootstrap — implemented in later prompts."""
