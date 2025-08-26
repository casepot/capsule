
# src/subprocess/namespace.py (delta)
# Add an async helper binding method (non-invasive).

class NamespaceManager:
    # ... existing code ...

    def bind_async_helpers(self, ainput_callable) -> None:
        """
        Expose async helpers (currently only `ainput`) into the user namespace.
        Safe to call multiple times.
        """
        self._namespace["ainput"] = ainput_callable
