"""Language purity helpers."""


def required_confidence_for_length(n_chars: int) -> float:
    """Return minimum LID confidence based on text length.

    Shorter texts need higher confidence to compensate for noise.
    """
    if n_chars < 300:
        return 0.95
    if n_chars < 500:
        return 0.90
    if n_chars < 1000:
        return 0.85
    return 0.80
