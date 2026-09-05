"""Unit tests for the relocated shared helpers (spec 015).

The ``api/shared.py`` helpers were relocated verbatim to ``tools/shared.py``
because the proxy's ``api.py`` module occupies the ``api`` import name. These
assert the helpers behave per the source contract, including the
``DOWNLOAD_HTML_BUTTON`` disabled path.
"""
from fastapi.responses import HTMLResponse

import tools.shared as shared


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {"authorization": "Bearer tok"}


def _result():
    return {
        "file_path_download": "[Download report.md](/api/v1/files/abc/content)",
        "download_url": "/api/v1/files/abc/content",
        "file_id": "abc",
        "file_name": "report",
        "file_type": "md",
    }


def test_build_request_context_captures_headers():
    ctx = shared.build_request_context(_FakeRequest())
    assert ctx == {"headers": {"authorization": "Bearer tok"}}


def test_get_file_icon_svg_inline_for_md():
    svg = shared.get_file_icon_svg("md")
    assert "<svg" in svg
    assert "MD" in svg


def test_render_download_button_html_for_valid_result():
    html = shared.render_download_button_html(_result())
    assert isinstance(html, HTMLResponse)
    assert "Download file" in html.body.decode()
    assert "/api/v1/files/abc/content" in html.body.decode()


def test_render_download_button_html_returns_none_when_missing():
    assert shared.render_download_button_html({"file_name": "x"}) is None
    assert shared.render_download_button_html("not-a-dict") is None


def test_build_download_response_structured_by_default():
    # The shared module's DOWNLOAD_HTML_BUTTON is forced to False by api.py,
    # so the default path returns the raw structured result (never HTML).
    resp = shared.build_download_response(_result())
    assert isinstance(resp, dict)
    assert resp["file_type"] == "md"


def test_build_download_response_structured_when_button_disabled(monkeypatch):
    monkeypatch.setattr(shared, "DOWNLOAD_HTML_BUTTON", False)
    resp = shared.build_download_response(_result())
    assert isinstance(resp, dict)
    assert resp["file_type"] == "md"
