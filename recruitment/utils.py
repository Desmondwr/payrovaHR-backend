import re

SCRIPT_TAG_RE = re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)


def sanitize_text(value: str) -> str:
    if value is None:
        return value
    return str(value).strip()


def sanitize_rich_text(value: str) -> str:
    if value is None:
        return value
    cleaned = SCRIPT_TAG_RE.sub("", str(value))
    return cleaned.strip()
