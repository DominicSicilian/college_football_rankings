"""Shared model configuration values for prediction scripts."""

from typing import Optional

HOME_FIELD_X_DEFAULT = 0.067059
WEEK1_SPI_WEIGHT = 0.7
WEEK1_TALENT_WEIGHT = 0.3

# No matchup is a certainty. An FBS team hosting an FCS opponent comes out of the
# model at a flat 100.0 / 0.0, which reads as a guarantee rather than a heavy
# favorite. Clamping the displayed probability keeps the extremes honest and
# keeps the two sides summing to 100.
WIN_PROB_MIN_PCT = 0.1
WIN_PROB_MAX_PCT = 99.9


def clamp_win_prob_pct(value: Optional[float]) -> Optional[float]:
    """Clamp a 0-100 win probability into [WIN_PROB_MIN_PCT, WIN_PROB_MAX_PCT]."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return max(WIN_PROB_MIN_PCT, min(WIN_PROB_MAX_PCT, value))


def clamp_win_prob_fraction(value: Optional[float]) -> Optional[float]:
    """Same clamp for probabilities expressed as a 0-1 fraction."""
    result = clamp_win_prob_pct(None if value is None else float(value) * 100.0)
    return None if result is None else result / 100.0
