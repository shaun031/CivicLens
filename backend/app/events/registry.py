from app.events.schema import consumer


class HandlerRegistry:
    """Explicit versioned consumers; ambiguous duplicate registration is a startup error."""

    def __init__(self):
        self.handlers = {}

    def register(self, name, handler, version=1):
        if name not in ("triage", "priority", "notify") or type(version) is not int or version != 1:
            raise ValueError("Unsupported consumer version")
        key = (name, version)
        if key in self.handlers:
            raise ValueError("Duplicate consumer registration")
        self.handlers[key] = handler

    def dispatch(self, event, message):
        handler = self.handlers.get((consumer(event), event.eventVersion))
        if handler is None:
            raise ValueError("Unregistered consumer version")
        return handler(event, message)
