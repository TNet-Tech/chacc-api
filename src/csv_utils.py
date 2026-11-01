def parse_csv(value):
    """Split a comma-separated setting into a list; empty or '*' means allow all."""
    items = [part.strip() for part in (value or "").split(",") if part.strip()]
    if not items or "*" in items:
        return ["*"]
    return items
