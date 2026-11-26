from __future__ import annotations

from fastapi import HTTPException, status


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, "details": details or {}},
        )


def bad_request(code: str, message: str, details: dict | None = None) -> AppError:
    return AppError(status.HTTP_400_BAD_REQUEST, code, message, details)


def unauthorized(code: str = "unauthorized", message: str = "Authentication required") -> AppError:
    return AppError(status.HTTP_401_UNAUTHORIZED, code, message)


def forbidden(code: str, message: str, details: dict | None = None) -> AppError:
    return AppError(status.HTTP_403_FORBIDDEN, code, message, details)


def not_found(code: str = "not_found", message: str = "Resource not found") -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, code, message)


def conflict(code: str, message: str, details: dict | None = None) -> AppError:
    return AppError(status.HTTP_409_CONFLICT, code, message, details)


def unprocessable(code: str, message: str, details: dict | None = None) -> AppError:
    return AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, code, message, details)


def too_many(code: str, message: str) -> AppError:
    return AppError(status.HTTP_429_TOO_MANY_REQUESTS, code, message)
