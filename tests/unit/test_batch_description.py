"""Unit tests for the batch endpoint tool description (spec 020, US2/US3)."""

import src.services.batch as batch


def test_description_states_configured_maximum():
    text = batch.build_batch_description(3)

    assert "3" in text
    assert "MAX_BATCH_SUBAGENTS" in text


def test_description_explains_truncation_rule():
    text = batch.build_batch_description(5).lower()

    assert "first 5" in text
    assert "dropped" in text
    assert "info" in text


def test_description_documents_task_fields():
    text = batch.build_batch_description(5)

    assert "message" in text
    assert "model_id" in text
    assert "chat_id" in text


def test_description_mentions_parallel_and_response_shape():
    text = batch.build_batch_description(5).lower()

    assert "parallel" in text or "concurrent" in text
    assert "assistant_response" in text
    assert "subagent_chat_id" in text
