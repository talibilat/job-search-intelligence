"""Typed, sanitized API error responses for the FastAPI boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Final, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.providers.email.provider import (
    EmailProviderAuthError,
    EmailProviderError,
    EmailProviderErrorCode,
    EmailProviderTransientError,
    EmailSyncCursorExpiredError,
)
from app.providers.llm import (
    LLMProviderError,
    LLMProviderRequestError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)


class ApiErrorCode(StrEnum):
    BAD_GATEWAY = "bad_gateway"
    BAD_REQUEST = "bad_request"
    CONFLICT = "conflict"
    EMAIL_AUTHORIZATION_REQUIRED = "email_authorization_required"
    EMAIL_INSUFFICIENT_SCOPE = "email_insufficient_scope"
    EMAIL_INVALID_PROVIDER_RESPONSE = "email_invalid_provider_response"
    EMAIL_PROVIDER_REQUEST_FAILED = "email_provider_request_failed"
    EMAIL_RATE_LIMITED = "email_rate_limited"
    EMAIL_SYNC_CURSOR_EXPIRED = "email_sync_cursor_expired"
    EMAIL_TEMPORARILY_UNAVAILABLE = "email_temporarily_unavailable"
    FORBIDDEN = "forbidden"
    HTTP_ERROR = "http_error"
    INTERNAL_ERROR = "internal_error"
    LLM_PROVIDER_INVALID_RESPONSE = "llm_provider_invalid_response"
    LLM_PROVIDER_REQUEST_FAILED = "llm_provider_request_failed"
    LLM_PROVIDER_TIMEOUT = "llm_provider_timeout"
    LLM_PROVIDER_UNAVAILABLE = "llm_provider_unavailable"
    NOT_FOUND = "not_found"
    SERVICE_UNAVAILABLE = "service_unavailable"
    UNAUTHORIZED = "unauthorized"
    VALIDATION_ERROR = "validation_error"


class ApiErrorDetail(BaseModel):
    field: str | None = None
    message: str
    type: str


class ApiErrorBody(BaseModel):
    code: ApiErrorCode
    message: str
    details: list[ApiErrorDetail] = Field(default_factory=list)


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


class ApiError(Exception):
    """Raise for public API failures that should return a typed error response."""

    def __init__(
        self,
        *,
        status_code: int,
        code: ApiErrorCode,
        message: str,
        details: Sequence[ApiErrorDetail] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = list(details or [])
        super().__init__(message)


_HTTP_STATUS_CODES: Final[dict[int, ApiErrorCode]] = {
    400: ApiErrorCode.BAD_REQUEST,
    401: ApiErrorCode.UNAUTHORIZED,
    403: ApiErrorCode.FORBIDDEN,
    404: ApiErrorCode.NOT_FOUND,
    409: ApiErrorCode.CONFLICT,
    422: ApiErrorCode.VALIDATION_ERROR,
    502: ApiErrorCode.BAD_GATEWAY,
    503: ApiErrorCode.SERVICE_UNAVAILABLE,
}

_HTTP_STATUS_MESSAGES: Final[dict[int, str]] = {
    400: "Bad request.",
    401: "Unauthorized.",
    403: "Forbidden.",
    404: "Not found.",
    409: "Conflict.",
    422: "Request validation failed.",
    502: "Bad gateway.",
    503: "Service unavailable.",
}

_EMAIL_PROVIDER_ERROR_CODES: Final[dict[EmailProviderErrorCode, ApiErrorCode]] = {
    EmailProviderErrorCode.AUTHORIZATION_REQUIRED: ApiErrorCode.EMAIL_AUTHORIZATION_REQUIRED,
    EmailProviderErrorCode.INSUFFICIENT_SCOPE: ApiErrorCode.EMAIL_INSUFFICIENT_SCOPE,
    EmailProviderErrorCode.INVALID_PROVIDER_RESPONSE: ApiErrorCode.EMAIL_INVALID_PROVIDER_RESPONSE,
    EmailProviderErrorCode.PROVIDER_REQUEST_FAILED: ApiErrorCode.EMAIL_PROVIDER_REQUEST_FAILED,
    EmailProviderErrorCode.RATE_LIMITED: ApiErrorCode.EMAIL_RATE_LIMITED,
    EmailProviderErrorCode.SYNC_CURSOR_EXPIRED: ApiErrorCode.EMAIL_SYNC_CURSOR_EXPIRED,
    EmailProviderErrorCode.TEMPORARILY_UNAVAILABLE: ApiErrorCode.EMAIL_TEMPORARILY_UNAVAILABLE,
}

_LLM_PROVIDER_ERROR_CODES: Final[dict[type[LLMProviderError], ApiErrorCode]] = {
    LLMProviderUnavailableError: ApiErrorCode.LLM_PROVIDER_UNAVAILABLE,
    LLMProviderRequestError: ApiErrorCode.LLM_PROVIDER_REQUEST_FAILED,
    LLMProviderResponseError: ApiErrorCode.LLM_PROVIDER_INVALID_RESPONSE,
    LLMProviderTimeoutError: ApiErrorCode.LLM_PROVIDER_TIMEOUT,
}


def _error_response(
    *,
    status_code: int,
    code: ApiErrorCode,
    message: str,
    details: Sequence[ApiErrorDetail] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ApiErrorResponse(
        error=ApiErrorBody(
            code=code,
            message=message,
            details=list(details or []),
        ),
    )
    return JSONResponse(
        content=body.model_dump(mode="json"),
        status_code=status_code,
        headers=headers,
    )


def _validation_details(errors: Sequence[dict[str, Any]]) -> list[ApiErrorDetail]:
    details: list[ApiErrorDetail] = []
    for error in errors:
        location = error.get("loc", "request")
        details.append(
            ApiErrorDetail(
                field=".".join(str(part) for part in location)
                if isinstance(location, list | tuple)
                else str(location),
                message=str(error.get("msg", "Invalid request value.")),
                type=str(error.get("type", "value_error")),
            ),
        )
    return details


def _http_error_code(status_code: int) -> ApiErrorCode:
    if status_code >= 500:
        return ApiErrorCode.INTERNAL_ERROR
    return _HTTP_STATUS_CODES.get(status_code, ApiErrorCode.HTTP_ERROR)


def _http_error_message(exception: StarletteHTTPException) -> str:
    if exception.status_code >= 500:
        return "Internal server error."
    if exception.status_code in _HTTP_STATUS_MESSAGES:
        return _HTTP_STATUS_MESSAGES[exception.status_code]
    return "HTTP error."


def _email_provider_status_code(exception: EmailProviderError) -> int:
    if isinstance(exception, EmailProviderAuthError):
        if exception.error_code is EmailProviderErrorCode.INSUFFICIENT_SCOPE:
            return 403
        return 401
    if isinstance(exception, EmailProviderTransientError):
        if exception.error_code is EmailProviderErrorCode.RATE_LIMITED:
            return 429
        return 503
    if isinstance(exception, EmailSyncCursorExpiredError):
        return 409
    return 502


def _email_provider_error_code(exception: EmailProviderError) -> ApiErrorCode:
    return _EMAIL_PROVIDER_ERROR_CODES.get(
        exception.error_code,
        ApiErrorCode.EMAIL_PROVIDER_REQUEST_FAILED,
    )


def _llm_provider_status_code(exception: LLMProviderError) -> int:
    if isinstance(exception, LLMProviderTimeoutError | LLMProviderUnavailableError):
        return 503
    return 502


def _llm_provider_error_code(exception: LLMProviderError) -> ApiErrorCode:
    return _LLM_PROVIDER_ERROR_CODES.get(
        type(exception),
        ApiErrorCode.LLM_PROVIDER_REQUEST_FAILED,
    )


def register_exception_handlers(app: FastAPI) -> None:
    async def api_error_handler(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        del request
        if not isinstance(exception, ApiError):
            return _error_response(
                status_code=500,
                code=ApiErrorCode.INTERNAL_ERROR,
                message="Internal server error.",
            )
        return _error_response(
            status_code=exception.status_code,
            code=exception.code,
            message=exception.message,
            details=exception.details,
        )

    async def validation_error_handler(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        del request
        if not isinstance(exception, RequestValidationError):
            return _error_response(
                status_code=500,
                code=ApiErrorCode.INTERNAL_ERROR,
                message="Internal server error.",
            )
        return _error_response(
            status_code=422,
            code=ApiErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            details=_validation_details(
                cast(Sequence[dict[str, Any]], exception.errors()),
            ),
        )

    async def http_exception_handler(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        del request
        if not isinstance(exception, StarletteHTTPException):
            return _error_response(
                status_code=500,
                code=ApiErrorCode.INTERNAL_ERROR,
                message="Internal server error.",
            )
        return _error_response(
            status_code=exception.status_code,
            code=_http_error_code(exception.status_code),
            message=_http_error_message(exception),
            headers=exception.headers,
        )

    async def email_provider_error_handler(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        del request
        if not isinstance(exception, EmailProviderError):
            return _error_response(
                status_code=500,
                code=ApiErrorCode.INTERNAL_ERROR,
                message="Internal server error.",
            )
        return _error_response(
            status_code=_email_provider_status_code(exception),
            code=_email_provider_error_code(exception),
            message=exception.public_message,
            details=(
                ApiErrorDetail(
                    field="email_provider",
                    message=exception.user_action.value,
                    type="user_action",
                ),
            ),
        )

    async def llm_provider_error_handler(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        del request
        if not isinstance(exception, LLMProviderError):
            return _error_response(
                status_code=500,
                code=ApiErrorCode.INTERNAL_ERROR,
                message="Internal server error.",
            )
        return _error_response(
            status_code=_llm_provider_status_code(exception),
            code=_llm_provider_error_code(exception),
            message=exception.public_message,
        )

    async def unhandled_exception_handler(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        del request, exception
        return _error_response(
            status_code=500,
            code=ApiErrorCode.INTERNAL_ERROR,
            message="Internal server error.",
        )

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(EmailProviderError, email_provider_error_handler)
    app.add_exception_handler(LLMProviderError, llm_provider_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
