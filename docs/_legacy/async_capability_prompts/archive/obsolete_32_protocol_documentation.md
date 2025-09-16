  Protocol Architecture Review

  🏗️ Current Implementation Analysis

  Layer 1: Framing (framing.py)

  ✅ Strengths:
  - Simple, efficient length-prefixed framing: [4 bytes][data]
  - Zero-copy operations where possible
  - Proper async locking for thread safety
  - Excellent rate limiter implementation - eliminates polling!

  ⚠️ Issues:
  - StreamMultiplexer defined but unused - adds complexity without value
  - No frame type identification (all frames treated identically)
  - 10MB frame size limit hardcoded

  Layer 2: Messages (messages.py)

  ✅ Strengths:
  - Clean Pydantic models for validation
  - Proper message type enumeration
  - Transaction support with policies
  - Execution correlation via execution_id

  ❌ Critical Gaps:
  - Missing capability messages (HttpRequest, HttpResponse, Display, etc.)
  - No sequence numbering for ordering
  - No acknowledgment messages
  - No protocol version field

  Layer 3: Transport (transport.py)

  ✅ Strengths:
  - Proper async synchronization with asyncio.Condition
  - Clean separation between reading and writing
  - Timeout support throughout
  - Good logging for debugging

  ⚠️ Issues:
  - No reconnection logic
  - No heartbeat mechanism beyond manual HeartbeatMessage
  - No message queue for handling bursts

  📋 Protocol Documentation

  """
  PyREPL3 Wire Protocol Specification
  ====================================

  1. FRAMING LAYER
  ----------------
  Format: [LENGTH:4 bytes, big-endian][PAYLOAD:N bytes]
  - Maximum frame size: 10MB
  - Minimum frame size: 0 bytes (heartbeat)

  2. MESSAGE LAYER
  ----------------
  Serialization: MessagePack (default) or JSON
  Message Structure:
  {
      "type": MessageType,      # Required: Message type enum
      "id": str,                 # Required: Unique message ID (UUID)
      "timestamp": float,        # Required: Unix timestamp
      "execution_id": str,       # Context: Links related messages
      ... type-specific fields
  }

  3. CORRELATION PATTERNS
  -----------------------
  Execution Flow:
      ExecuteMessage.id → becomes execution_id for:
          - OutputMessage.execution_id
          - InputMessage.execution_id
          - ResultMessage.execution_id
          - ErrorMessage.execution_id

  Input Flow:
      InputMessage.id → becomes input_id for:
          - InputResponseMessage.input_id

  4. MESSAGE SEQUENCES
  --------------------
  Normal Execution:
      → ExecuteMessage
      ← OutputMessage (0..n)
      ← ResultMessage | ErrorMessage

  Interactive Execution:
      → ExecuteMessage
      ← OutputMessage (0..n)
      ← InputMessage
      → InputResponseMessage
      ← OutputMessage (0..n)
      ← ResultMessage | ErrorMessage

  Transaction Execution:
      → ExecuteMessage (with transaction_id)
      ← OutputMessage (0..n)
      ← ErrorMessage
      → RestoreMessage (rollback)
      ← ReadyMessage (recovered)
  """

  🔧 Recommended Protocol Enhancements

  # 1. Add missing capability messages to messages.py

  class HttpRequestMessage(BaseMessage):
      """Capability request for HTTP operations."""
      type: Literal["http_request"] = Field(default="http_request")
      url: str = Field(description="URL to request")
      method: str = Field(default="GET", description="HTTP method")
      headers: Optional[Dict[str, str]] = Field(default=None)
      body: Optional[bytes] = Field(default=None)
      execution_id: str = Field(description="Execution context")
      timeout: float = Field(default=30.0)

  class HttpResponseMessage(BaseMessage):
      """Response to HTTP request."""
      type: Literal["http_response"] = Field(default="http_response")
      request_id: str = Field(description="ID of HttpRequestMessage")
      status: int = Field(description="HTTP status code")
      headers: Dict[str, str] = Field(default_factory=dict)
      body: bytes = Field(description="Response body")

  class DisplayMessage(BaseMessage):
      """Rich display output."""
      type: Literal["display"] = Field(default="display")
      mime_type: str = Field(description="MIME type of content")
      data: Any = Field(description="Display data")
      metadata: Dict[str, Any] = Field(default_factory=dict)
      execution_id: str = Field(description="Execution context")

  class QueryRequestMessage(BaseMessage):
      """Database query capability."""
      type: Literal["query_request"] = Field(default="query_request")
      sql: str = Field(description="SQL query")
      params: Optional[List[Any]] = Field(default=None)
      execution_id: str = Field(description="Execution context")

  class QueryResponseMessage(BaseMessage):
      """Database query results."""
      type: Literal["query_response"] = Field(default="query_response")
      request_id: str = Field(description="ID of QueryRequestMessage")
      rows: List[Dict[str, Any]] = Field(description="Query results")
      row_count: int = Field(description="Number of rows affected")

  # 2. Add protocol versioning
  class ProtocolVersion(BaseModel):
      major: int = 1
      minor: int = 0
      patch: int = 0

      def is_compatible(self, other: "ProtocolVersion") -> bool:
          """Check if protocols are compatible (same major version)."""
          return self.major == other.major

  # 3. Add message acknowledgment
  class AckMessage(BaseMessage):
      """Acknowledge receipt of a message."""
      type: Literal["ack"] = Field(default="ack")
      message_id: str = Field(description="ID of acknowledged message")
      status: Literal["received", "processed", "failed"] = Field()
      error: Optional[str] = Field(default=None)

  🔍 Critical Protocol Patterns

  # Pattern 1: Message Queueing for Async Context
  class ProtocolAdapter:
      """Adapter to handle protocol in any execution context."""

      def __init__(self, transport: MessageTransport):
          self.transport = transport
          self._queue = []
          self._lock = threading.Lock()

      async def send_safe(self, message: Message) -> None:
          """Send message, queuing if not in async context."""
          try:
              # Try direct send if in async context
              await self.transport.send_message(message)
          except RuntimeError:  # No event loop
              # Queue for later
              with self._lock:
                  self._queue.append(message)

      async def flush_queue(self) -> None:
          """Flush queued messages when entering async context."""
          with self._lock:
              messages = self._queue[:]
              self._queue.clear()

          for msg in messages:
              await self.transport.send_message(msg)

  # Pattern 2: Execution Context Tracking
  class ExecutionContext:
      """Track execution context for message correlation."""

      def __init__(self, execution_id: str):
          self.execution_id = execution_id
          self.start_time = time.time()
          self.messages_sent = []
          self.messages_received = []

      def track_sent(self, message: Message):
          """Track outgoing message."""
          self.messages_sent.append({
              'type': message.type,
              'id': message.id,
              'timestamp': message.timestamp
          })

      def track_received(self, message: Message):
          """Track incoming message."""
          self.messages_received.append({
              'type': message.type,
              'id': message.id,
              'timestamp': message.timestamp
          })

  # Pattern 3: Protocol State Machine
  class ProtocolStateMachine:
      """State machine for protocol message flow."""

      STATES = {
          'idle': ['execute'],
          'executing': ['output', 'input', 'result', 'error'],
          'waiting_input': ['input_response'],
          'completed': ['idle']
      }

      def __init__(self):
          self.state = 'idle'
          self.execution_id = None

      def transition(self, message_type: str) -> bool:
          """Validate state transition."""
          allowed = self.STATES.get(self.state, [])
          if message_type not in allowed:
              logger.warning(f"Invalid transition: {self.state} -> {message_type}")
              return False

          # Update state based on message
          if message_type == 'execute':
              self.state = 'executing'
          elif message_type == 'input':
              self.state = 'waiting_input'
          elif message_type in ['result', 'error']:
              self.state = 'completed'
          elif message_type == 'input_response':
              self.state = 'executing'

          return True

  📊 Protocol Metrics & Monitoring

  class ProtocolMetrics:
      """Track protocol performance and health."""

      def __init__(self):
          self.messages_sent = 0
          self.messages_received = 0
          self.bytes_sent = 0
          self.bytes_received = 0
          self.errors = 0
          self.latencies = []
          self.message_types = defaultdict(int)

      def record_sent(self, message: Message, size: int):
          """Record sent message metrics."""
          self.messages_sent += 1
          self.bytes_sent += size
          self.message_types[message.type] += 1

      def record_received(self, message: Message, size: int):
          """Record received message metrics."""
          self.messages_received += 1
          self.bytes_received += size

      def record_roundtrip(self, request_time: float, response_time: float):
          """Record request-response latency."""
          latency = response_time - request_time
          self.latencies.append(latency)

      def get_stats(self) -> Dict[str, Any]:
          """Get protocol statistics."""
          return {
              'messages': {
                  'sent': self.messages_sent,
                  'received': self.messages_received,
                  'errors': self.errors
              },
              'bandwidth': {
                  'sent_bytes': self.bytes_sent,
                  'received_bytes': self.bytes_received
              },
              'performance': {
                  'avg_latency': sum(self.latencies) / len(self.latencies) if self.latencies else 0,
                  'max_latency': max(self.latencies) if self.latencies else 0
              },
              'message_distribution': dict(self.message_types)
          }

  ✅ Protocol Validation Rules

  class ProtocolValidator:
      """Validate protocol invariants."""

      @staticmethod
      def validate_execution_flow(messages: List[Message]) -> bool:
          """Validate that execution follows protocol rules."""

          # Rule 1: Every ExecuteMessage must have Result or Error
          executions = {}
          for msg in messages:
              if isinstance(msg, ExecuteMessage):
                  executions[msg.id] = {'complete': False}
              elif isinstance(msg, (ResultMessage, ErrorMessage)):
                  if msg.execution_id in executions:
                      executions[msg.execution_id]['complete'] = True

          incomplete = [e for e, v in executions.items() if not v['complete']]
          if incomplete:
              logger.error(f"Incomplete executions: {incomplete}")
              return False

          # Rule 2: InputResponse must follow InputMessage
          pending_inputs = set()
          for msg in messages:
              if isinstance(msg, InputMessage):
                  pending_inputs.add(msg.id)
              elif isinstance(msg, InputResponseMessage):
                  if msg.input_id not in pending_inputs:
                      logger.error(f"InputResponse without request: {msg.input_id}")
                      return False
                  pending_inputs.remove(msg.input_id)

          if pending_inputs:
              logger.error(f"Unanswered inputs: {pending_inputs}")
              return False

          return True

  🚀 Implementation Priorities

  1. Immediate (Critical):
    - Add missing capability messages
    - Implement message queueing for async context
    - Add execution context tracking
  2. Short-term (Important):
    - Add protocol versioning
    - Implement acknowledgments for critical messages
    - Add connection health monitoring
  3. Long-term (Nice-to-have):
    - Remove unused StreamMultiplexer
    - Add compression for large messages
    - Implement reconnection logic

  📝 Summary

  The protocol implementation is fundamentally sound with excellent async handling and clean
  separation of concerns. The main gaps are:

  1. Missing capability messages - Easy to add
  2. No message ordering guarantees - Add sequence numbers
  3. No acknowledgment mechanism - Add for reliability
  4. Async context handling - Needs message queueing pattern
