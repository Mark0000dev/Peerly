from http import HTTPStatus

from starlette.responses import JSONResponse

from studymate.application.idempotency import IdempotencyConflictError
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.presentation.problems import problem

STUDENT_ERRORS = (UnauthenticatedError, StudentActionDeniedError, IdempotencyConflictError)


def student_problem(error: Exception) -> JSONResponse | None:
    if isinstance(error, UnauthenticatedError):
        return problem(HTTPStatus.UNAUTHORIZED, "unauthenticated")
    if isinstance(error, StudentActionDeniedError):
        return problem(HTTPStatus.FORBIDDEN, "student_action_not_allowed")
    if isinstance(error, IdempotencyConflictError):
        return problem(HTTPStatus.CONFLICT, "idempotency_conflict")
    return None
