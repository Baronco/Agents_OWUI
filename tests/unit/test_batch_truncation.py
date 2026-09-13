"""Unit tests for batch truncation policy (spec 020, US2)."""

import src.services.batch as batch


class _Task:
    def __init__(self, model_id="m", message="hi", chat_id=None):
        self.model_id = model_id
        self.message = message
        self.chat_id = chat_id


def test_keeps_first_n_and_reports_trailing_indices():
    tasks = [_Task(f"m{i}") for i in range(4)]

    kept, dropped = batch.truncate_tasks(tasks, 2)

    assert [t.model_id for t in kept] == ["m0", "m1"]
    assert dropped == [2, 3]


def test_exactly_n_drops_nothing():
    tasks = [_Task(f"m{i}") for i in range(3)]

    kept, dropped = batch.truncate_tasks(tasks, 3)

    assert len(kept) == 3
    assert dropped == []


def test_under_limit_drops_nothing():
    tasks = [_Task(f"m{i}") for i in range(2)]

    kept, dropped = batch.truncate_tasks(tasks, 5)

    assert len(kept) == 2
    assert dropped == []


def test_empty_list():
    kept, dropped = batch.truncate_tasks([], 5)

    assert kept == []
    assert dropped == []


def test_zero_limit_drops_everything():
    tasks = [_Task(), _Task()]

    kept, dropped = batch.truncate_tasks(tasks, 0)

    assert kept == []
    assert dropped == [0, 1]


def test_truncation_info_names_count_and_indices():
    info = batch.truncation_info([2, 3], 2)

    assert "2" in info
    assert "2, 3" in info
    assert "MAX_BATCH_SUBAGENTS" in info
