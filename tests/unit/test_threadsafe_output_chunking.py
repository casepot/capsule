import pytest
from unittest.mock import Mock

from src.subprocess.executor import ThreadSafeOutput
from src.protocol.messages import StreamType


@pytest.mark.unit
def test_threadsafe_output_coerces_chunk_size_with_mock_public_attr():
    """Ensure write() handles mocked/non-int chunk size and uses fallback.

    If `executor.line_chunk_size` is a Mock, the implementation should
    fall back to `_line_chunk_size` and still chunk/signal correctly.
    """
    # Arrange a mock executor with mocked public attr and valid internal attr
    executor = Mock()
    # Public attribute resolves to a Mock (non-int), as seen in feature tests
    executor.line_chunk_size = Mock()
    # Internal attribute used by tests to configure a numeric chunk size
    executor._line_chunk_size = 5

    enqueued: list[tuple[str, StreamType]] = []
    executor._enqueue_from_thread = lambda data, stream: enqueued.append((data, stream))

    out = ThreadSafeOutput(executor, StreamType.STDOUT)

    # Act: 12 chars + newline should result in 3 chunks (5, 5, 2+\n)
    out.write("abcdefghijkl\n")

    # Assert
    assert enqueued == [
        ("abcde", StreamType.STDOUT),
        ("fghij", StreamType.STDOUT),
        ("kl\n", StreamType.STDOUT),
    ]

