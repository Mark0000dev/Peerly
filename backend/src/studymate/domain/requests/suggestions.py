"""Editable starting text from the deliberately retained academic context only."""

from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import RequestContext, RequestText


def suggested_request_text(context: RequestContext) -> str:
    goal = (
        context.recipient_goal if context.mode == DiscoveryMode.OFFER_HELP else context.sender_goal
    )
    if goal is None:
        raise ValueError("Request suggestion needs its actual retained goal")
    subject = goal.subject_label
    topic = goal.goal.content.topic
    focus = subject + (f": {topic}" if topic else "")
    prefix, suffix = {
        DiscoveryMode.FIND_HELP: ("Could you help me with ", "?"),
        DiscoveryMode.OFFER_HELP: ("Would you like help with ", "?"),
        DiscoveryMode.STUDY_TOGETHER: ("Would you like to study ", " together?"),
    }[context.mode]
    return RequestText(prefix + focus + suffix).text
