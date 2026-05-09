from app.services.sanitize import sanitize_html


def test_sanitize_html_removes_style_contents():
    html = "<style>.hidden{display:none}</style><p>Hello</p><script>alert(1)</script>"

    assert sanitize_html(html) == "<p>Hello</p>"
