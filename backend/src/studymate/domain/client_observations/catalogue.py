"""Closed semantic observation vocabulary. Values are client claims, not commits."""

from enum import StrEnum


class Screen(StrEnum):
    WELCOME = "welcome"
    VERIFICATION = "verification"
    ONBOARDING = "onboarding"
    DISCOVER = "discover"
    REQUESTS = "requests"
    CHATS = "chats"
    CONVERSATION = "conversation"
    PROFILE = "profile"
    STUDY = "study"
    NOTIFICATIONS = "notifications"
    SUPPORT = "support"
    HELP = "help"
    TERMS = "terms"
    PRIVACY = "privacy"
    OPERATOR = "operator"
    UNKNOWN = "unknown"


class Action(StrEnum):
    NAVIGATE = "navigate"
    SUBMIT = "submit"
    RETRY = "retry"
    CANCEL = "cancel"
    APPLY = "apply"
    DISMISS = "dismiss"
    LOAD_MORE = "load_more"
    UPLOAD = "upload"
    PERMISSION_REQUEST = "permission_request"
    OPEN_SETTINGS = "open_settings"


class ObservedOutcome(StrEnum):
    INVOKED = "invoked"
    SUCCEEDED = "succeeded_observed"
    REJECTED = "rejected_observed"
    FAILED = "failed_observed"
    CANCELLED = "cancelled_observed"
    UNKNOWN = "unknown"


class Metric(StrEnum):
    ROUTE_READY = "route_ready"
    LCP = "lcp"
    INP = "inp"
    FCP = "fcp"
    TTFB = "ttfb"
    CLS = "cls"


class ErrorCategory(StrEnum):
    NETWORK = "network"
    HTTP = "http"
    TIMEOUT = "timeout"
    OFFLINE = "offline"
    JAVASCRIPT = "javascript"
    RENDER = "render"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


class HttpMethod(StrEnum):
    GET = "GET"
    HEAD = "HEAD"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    OPTIONS = "OPTIONS"


class ApiRoute(StrEnum):
    IDENTITY = "identity"
    VERIFICATION = "verification"
    REGISTRATION = "registration"
    PROFILE = "profile"
    STUDY = "study"
    DISCOVERY = "discovery"
    REQUESTS = "requests"
    CONVERSATIONS = "conversations"
    MEDIA = "media"
    SUPPORT = "support"
    NOTIFICATIONS = "notifications"
    AI = "ai"
    OPERATOR = "operator"
    OTHER = "other"


class StatusClass(StrEnum):
    INFORMATIONAL = "1xx"
    SUCCESS = "2xx"
    REDIRECT = "3xx"
    CLIENT_ERROR = "4xx"
    SERVER_ERROR = "5xx"
    NETWORK = "network"
    CANCELLED = "cancelled"


class QualityReason(StrEnum):
    OVERFLOW = "overflow"
    INVALID = "invalid"
    EXPIRED = "expired"
    REJECTED = "rejected"
    EXHAUSTED = "exhausted"
    UNAVAILABLE = "unavailable"
