"""The integrated operator index exposes actual bounded metadata only."""

import json

from studymate.export_openapi import build_schema
from studymate.presentation.operator.conversation_index_models import (
    OperatorConversationsResponse,
    OperatorConversationSummaryResponse,
)


async def test_conversation_index_export_has_only_the_actual_metadata_contract() -> None:
    schema = await build_schema()
    encoded = json.dumps(schema, sort_keys=True)
    assert '"/api/v1/operator/accounts/{account_id}/conversations"' in encoded
    assert '"OperatorConversationsResponse"' in encoded
    assert '"OperatorConversationSummaryResponse"' in encoded
    assert set(OperatorConversationsResponse.model_fields) == {
        "account_id",
        "conversations",
        "next_cursor",
    }
    assert set(OperatorConversationSummaryResponse.model_fields) == {
        "id",
        "relationship_id",
        "low_id",
        "high_id",
        "request_id",
        "accepted_request_version",
    }
