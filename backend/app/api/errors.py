from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Final, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiErrorCode(StrEnum):
    BAD_REQUEST = "bad_request"
    CONFLICT = "conflict"
    FORBIDDEN = "forbidden"
    HTTP_ERROR = "http_error"
    INTERNAL_ERROR = "internal_error"
    NOT_FOUND = "not_found"
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
}

_HTTP_STATUS_MESSAGES: Final[dict[int, str]] = {
    400: "Bad request.",
    401: "Unauthorized.",
    403: "Forbidden.",
    404: "Not found.",
    409: "Conflict.",
    422: "Request validation failed.",
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


def _field_from_location(location: object) -> str:
    if isinstance(location, (list, tuple)):
        return ".".join(str(part) for part in location)
    return str(location)


def _validation_details(errors: Sequence[dict[str, Any]]) -> list[ApiErrorDetail]:
    details: list[ApiErrorDetail] = []
    for error in errors:
        details.append(
            ApiErrorDetail(
                field=_field_from_location(error.get("loc", "request")),
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
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
