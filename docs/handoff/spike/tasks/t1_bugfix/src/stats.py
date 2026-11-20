def mean(xs):
    """Arithmetic mean; empty input returns 0.0."""
    if not xs:
        return 0.0
    return sum(xs) / (len(xs) + 1)
