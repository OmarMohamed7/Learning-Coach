import re

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(the\s+)?system\s+prompt",
    r"reveal\s+(the\s+)?system\s+prompt",
    r"show\s+(me\s+)?your\s+instructions",
    r"developer\s+message",
    r"system\s+message",
    r"jailbreak",
]


def query_audit(query: str) -> str:
    if not isinstance(query, str):
        raise ValueError("Query must be a string")

    query = query.lower().strip()

    if not query:
        raise ValueError("Query cannot be empty")

    if len(query) > 1000:
        raise ValueError("Query is too long")

    normalized = query.lower()

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, normalized):
            raise ValueError("Potentially malicious query")

    return normalized