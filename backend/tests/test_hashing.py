from app.services.hashing import FingerprintAttachment, email_fingerprint, sha256_bytes


def test_sha256_bytes_is_stable():
    assert sha256_bytes(b"attachment") == sha256_bytes(b"attachment")


def test_email_fingerprint_is_attachment_order_stable():
    attachments_a = [
        FingerprintAttachment(filename="b.pdf", content_hash="222"),
        FingerprintAttachment(filename="a.txt", content_hash="111"),
    ]
    attachments_b = list(reversed(attachments_a))
    first = email_fingerprint(
        message_id="<id@example.com>",
        subject=" Quarterly Update ",
        sender_email="ALICE@example.com",
        sent_at_iso="2025-01-01T10:00:00",
        body_text="Same body",
        attachments=attachments_a,
    )
    second = email_fingerprint(
        message_id="<id@example.com>",
        subject="quarterly update",
        sender_email="alice@example.com",
        sent_at_iso="2025-01-01T10:00:00",
        body_text="Same body",
        attachments=attachments_b,
    )
    assert first == second


def test_email_fingerprint_is_stable_when_attachment_filename_parser_improves():
    first = email_fingerprint(
        message_id="<id@example.com>",
        subject="Quarterly Update",
        sender_email="alice@example.com",
        sent_at_iso="2025-01-01T10:00:00",
        body_text="Same body",
        attachments=[FingerprintAttachment(filename="attachment-1", content_hash="111")],
    )
    second = email_fingerprint(
        message_id="<id@example.com>",
        subject="Quarterly Update",
        sender_email="alice@example.com",
        sent_at_iso="2025-01-01T10:00:00",
        body_text="Same body",
        attachments=[FingerprintAttachment(filename="Real Filename.pdf", content_hash="111")],
    )

    assert first == second
