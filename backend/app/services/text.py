from bs4 import BeautifulSoup


def clean_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    text = str(value)
    return "".join(
        char
        for char in text
        if char in "\t\n\r" or (0x20 <= ord(char) <= 0xD7FF) or (0xE000 <= ord(char) <= 0xFFFD) or ord(char) >= 0x10000
    ).replace("\x00", "")


def html_to_text(html: str | bytes | None) -> str:
    if not html:
        return ""
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="ignore")
    html = clean_text(html)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def chunk_text(text: str, max_chars: int = 3000, overlap_chars: int = 300) -> list[str]:
    normalized = " ".join(clean_text(text).split())
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + int(max_chars * 0.65), end)
            if boundary > start:
                end = boundary
        chunks.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        start = max(0, end - overlap_chars)
    return [chunk for chunk in chunks if chunk]


def normalize_for_hash(value: str | None) -> str:
    return " ".join(clean_text(value).casefold().split())
