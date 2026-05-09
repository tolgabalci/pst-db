from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from email.parser import Parser
from email.utils import getaddresses
from pathlib import Path
from typing import Any

from dateutil.parser import parse as parse_date

from app.services.text import clean_text, html_to_text

try:
    import pypff  # type: ignore
except ImportError:  # pragma: no cover - only available in the worker image
    pypff = None


@dataclass
class ParsedRecipient:
    kind: str
    name: str | None = None
    email: str | None = None


@dataclass
class ParsedAttachment:
    filename: str
    content_id: str | None
    disposition: str | None
    mime_type: str | None
    ordinal: int
    data: bytes


@dataclass
class ParsedEmail:
    entry_id: str
    folder_path: str
    message_id: str | None
    subject: str
    sender_name: str | None
    sender_email: str | None
    sent_at: datetime | None
    received_at: datetime | None
    body_text: str
    body_html: str | None
    recipients: list[ParsedRecipient] = field(default_factory=list)
    attachments: list[ParsedAttachment] = field(default_factory=list)


@dataclass
class ParsedError:
    item_ref: str
    stage: str
    message: str


def _get_attr(obj: Any, *names: str, default=None):
    for name in names:
        try:
            value = getattr(obj, name)
        except Exception:  # noqa: BLE001
            continue
        if callable(value):
            try:
                value = value()
            except TypeError:
                continue
            except Exception:  # noqa: BLE001
                continue
        if value not in (None, ""):
            return value
    return default


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return parse_date(str(value))
    except Exception:  # noqa: BLE001
        return None


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        if len(value) > 2 and value[1::2].count(0) > len(value) // 4:
            return clean_text(value.decode("utf-16-le", errors="ignore").rstrip("\x00"))
        return clean_text(value.decode("utf-8", errors="ignore").rstrip("\x00"))
    return clean_text(str(value))


def _clean_text(value: Any) -> str:
    return clean_text(_to_text(value)).strip()


def _record_entry(obj: Any, *entry_types: int):
    wanted = set(entry_types)
    record_count = int(_get_attr(obj, "number_of_record_sets", "get_number_of_record_sets", default=0) or 0)
    for record_index in range(record_count):
        try:
            record_set = obj.get_record_set(record_index)
        except Exception:  # noqa: BLE001
            continue
        entry_count = int(_get_attr(record_set, "number_of_entries", "get_number_of_entries", default=0) or 0)
        for entry_index in range(entry_count):
            try:
                entry = record_set.get_entry(entry_index)
            except Exception:  # noqa: BLE001
                continue
            entry_type = _get_attr(entry, "entry_type", "get_entry_type", default=None)
            if entry_type in wanted:
                return entry
    return None


def _record_string(obj: Any, *entry_types: int) -> str:
    entry = _record_entry(obj, *entry_types)
    if entry is None:
        return ""
    value = _get_attr(entry, "data_as_string", "get_data_as_string", default=None)
    if value in (None, ""):
        value = _get_attr(entry, "data", "get_data", default=None)
    return _clean_text(value)


