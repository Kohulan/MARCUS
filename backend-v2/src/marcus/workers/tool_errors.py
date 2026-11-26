"""The tools workers' input error, in its own module so a helper module (marcus.workers.paper_view)
can raise it without importing marcus.workers.tools, which imports that helper (no import cycle)."""


class ToolInputError(ValueError):
    """The caller's input cannot be parsed or is unusable (HTTP 422)."""
