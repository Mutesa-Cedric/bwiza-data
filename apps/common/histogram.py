"""Simple numeric bucketing for histograms."""

LID_BINS = [0.80, 0.85, 0.90, 0.95, 1.0]
LENGTH_BINS = [200, 500, 1000, 2000, 5000, 10000]


def bucket(value: float, bins: list[float]) -> str:
    """Assign a value to a bucket label. Values below first bin go to '<first'."""
    if value < bins[0]:
        return f"<{bins[0]}"
    for i in range(len(bins) - 1):
        if value < bins[i + 1]:
            return f"{bins[i]}-{bins[i + 1]}"
    return f">={bins[-1]}"


def update_histogram(hist: dict, value: float, bins: list[float]) -> None:
    """Increment the count for the bucket this value falls into."""
    label = bucket(value, bins)
    hist[label] = hist.get(label, 0) + 1
