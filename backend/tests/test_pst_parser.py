from datetime import datetime

from app.importers.pst import _parse_attachments, _parse_message


def test_parse_attachment_uses_mapi_record_metadata():
    attachment = FakeAttachment(
        entries=[
            FakeEntry(0x3701, data=b"document bytes"),
            FakeEntry(0x3703, data_as_string=".pdf"),
            FakeEntry(0x3705, data_as_integer=1),
            FakeEntry(0x3707, data_as_string="Quarterly Report.PDF"),
            FakeEntry(0x370E, data_as_string="application/pdf"),
            FakeEntry(0x3712, data_as_string="cid-123"),
        ]
    )
    message = FakeMessage(attachments=[attachment])

    attachments = _parse_attachments(message)

    assert len(attachments) == 1
    assert attachments[0].filename == "Quarterly Report.PDF"
    assert attachments[0].content_id == "cid-123"
    assert attachments[0].disposition == "1"
    assert attachments[0].mime_type == "application/pdf"
    assert attachments[0].data == b"document bytes"


def test_parse_message_uses_mapi_record_sender_and_body_fallbacks():
    sent_at = datetime(2026, 1, 2, 3, 4, 5)
    message = FakeMessage(
        entries=[
            FakeEntry(0x0037, data_as_string="Fallback subject"),
            FakeEntry(0x0C1A, data_as_string="Sender Name"),
            FakeEntry(0x0C1F, data_as_string="sender@example.com"),
            FakeEntry(0x1000, data_as_string="Plain body from record set"),
            FakeEntry(0x3007, data_as_datetime=sent_at),
        ]
    )

    email = _parse_message(message, "Root/Inbox")

    assert email.subject == "Fallback subject"
    assert email.sender_name == "Sender Name"
    assert email.sender_email == "sender@example.com"
    assert email.body_text == "Plain body from record set"
    assert email.sent_at == sent_at


def test_parse_message_uses_display_recipient_fallbacks():
    message = FakeMessage(
        entries=[
            FakeEntry(0x0037, data_as_string="Fallback subject"),
            FakeEntry(0x0E04, data_as_string="Recipient One;Recipient Two"),
            FakeEntry(0x0E03, data_as_string="Recipient Three"),
            FakeEntry(0x0E02, data_as_string="Recipient Four"),
        ]
    )

    email = _parse_message(message, "Root/Inbox")

    assert [(item.kind, item.name, item.email) for item in email.recipients] == [
        ("to", "Recipient One", None),
        ("to", "Recipient Two", None),
        ("cc", "Recipient Three", None),
        ("bcc", "Recipient Four", None),
    ]


class FakeMessage:
    def __init__(self, entries=None, attachments=None):
        self.number_of_record_sets = 1 if entries else 0
        self._record_set = FakeRecordSet(entries or [])
        self.number_of_attachments = len(attachments or [])
        self._attachments = attachments or []
        self.number_of_recipients = 0

    def get_record_set(self, _index):
        return self._record_set

    def get_attachment(self, index):
        return self._attachments[index]


class FakeAttachment:
    def __init__(self, entries):
        self.number_of_record_sets = 1
        self._record_set = FakeRecordSet(entries)

    def get_record_set(self, _index):
        return self._record_set


class FakeRecordSet:
    def __init__(self, entries):
        self._entries = entries
        self.number_of_entries = len(entries)

    def get_entry(self, index):
        return self._entries[index]


class FakeEntry:
    def __init__(self, entry_type, data=None, data_as_string=None, data_as_integer=None, data_as_datetime=None):
        self.entry_type = entry_type
        self.data = data
        self.data_as_string = data_as_string
        self.data_as_integer = data_as_integer
        self.data_as_datetime = data_as_datetime