def _record_integer(obj: Any, *entry_types: int) -> int | None:
    entry = _record_entry(obj, *entry_types)
    if entry is None:
        return None
    value = _get_attr(entry, "data_as_integer", "get_data_as_integer", default=None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _record_datetime(obj: Any, *entry_types: int) -> datetime | None:
    entry = _record_entry(obj, *entry_types)
    if entry is None:
        return None
    value = _get_attr(entry, "data_as_datetime", "get_data_as_datetime", default=None)
    return _to_datetime(value)


def _record_bytes(obj: Any, *entry_types: int) -> bytes:
    entry = _record_entry(obj, *entry_types)
    if entry is None:
        return b""
    value = _get_attr(entry, "data", "get_data", default=None)
    return value if isinstance(value, bytes) else b""


def _entry_id(message: Any) -> str:
    raw = _get_attr(message, "identifier", "entry_identifier", default=None)
    if isinstance(raw, bytes):
        return raw.hex()
    return str(raw or id(message))


def _read_attachment_data(attachment: Any) -> bytes:
    size = int(_get_attr(attachment, "size", "get_size", default=0) or 0)
    if hasattr(attachment, "read_buffer"):
        try:
            return attachment.read_buffer(size) if size else attachment.read_buffer()
        except TypeError:
            return attachment.read_buffer(size, 0)
    if hasattr(attachment, "read"):
        return attachment.read()
    return b""


def _parse_recipients(message: Any) -> list[ParsedRecipient]:
    recipients: list[ParsedRecipient] = []
    count = int(_get_attr(message, "number_of_recipients", "get_number_of_recipients", default=0) or 0)
    for index in range(count):
        try:
            recipient = message.get_recipient(index)
        except Exception:  # noqa: BLE001
            continue
        recipients.append(
            ParsedRecipient(
                kind=_recipient_kind(_get_attr(recipient, "type", "recipient_type", default="to")),
                name=_clean_text(_get_attr(recipient, "name", "display_name", default="")) or None,
                email=_clean_text(_get_attr(recipient, "email_address", "smtp_address", default="")) or None,
            )
        )
    if recipients:
        return recipients

    recipients.extend(_display_recipients("to", _record_string(message, 0x0E04)))
    recipients.extend(_display_recipients("cc", _record_string(message, 0x0E03)))
    recipients.extend(_display_recipients("bcc", _record_string(message, 0x0E02)))
    if recipients:
        return recipients

    headers = _record_string(message, 0x007D)
    if headers:
        parsed = Parser().parsestr(headers)
        for kind, header in (("to", "to"), ("cc", "cc"), ("bcc", "bcc")):
            for name, address in getaddresses(parsed.get_all(header, [])):
                recipients.append(ParsedRecipient(kind=kind, name=_clean_text(name) or None, email=_clean_text(address) or None))
    return recipients


def _recipient_kind(value: Any) -> str:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = None
    if numeric == 1:
        return "to"
    if numeric == 2:
        return "cc"
    if numeric == 3:
        return "bcc"
    text = _clean_text(value).casefold()
    if "cc" in text and "bcc" not in text:
        return "cc"
    if "bcc" in text:
        return "bcc"
    return "to"


def _display_recipients(kind: str, value: str) -> list[ParsedRecipient]:
    if not value:
        return []
    names = [part.strip() for part in value.replace(",", ";").split(";")]
    return [ParsedRecipient(kind=kind, name=name, email=None) for name in names if name]


def _parse_attachments(message: Any) -> list[ParsedAttachment]:
    attachments: list[ParsedAttachment] = []
    count = int(_get_attr(message, "number_of_attachments", "get_number_of_attachments", default=0) or 0)
    for index in range(count):
        try:
            attachment = message.get_attachment(index)
            name = (
                _record_string(attachment, 0x3707, 0x3704, 0x3001)
                or _clean_text(_get_attr(attachment, "long_filename", "filename", "name", default=""))
                or f"attachment-{index + 1}"
            )
            extension = _record_string(attachment, 0x3703)
            if name.startswith("attachment-") and extension.startswith("."):
                name = f"{name}{extension}"
            data = _read_attachment_data(attachment) or _record_bytes(attachment, 0x3701)
            method = _record_integer(attachment, 0x3705)
            attachments.append(
                ParsedAttachment(
                    filename=name,
                    content_id=(
                        _record_string(attachment, 0x3712)
                        or _clean_text(_get_attr(attachment, "content_identifier", default=""))
                        or None
                    ),
                    disposition=(
                        str(method)
                        if method is not None
                        else (_clean_text(_get_attr(attachment, "method", "attachment_method", default="")) or None)
                    ),
                    mime_type=_record_string(attachment, 0x370E) or None,
                    ordinal=index,
                    data=data,
                )
            )
        except Exception:  # noqa: BLE001
            continue
    return attachments


def _parse_message(message: Any, folder_path: str) -> ParsedEmail:
    html = _to_text(_get_attr(message, "html_body", "get_html_body", default="")) or _to_text(_record_bytes(message, 0x1013)) or None
    plain = (
        _to_text(_get_attr(message, "plain_text_body", "get_plain_text_body", default=""))
        or _record_string(message, 0x1000)
    )
    body_text = clean_text(plain or html_to_text(html))
    message_id = _clean_text(_get_attr(message, "internet_message_identifier", "message_identifier", default="")) or _record_string(
        message, 0x1035, 0x1042
    )
    subject = _clean_text(_get_attr(message, "subject", default="")) or _record_string(message, 0x0037, 0x0070, 0x0E1D)
    return ParsedEmail(
        entry_id=_entry_id(message),
        folder_path=folder_path,
        message_id=message_id or None,
        subject=subject,
        sender_name=_clean_text(_get_attr(message, "sender_name", default="")) or _record_string(message, 0x0C1A, 0x0042) or None,
        sender_email=(
            _clean_text(_get_attr(message, "sender_email_address", "sender_smtp_address", default=""))
            or _record_string(message, 0x0C1F, 0x0065, 0x39FE, 0x3FFA, 0x5D01)
            or None
        ),
        sent_at=_to_datetime(_get_attr(message, "client_submit_time", default=None)) or _record_datetime(message, 0x0039, 0x3007),
        received_at=_to_datetime(_get_attr(message, "delivery_time", default=None)) or _record_datetime(message, 0x0E06, 0x3008),
        body_text=body_text,
        body_html=clean_text(html) if html else None,
        recipients=_parse_recipients(message),
        attachments=_parse_attachments(message),
    )


class PstReader:
    def __init__(self, path: Path):
        self.path = path
        if pypff is None:
            raise RuntimeError("pypff is not installed. Use the Docker worker image or install python3-libpff.")

    def iter_messages(self) -> Iterator[ParsedEmail]:
        for item in self.iter_items():
            if isinstance(item, ParsedEmail):
                yield item

    def iter_items(self) -> Iterator[ParsedEmail | ParsedError]:
        pst_file = pypff.file()
        pst_file.open(str(self.path))
        try:
            root = pst_file.get_root_folder()
            yield from self._walk_folder(root, root.name or "Root")
        finally:
            pst_file.close()

    def _walk_folder(self, folder: Any, folder_path: str) -> Iterator[ParsedEmail | ParsedError]:
        message_count = int(_get_attr(folder, "number_of_sub_messages", "get_number_of_sub_messages", default=0) or 0)
        for index in range(message_count):
            try:
                message = folder.get_sub_message(index)
                yield _parse_message(message, folder_path)
            except Exception as exc:  # noqa: BLE001
                yield ParsedError(
                    item_ref=f"{folder_path} message {index}",
                    stage="pst_message_parse",
                    message=str(exc),
                )

        folder_count = int(_get_attr(folder, "number_of_sub_folders", "get_number_of_sub_folders", default=0) or 0)
        for index in range(folder_count):
            try:
                sub_folder = folder.get_sub_folder(index)
                name = _to_text(_get_attr(sub_folder, "name", default=f"Folder {index + 1}"))
                yield from self._walk_folder(sub_folder, f"{folder_path}/{name}")
            except Exception as exc:  # noqa: BLE001
                yield ParsedError(
                    item_ref=f"{folder_path} folder {index}",
                    stage="pst_folder_parse",
                    message=str(exc),
                )
