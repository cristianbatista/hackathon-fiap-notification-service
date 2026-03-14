"""Unit tests for email templates (TDD — written before implementation)."""
import pytest

from src.core.template_renderer import TemplateNotFoundError, render_template


class TestEmailTemplate:
    def test_done_template_contains_success_text(self):
        result = render_template("DONE", {"job_id": "test-job-123"})
        assert "processado com sucesso" in result

    def test_done_template_contains_job_id(self):
        result = render_template("DONE", {"job_id": "my-special-job"})
        assert "my-special-job" in result

    def test_error_template_contains_failure_text(self):
        result = render_template("ERROR", {"job_id": "test-job-456"})
        assert "falha" in result.lower()

    def test_error_template_contains_job_id(self):
        result = render_template("ERROR", {"job_id": "err-job-789"})
        assert "err-job-789" in result

    def test_error_template_does_not_contain_stack_trace(self):
        result = render_template("ERROR", {"job_id": "err-job"})
        assert "Traceback" not in result
        assert "Exception" not in result
        assert "stack" not in result.lower()

    def test_invalid_status_raises_template_not_found_error(self):
        with pytest.raises(TemplateNotFoundError):
            render_template("UNKNOWN", {"job_id": "x"})

    def test_done_template_returns_html(self):
        result = render_template("DONE", {"job_id": "x"})
        assert "<html" in result.lower()

    def test_error_template_returns_html(self):
        result = render_template("ERROR", {"job_id": "x"})
        assert "<html" in result.lower()
