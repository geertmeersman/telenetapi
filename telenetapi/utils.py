"""telenetapi library utils."""


def str_to_float(input) -> float:
    """Transform float to string."""
    return float(input.replace(",", "."))


def kb_to_gb(input) -> float:
    """Transform kb to gb."""
    return round(float(input) / 1048576, 1)
