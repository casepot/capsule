from typing import Any, Callable

def packb(
    o: Any,
    *,
    default: Callable[[Any], Any] | None = ...,
    use_bin_type: bool = ...,
    **kwargs: Any,
) -> bytes: ...

def unpackb(
    packed: bytes,
    *,
    raw: bool | None = ...,
    strict_map_key: bool | None = ...,
    **kwargs: Any,
) -> Any: ...

