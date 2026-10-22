import logging


class QueryPrivacyFilter(logging.Filter):
    """Keep search terms and ephemeral map/GPS queries out of standard access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            values = list(record.args)
            index = 2 if record.name == "uvicorn.access" else 1
            if len(values) > index:
                values[index] = str(values[index]).partition("?")[0]
                record.args = tuple(values)
        return True


def configure_logging(level: str) -> None:
    """Configure consistent application logging for local and Lambda runtimes."""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Lambda/ASGI hosts may have installed handlers already; basicConfig alone is then a no-op.
    logging.getLogger().setLevel(getattr(logging, level))
    for name in ("uvicorn.access", "httpx"):
        target = logging.getLogger(name)
        if not any(isinstance(item, QueryPrivacyFilter) for item in target.filters):
            target.addFilter(QueryPrivacyFilter())
