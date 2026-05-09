import bleach
from bs4 import BeautifulSoup

from app.services.text import clean_text

ALLOWED_TAGS = [
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}


def sanitize_html(html: str | None) -> str | None:
    if not html:
        return None
    soup = BeautifulSoup(clean_text(html), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return bleach.clean(
        str(soup),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
