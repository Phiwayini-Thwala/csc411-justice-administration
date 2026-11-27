"""Application errors. Every error is rendered as the shared body
{"error": "NOT_FOUND", "message": "..."} (design 9.2)."""


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationFailed(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    """Wrong state / duplicate (design 5.3, 11)."""
    status_code = 409
    code = "CONFLICT"


class BadGatewayError(AppError):
    """The Correctional service failed (design 11)."""
    status_code = 502
    code = "BAD_GATEWAY"
