"""Tests for targeted crawler safety checks."""

from apps.targeted_crawler.safety import check_redirect_safety, is_safe_url

ALLOWED = {"example.rw", "test.rw"}


class TestIsSafeUrl:
    def test_allowed_domain(self):
        ok, reason = is_safe_url("https://example.rw/page", ALLOWED)
        assert ok
        assert reason == "ok"

    def test_off_allowlist(self):
        ok, reason = is_safe_url("https://evil.com/page", ALLOWED)
        assert not ok
        assert reason == "off_allowlist"

    def test_bad_scheme(self):
        ok, reason = is_safe_url("ftp://example.rw/file", ALLOWED)
        assert not ok
        assert reason == "bad_scheme"

    def test_skip_pdf(self):
        ok, reason = is_safe_url("https://example.rw/doc.pdf", ALLOWED)
        assert not ok
        assert "skip_extension" in reason

    def test_skip_image(self):
        ok, reason = is_safe_url("https://example.rw/photo.jpg", ALLOWED)
        assert not ok
        assert "skip_extension" in reason

    def test_skip_css(self):
        ok, reason = is_safe_url("https://example.rw/style.css", ALLOWED)
        assert not ok
        assert "skip_extension" in reason

    def test_skip_zip(self):
        ok, reason = is_safe_url("https://example.rw/archive.zip", ALLOWED)
        assert not ok

    def test_html_path_ok(self):
        ok, reason = is_safe_url("https://example.rw/page.html", ALLOWED)
        assert ok

    def test_no_extension_ok(self):
        ok, reason = is_safe_url("https://example.rw/about", ALLOWED)
        assert ok

    def test_www_normalized(self):
        ok, reason = is_safe_url("https://www.example.rw/page", ALLOWED)
        assert ok


class TestRedirectSafety:
    def test_no_redirect(self):
        ok, reason = check_redirect_safety("https://example.rw/a", "https://example.rw/a", ALLOWED)
        assert ok

    def test_same_domain_redirect(self):
        ok, reason = check_redirect_safety("https://example.rw/a", "https://example.rw/b", ALLOWED)
        assert ok

    def test_off_allowlist_redirect(self):
        ok, reason = check_redirect_safety("https://example.rw/a", "https://evil.com/b", ALLOWED)
        assert not ok
        assert "redirect_off_allowlist" in reason

    def test_cross_allowed_redirect(self):
        ok, reason = check_redirect_safety("https://example.rw/a", "https://test.rw/b", ALLOWED)
        assert ok

    def test_empty_final_url(self):
        ok, reason = check_redirect_safety("https://example.rw/a", "", ALLOWED)
        assert ok
