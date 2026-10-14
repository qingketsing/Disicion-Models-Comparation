from orchestration.stage_watchdog import find_failure


def test_first_transport_failure_is_not_hidden_by_recovery():
    rows = [{"status": status} for status in ["ok", "network_error", "ok"]]
    assert find_failure(rows) is None
    assert find_failure(rows, stop_transport_error=True) is rows[1]


def test_timeout_warmup_and_previous_policy():
    assert find_failure([{"status": "timeout"}], stop_transport_error=True)
    rows = [{"status": status} for status in ["network_error", "timeout", "network_error"]]
    assert find_failure(rows) is rows[-1]


def test_http_and_invalid_output_policy_unchanged():
    assert find_failure([{"status": "http_error"}])
    assert find_failure([{"status": "invalid_output"}]) is None
    assert find_failure([{"status": "invalid_output"}], stop_invalid=True)
    assert find_failure([{"status": "ok"}], True, True) is None
