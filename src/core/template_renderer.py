import os

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")

_env = Environment(
    loader=FileSystemLoader(os.path.abspath(_TEMPLATES_DIR)),
    autoescape=True,
)


class TemplateNotFoundError(Exception):
    """Raised when the requested email template does not exist."""


def render_template(status: str, context: dict) -> str:
    """Render an email template for the given job status.

    Args:
        status: Job status string — 'DONE' or 'ERROR'.
        context: Template variables, must include at least 'job_id'.

    Returns:
        Rendered HTML string.

    Raises:
        TemplateNotFoundError: If no template exists for the given status.
    """
    template_name = f"{status}.html.j2"
    try:
        template = _env.get_template(template_name)
    except TemplateNotFound as exc:
        raise TemplateNotFoundError(f"No template for status '{status}'") from exc
    return template.render(**context)
