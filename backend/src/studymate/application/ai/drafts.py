import hashlib
import json

from studymate.application.ai.ports import DraftSourceIntent, StudentSubmission
from studymate.domain.ai.tasks import DraftSnapshotSource


def draft_snapshot_source(submission: StudentSubmission) -> DraftSnapshotSource:
    """Server-derived actual input hash, not client authority or an actor/resource grant.

    Exact validated strings, no trim/NFC mutation; canonical UUID candidate subset sorted
    lexically. UTF-8 compact JSON array (ensure_ascii=False), SHA256 lowercase hex.
    Client only needs to retain returned hash plus its submitted draft id/revision.
    """
    if not isinstance(submission.source, DraftSourceIntent):
        raise ValueError("An explicit unsaved draft source is required")
    parts = (
        "peerly-ai-draft-v1",
        submission.kind.value,
        submission.target.value,
        submission.text or "",
        submission.label or "",
        *sorted(str(candidate) for candidate in submission.candidate_ids),
    )
    digest = hashlib.sha256(
        json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return DraftSnapshotSource(submission.source.id, submission.source.version, digest)
