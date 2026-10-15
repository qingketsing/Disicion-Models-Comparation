import pytest

from orchestration.jev_capacity_driver import formal_selection
from orchestration.prepare_jev_capacity import quota_screen


def test_jev_quota_screen_includes_three_additional_attempts_and_output_tokens():
    report = quota_screen([1, 8], 3, 80, 100000, 2566)
    assert report['projected_attempt_rps'] == 32
    assert report['projected_token_rps'] == 82112
    # Logical16 RPS fits the published request quota even after retries,
    # but total token usage for initial plus three attempts does not.
    with pytest.raises(ValueError, match='token budget'):
        quota_screen([16], 3, 80, 100000, 2566)
    with pytest.raises(ValueError, match='attempt or token budget'):
        quota_screen([32], 3, 80, 1000000, 2566)


@pytest.mark.parametrize('rates', [[], [0], [-1], [float('inf')], [float('nan')]])
def test_jev_quota_screen_rejects_unknown_or_invalid_budget(rates):
    with pytest.raises(ValueError, match='finite and positive'):
        quota_screen(rates, 3, 80, 100000, 2566)


def test_jev_quota_screen_rejects_different_retry_strategy():
    with pytest.raises(ValueError, match='three additional'):
        quota_screen([1], 0, 80, 100000, 2566)


@pytest.mark.parametrize('passing,expected', [([], [1]), ([1], [1, 2]),
                                           ([1, 2], [2, 4]), ([1, 2, 4, 8], [8])])
def test_jev_formal_selection_uses_three_repeat_evidence_and_minimum_fallback(passing, expected):
    rates = {rate: {'all_repeats_pass': rate in passing} for rate in [1, 2, 4, 8]}
    assert formal_selection(rates)[0] == expected
