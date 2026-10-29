from datetime import UTC, datetime

import pytest

from runner.run_code import exec_time, status_map


@pytest.mark.parametrize("exit_code,is_oom, expected_string", [
    (137, True, "oom"),
    (0, False, "ok"),
    (0, True, "oom"),
    (125, False,"internal_error"),
    (126, False, "internal_error"),
    (127, False, "internal_error"),
    (124, False, "timed_out"),
    (1, False, "runtime_error"),
    (137, False, "runtime_error")
])  
def test_status_map(exit_code, is_oom, expected_string):
    assert status_map(exit_code, is_oom) == expected_string


def test_exec_time_truncates_nanoseconds():
    result = exec_time("2026-10-18T09:00:00.123456789Z")
    assert result == datetime(2026, 10, 18, 9, 0, 0, 123456, tzinfo=UTC)