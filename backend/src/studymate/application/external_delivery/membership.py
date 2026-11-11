"""A committed membership fact is not evidence that OTP was consumed."""

import re

from studymate.domain.external_delivery.sources import MembershipEvidence

_MANUAL = re.compile(r"smv1:[0-9a-f]{32}:(p|c[A-Za-z0-9_-]{22}):[A-Za-z0-9_-]{1,38}")


def membership_evidence(
    occurrence_key: str, *, consumed_challenge_proven: bool
) -> MembershipEvidence:
    manual = _MANUAL.fullmatch(occurrence_key)
    if manual is not None:
        return (
            MembershipEvidence.MANUAL_PLACEHOLDER
            if manual.group(1) == "p"
            else MembershipEvidence.MANUAL_CHALLENGE
        )
    if occurrence_key == "institutional_binding" and consumed_challenge_proven:
        return MembershipEvidence.OTP
    return MembershipEvidence.UNKNOWN
