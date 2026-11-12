"""Bound JSON-command memory/wait time; binary uploads go directly to storage."""

import asyncio
from http import HTTPStatus

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from studymate.presentation.problems import problem

COMMAND_BODY_BYTES = 8192
SUPPORT_BODY_BYTES = 32768
OBSERVATION_BODY_BYTES = 16384
BODY_TIMEOUT_SECONDS = 5


def _operator_ban(scope: Scope) -> bool:
    if scope["type"] != "http" or scope["method"] != "PUT":
        return False
    match scope["path"].split("/"):
        case ["", "api", "v1", "operator", "accounts", account_id, "ban"]:
            return bool(account_id)
        case _:
            return False


def _operator_support_status(scope: Scope) -> bool:
    if scope["type"] != "http" or scope["method"] != "PUT":
        return False
    match scope["path"].split("/"):
        case ["", "api", "v1", "operator", "cases", case_id, "status"]:
            return bool(case_id)
        case _:
            return False


def _operator_membership_verification(scope: Scope) -> bool:
    if scope["type"] != "http" or scope["method"] != "POST":
        return False
    match scope["path"].split("/"):
        case ["", "api", "v1", "operator", "accounts", account_id, "membership-verifications"]:
            return bool(account_id)
        case _:
            return False


def _operator_human_review(scope: Scope) -> bool:
    if scope["type"] != "http" or scope["method"] != "POST":
        return False
    match scope["path"].split("/"):
        case ["", "api", "v1", "operator", "accounts", account_id, "photo-reviews"]:
            return bool(account_id)
        case ["", "api", "v1", "operator", "reports", report_id, "reviews"]:
            return bool(report_id)
        case _:
            return False


class JsonCommandBodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in {"POST", "PUT", "PATCH"}
            or (
                not scope["path"].startswith(
                    (
                        "/api/v1/auth/",
                        "/api/v1/me/",
                        "/api/v1/media/",
                        "/api/v1/ai/",
                        "/api/v1/discovery/",
                        "/api/v1/requests/",
                        "/api/v1/conversations/",
                    )
                )
                and scope["path"]
                not in {
                    "/api/v1/reports",
                    "/api/v1/requests",
                    "/api/v1/support-context",
                    "/api/v1/support-cases",
                    "/api/v1/telemetry/events",
                }
                and not _operator_ban(scope)
                and not _operator_support_status(scope)
                and not _operator_membership_verification(scope)
                and not _operator_human_review(scope)
            )
        ):
            await self.app(scope, receive, send)
            return
        if (
            _operator_ban(scope)
            or _operator_support_status(scope)
            or _operator_membership_verification(scope)
            or _operator_human_review(scope)
            or (
                scope["path"].startswith("/api/v1/conversations/")
                and scope["path"].endswith(
                    (
                        "/messages",
                        "/goal-shares",
                        "/read-position",
                        "/study-outcome",
                        "/feedback",
                        "/study-prompt-visits",
                        "/image-preparations",
                    )
                )
            )
            or scope["path"].startswith(
                (
                    "/api/v1/auth/email-challenges",
                    "/api/v1/me/blocks/",
                    "/api/v1/discovery/passes/",
                    "/api/v1/requests/",
                )
            )
            or scope["path"]
            in (
                "/api/v1/me/registration",
                "/api/v1/me/notification-preference",
                "/api/v1/me/support-cases",
                "/api/v1/support-context",
                "/api/v1/support-cases",
                "/api/v1/telemetry/events",
                "/api/v1/me/deletion",
                "/api/v1/me/deletion-workflows",
                "/api/v1/media/uploads",
                "/api/v1/me/profile",
                "/api/v1/me/goal",
                "/api/v1/me/goal/complete",
                "/api/v1/me/help-subjects",
                "/api/v1/me/visibility",
                "/api/v1/ai/jobs",
                "/api/v1/reports",
                "/api/v1/requests",
            )
        ):
            content_type = Headers(scope=scope).get("content-type", "").split(";", 1)[0].lower()
            if content_type != "application/json":
                await self._reject(scope, receive, send, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
        body_limit = {
            "/api/v1/support-cases": SUPPORT_BODY_BYTES,
            "/api/v1/me/support-cases": SUPPORT_BODY_BYTES,
            "/api/v1/telemetry/events": OBSERVATION_BODY_BYTES,
        }.get(scope["path"], COMMAND_BODY_BYTES)
        body = bytearray()
        try:
            async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk: object = message.get("body", b"")
                    if not isinstance(chunk, bytes):
                        raise ValueError("Invalid ASGI body message")
                    if len(body) + len(chunk) > body_limit:
                        await self._reject(
                            scope, receive, send, HTTPStatus.REQUEST_ENTITY_TOO_LARGE
                        )
                        return
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await self._reject(scope, receive, send, HTTPStatus.REQUEST_TIMEOUT)
            return
        if body and (
            (
                scope["path"].startswith("/api/v1/conversations/")
                and "/messages/" in scope["path"]
                and scope["path"].endswith("/report-contexts")
            )
            or scope["path"] in ("/api/v1/auth/logout", "/api/v1/me/registration-context")
            or scope["path"].startswith("/api/v1/media/uploads/")
            or (scope["path"].startswith("/api/v1/ai/jobs/") and scope["path"].endswith("/cancel"))
            or (
                scope["path"].startswith("/api/v1/conversations/")
                and "/image-preparations/" in scope["path"]
                and scope["path"].endswith(("/finalize", "/upload-access"))
            )
            or (
                scope["path"].startswith("/api/v1/conversations/")
                and "/message-operations/" in scope["path"]
                and scope["path"].endswith("/cancel")
            )
        ):
            await self._reject(scope, receive, send, HTTPStatus.BAD_REQUEST)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send, status: HTTPStatus) -> None:
        code = (
            "command_body_rejected"
            if scope["path"].startswith(
                (
                    "/api/v1/media/",
                    "/api/v1/ai/",
                    "/api/v1/me/blocks/",
                    "/api/v1/discovery/",
                    "/api/v1/requests/",
                    "/api/v1/conversations/",
                )
            )
            or _operator_ban(scope)
            or _operator_support_status(scope)
            or _operator_membership_verification(scope)
            or _operator_human_review(scope)
            or scope["path"]
            in {
                "/api/v1/reports",
                "/api/v1/requests",
                "/api/v1/support-context",
                "/api/v1/support-cases",
                "/api/v1/telemetry/events",
                "/api/v1/me/support-cases",
                "/api/v1/me/notification-preference",
                "/api/v1/me/deletion",
                "/api/v1/me/deletion-workflows",
            }
            else "auth_body_rejected"
        )
        response = problem(status, code)
        await response(scope, receive, send)
