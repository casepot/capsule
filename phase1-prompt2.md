  Context and Objective

  Implement a production-ready AsyncExecutor with correct top-level await (TLA)
  semantics, robust namespace management, intelligent execution routing, and
  foundational patterns for future Resonate integration. This implementation will
  serve as the bridge between the current ThreadedExecutor and the future distributed
   execution architecture.

  Required Reading

  Read these specifications in full before implementation:
  - FOUNDATION_FIX_PLAN.md (especially PR #11 Triage and Phase 1 sections)
  - docs/async_capability_prompts/current/22_spec_async_execution.md (CO_COROUTINE flag pattern)
  - docs/async_capability_prompts/current/24_spec_namespace_management.md (namespace merge patterns)
  - docs/async_capability_prompts/current/20_spec_architecture.md
  - docs/async_capability_prompts/current/00_foundation_resonate.md
  - docs/async_capability_prompts/current/21_spec_resonate_integration.md (DI patterns, timeout patterns)
  - docs/async_capability_prompts/current/PyCF_TOP_LEVEL_AWAIT_spec.pdf
  - docs/async_capability_prompts/current/10_prompt_async_executor.md (Python 3.11+ patterns)

  Review existing code:
  - src/subprocess/async_executor.py, src/subprocess/executor.py
  - src/subprocess/namespace.py, src/session/manager.py
  - tests/unit/test_top_level_await.py, tests/unit/test_async_executor.py

  Scope Definition

  In-Scope

  - Complete TLA implementation with both direct compilation and AST fallback paths
  - Robust namespace merge-only semantics with proper global/local precedence
  - Intelligent execution mode routing with comprehensive blocking I/O detection
  - Factory-based dependency injection pattern (no temporal coupling)
  - Minimal awaitable promise adapter interface
  - Test stability and CI integration
  - Edge case handling for problematic Python constructs

  Out-of-Scope

  - Full Resonate SDK integration or remote orchestration
  - Complete capability security model
  - Worker/session pool architectural changes
  - Network-based promise resolution

  Detailed Implementation Plan

  1. Top-Level Await Core Implementation

  1.1 Correct Flag Value Usage

  File: src/subprocess/async_executor.py

  class AsyncExecutor:
      # Use Python's actual constant value directly
      PyCF_ALLOW_TOP_LEVEL_AWAIT = getattr(ast, 'PyCF_ALLOW_TOP_LEVEL_AWAIT', 0x2000)

  Rationale: Use the correct Python flag value (0x2000) as documented in CPython
  source and confirmed by the comprehensive PyCF_ALLOW_TOP_LEVEL_AWAIT report.

  1.2 Execution Routing Strategy

  File: src/subprocess/async_executor.py::execute()

  Implement fast-path routing with test awareness:
  async def execute(self, code: str) -> Any:
      # Fast-path: Skip AST analysis if code contains 'await'
      if 'await' in code:
          mode = ExecutionMode.TOP_LEVEL_AWAIT
      else:
          mode = self.analyze_execution_mode(code)

      # Route based on mode
      if mode == ExecutionMode.TOP_LEVEL_AWAIT:
          return await self._execute_top_level_await(code)
      elif 'await' in code:
          # Fallback for edge cases like lambdas with await
          return await self._execute_top_level_await(code)
      else:
          return await self._execute_with_threaded_executor(code)

  1.3 Direct TLA Path Implementation

  File: src/subprocess/async_executor.py::_execute_top_level_await()

  Key requirements:
  - Attempt eval mode first for expressions (enables test control)
  - Use live namespace as globals for proper binding
  - Take pre-execution snapshot for globals diff detection
  - Apply updates in correct order: locals first, then global diffs

  async def _execute_top_level_await(self, code: str) -> Any:
      base_flags = compile('', '', 'exec').co_flags
      flags = base_flags | self.PyCF_ALLOW_TOP_LEVEL_AWAIT

      try:
          # Try eval mode first (for expressions)
          compiled = compile(code, '<async_session>', 'eval', flags=flags)

          # Check CO_COROUTINE flag (more reliable than runtime checks)
          # This is the canonical pattern used by IPython/Jupyter
          import inspect
          is_coroutine_code = bool(inspect.CO_COROUTINE & compiled.co_flags)

          # Use live namespace as globals, separate locals
          global_ns = self.namespace.namespace  # Live mapping
          local_ns = {}

          # Snapshot globals before execution
          pre_globals = dict(global_ns)

          # Ensure asyncio available
          if 'asyncio' not in global_ns:
              import asyncio as _asyncio
              global_ns['asyncio'] = _asyncio

          # Execute
          coro_or_result = eval(compiled, global_ns, local_ns)

          if is_coroutine_code and inspect.iscoroutine(coro_or_result):
              self._track_coroutine(coro_or_result)
              # Use Python 3.11+ asyncio.timeout for cleaner timeout handling
              async with asyncio.timeout(30):  # Configurable timeout
                  result = await coro_or_result
          else:
              result = coro_or_result

          # Update namespace: locals first
          if local_ns:
              self.namespace.update_namespace(local_ns, source_context='async')

          # Then apply global diffs (ensures global writes win)
          global_updates = self._compute_global_diff(pre_globals, global_ns)
          if global_updates:
              self.namespace.update_namespace(global_updates, source_context='async')

          # Track expression results
          if result is not None:
              self.namespace.record_expression_result(result)

          return result

      except asyncio.TimeoutError as e:
          # Enrich timeout error with context (Python 3.11+)
          if hasattr(e, 'add_note'):
              e.add_note(f"Code execution timed out after 30 seconds")
              e.add_note(f"Execution ID: {self.execution_id}")
              e.add_note(f"Code snippet: {code[:100]}..." if len(code) > 100 else code)
          raise
      except SyntaxError as e:
          # Add context to syntax error (Python 3.11+)
          if hasattr(e, 'add_note'):
              e.add_note("Direct compilation with PyCF_ALLOW_TOP_LEVEL_AWAIT failed")
              e.add_note("Falling back to AST transformation wrapper")
          # Fall back to AST transformation
          return await self._execute_with_ast_transform(code)

  1.4 AST Transformation Fallback

  File: src/subprocess/async_executor.py::_execute_with_ast_transform()

  Implement sophisticated AST transformations for edge cases:

  1. Pre-transformations (before wrapping):
    - Convert def containing await to async def
    - Rewrite zero-arg lambdas with await to async def helpers
    - Handle other problematic patterns
  2. Global hoisting (conservative):
    - Analyze top-level assignments
    - Insert ast.Global declarations for simple names
    - Avoid complex patterns that could break
  3. Execution and merge ordering:
    - Same snapshot/diff pattern as direct path
    - Locals merge followed by global diff application

  async def _execute_with_ast_transform(self, code: str) -> Any:
      tree = ast.parse(code)

      # Pre-transform problematic patterns
      transformed_body = []
      for stmt in tree.body:
          # Transform def with await -> async def
          if isinstance(stmt, ast.FunctionDef) and self._contains_await(stmt):
              async_def = ast.AsyncFunctionDef(
                  name=stmt.name,
                  args=stmt.args,
                  body=stmt.body,
                  decorator_list=stmt.decorator_list,
                  returns=stmt.returns
              )
              ast.copy_location(async_def, stmt)
              transformed_body.append(async_def)

          # Transform zero-arg lambda with await
          elif isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Lambda):
              if self._should_transform_lambda(stmt.value):
                  transformed = self._transform_lambda_to_async_def(stmt)
                  transformed_body.extend(transformed)
          else:
              transformed_body.append(stmt)

      tree.body = transformed_body

      # Determine if expression or statements
      is_expression = len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr)

      # Prepare wrapper body
      if is_expression:
          body = [ast.Return(value=tree.body[0].value)]
      else:
          # Conservative global hoisting
          assigned_names = self._collect_safe_assigned_names(tree.body)
          body = []
          if assigned_names:
              body.append(ast.Global(names=sorted(assigned_names)))
          body.extend(tree.body)
          body.append(ast.Return(value=ast.Call(
              func=ast.Name(id='locals', ctx=ast.Load()),
              args=[], keywords=[]
          )))

      # Create async wrapper
      async_wrapper = ast.AsyncFunctionDef(
          name='__async_exec__',
          args=ast.arguments(
              posonlyargs=[], args=[], kwonlyargs=[],
              kw_defaults=[], defaults=[]
          ),
          body=body,
          decorator_list=[]
      )

      # Execute with proper namespace handling (same as direct path)
      # ... (snapshot, execution, diff application)

  2. Enhanced Blocking I/O Detection

  File: src/subprocess/async_executor.py::_contains_blocking_io()

  Implement comprehensive detection with alias tracking:

  def _contains_blocking_io(self, tree: ast.AST) -> bool:
      """Detect blocking I/O with alias resolution.
      
      Detects patterns including:
      - time.sleep(), socket.recv(), file.read()
      - Database clients: psycopg2, pymongo, redis
      - HTTP clients: requests, urllib, httpx (sync)
      - Import aliases and from imports
      """

      # Extended blocking modules list
      BLOCKING_IO_MODULES = {
          'requests', 'urllib', 'socket', 'subprocess',
          'sqlite3', 'psycopg2', 'pymongo', 'redis',
          'time', 'os', 'shutil', 'pathlib'
      }
      
      # Blocking methods by module
      BLOCKING_METHODS = {
          'time': {'sleep', 'wait'},
          'socket': {'recv', 'send', 'accept', 'connect'},
          'requests': {'get', 'post', 'put', 'delete', 'patch'},
          'os': {'system', 'popen', 'waitpid'},
          'pathlib': {'read_text', 'read_bytes', 'write_text', 'write_bytes'}
      }

      # Track import aliases
      alias_to_module = {}

      # First pass: collect imports and aliases
      for node in ast.walk(tree):
          if isinstance(node, ast.Import):
              for alias in node.names:
                  module_name = alias.name.split('.')[0]
                  if alias.asname:
                      alias_to_module[alias.asname] = module_name
                  else:
                      alias_to_module[alias.name] = module_name

          elif isinstance(node, ast.ImportFrom):
              if node.module:
                  module_name = node.module.split('.')[0]
                  for alias in node.names:
                      name = alias.asname or alias.name
                      alias_to_module[name] = module_name

      # Second pass: detect blocking patterns
      for node in ast.walk(tree):
          if isinstance(node, ast.Call):
              # Direct calls
              if isinstance(node.func, ast.Name):
                  if node.func.id in self.BLOCKING_IO_CALLS:
                      return True
                  # Check if it's an imported blocking function
                  if alias_to_module.get(node.func.id) in BLOCKING_IO_MODULES:
                      return True

              # Attribute calls (time.sleep, requests.get, etc.)
              elif isinstance(node.func, ast.Attribute):
                  base = self._resolve_attribute_base(node.func.value)
                  if base in alias_to_module:
                      actual_module = alias_to_module[base]
                      if actual_module in BLOCKING_IO_MODULES:
                          methods = BLOCKING_METHODS.get(actual_module, set())
                          if node.func.attr in methods:
                              return True

      return False

  3. Helper Methods

  File: src/subprocess/async_executor.py

  def _compute_global_diff(self, before: dict, after: dict) -> dict:
      """Compute globals diff, filtering system variables."""
      updates = {}
      skip = {'__async_exec__', 'asyncio', '__builtins__'}

      for key, value in after.items():
          if key in skip or key in ENGINE_INTERNALS:
              continue
          if key.startswith('__') and key.endswith('__'):
              continue
          if key not in before or before[key] is not value:
              updates[key] = value

      return updates

  def _collect_safe_assigned_names(self, body: list) -> set:
      """Collect simple identifiers safe for global declaration."""
      names = set()

      for node in body:
          if isinstance(node, ast.Assign):
              for target in node.targets:
                  if isinstance(target, ast.Name):
                      if not target.id.startswith('__') and target.id not in
  ENGINE_INTERNALS:
                          names.add(target.id)
          elif isinstance(node, ast.AnnAssign):
              if isinstance(node.target, ast.Name):
                  if not node.target.id.startswith('__'):
                      names.add(node.target.id)
          elif isinstance(node, ast.AugAssign):
              if isinstance(node.target, ast.Name):
                  names.add(node.target.id)

      return names

  def _resolve_attribute_base(self, node: ast.AST) -> str:
      """Resolve attribute chain to base name."""
      while isinstance(node, ast.Attribute):
          node = node.value
      if isinstance(node, ast.Name):
          return node.id
      return None

  4. Dependency Injection Factory Pattern

  File: src/integration/resonate_wrapper.py (new)

  """Factory-based dependency injection for AsyncExecutor.

  Provides ready-to-use instances without temporal coupling.
  """

  from typing import Optional
  import asyncio
  from ..subprocess.async_executor import AsyncExecutor
  from ..subprocess.namespace import NamespaceManager

  class AwaitablePromise:
      """Adapter to make promises awaitable in async contexts."""

      def __init__(self):
          self._future: Optional[asyncio.Future] = None

      def _ensure_future(self) -> asyncio.Future:
          if self._future is None:
              loop = asyncio.get_running_loop()
              self._future = loop.create_future()
          return self._future

      def set_result(self, value) -> None:
          fut = self._ensure_future()
          if not fut.done():
              fut.set_result(value)

      def set_exception(self, exc: BaseException) -> None:
          fut = self._ensure_future()
          if not fut.done():
              fut.set_exception(exc)

      def __await__(self):
          return self._ensure_future().__await__()

  def async_executor_factory(
      ctx=None,
      namespace_manager: Optional[NamespaceManager] = None,
      transport=None,
      execution_id: Optional[str] = None
  ) -> AsyncExecutor:
      """Factory returning ready-to-use AsyncExecutor instances.

      No initialize() needed - instances are fully configured on creation.

      Usage in DI:
          resonate.set_dependency(
              "async_executor",
              lambda ctx: async_executor_factory(ctx),
              singleton=False
          )
      """
      ns = namespace_manager or NamespaceManager()
      exec_id = execution_id or getattr(ctx, 'execution_id', 'local-exec')
      return AsyncExecutor(namespace_manager=ns, transport=transport,
  execution_id=exec_id)

  5. Python 3.11+ Modern Patterns

  File: src/subprocess/async_executor.py (enhancements)

  5.1 CO_COROUTINE Flag Checking

  The CO_COROUTINE flag is the canonical way to detect if compiled code is a
  coroutine, used by IPython/Jupyter:

  import inspect
  
  # After compilation, check the flag
  compiled = compile(code, '<async_session>', 'exec', flags=flags)
  is_coroutine_code = bool(inspect.CO_COROUTINE & compiled.co_flags)
  
  # This is more reliable than runtime checks
  if is_coroutine_code:
      # Code will return a coroutine when executed
      pass

  5.2 Timeout with asyncio.timeout (Python 3.11+)

  Replace asyncio.wait_for with the cleaner asyncio.timeout context manager:

  # Instead of: result = await asyncio.wait_for(coro, timeout=30)
  async with asyncio.timeout(30):
      result = await coro
  
  # Benefits: Cleaner cancellation, better exception handling

  5.3 Exception Context with add_note (Python 3.11+)

  Enrich exceptions with execution context:

  try:
      result = await execute(code)
  except Exception as e:
      if hasattr(e, 'add_note'):
          e.add_note(f"Execution ID: {execution_id}")
          e.add_note(f"Code length: {len(code)} characters")
          e.add_note(f"Execution mode: {mode.value}")
      raise

  5.4 Structured Concurrency (Optional Future Enhancement)

  For parallel execution scenarios (future enhancement):

  async with asyncio.TaskGroup() as tg:
      task1 = tg.create_task(execute_code1())
      task2 = tg.create_task(execute_code2())
  # All tasks complete or all cancel on error

  5.5 Critical Limitation Note

  IMPORTANT: Top-level await ONLY works in interactive/REPL contexts.
  It cannot be used in importable modules - this is a Python language limitation,
  not an implementation choice. The PyCF_ALLOW_TOP_LEVEL_AWAIT flag enables
  compilation but the resulting code must be executed in an appropriate context.

  6. Testing Strategy

  6.1 Namespace Binding Tests

  File: tests/unit/test_async_executor_namespace_binding.py (new)

  Create comprehensive tests for globals binding:
  - Direct TLA path: functions bind to live globals
  - Direct TLA path: global assignments persist
  - AST fallback: functions bind to live globals
  - AST fallback: global assignments persist
  - AST fallback: functions see later global updates
  - CO_COROUTINE flag: verify flag is set with PyCF_ALLOW_TOP_LEVEL_AWAIT
  - CO_COROUTINE flag: verify flag matches actual coroutine behavior

  6.2 Blocking I/O Detection Tests

  File: tests/unit/test_async_executor.py (enhance)

  Add tests for:
  - Attribute calls: time.sleep(), requests.get(), socket.recv()
  - Import aliases: import requests as rq; rq.get()
  - From imports: from requests import get; get()
  - Nested attributes: client.session.get()
  - Database patterns: psycopg2.connect(), redis.Redis()
  - File I/O: pathlib.Path().read_text(), open().read()

  6.3 Edge Case Tests

  File: tests/unit/test_top_level_await.py (enhance)

  Add tests for:
  - def with await transformation
  - Zero-arg lambda with await transformation
  - Complex await expressions
  - Multiple sequential awaits
  - asyncio.timeout() cancellation behavior
  - Exception notes propagation

  6.4 Performance Test Stability

  File: tests/unit/test_top_level_await.py::TestPerformance

  def test_simple_await_performance(self):
      """Test await performance is reasonable."""
      start = time.perf_counter()  # Use monotonic clock
      # ... execute code ...
      elapsed = time.perf_counter() - start
      assert elapsed < 0.25, f"Execution took {elapsed:.3f}s, expected < 250ms"

  6.5 CO_COROUTINE Flag Tests

  File: tests/unit/test_top_level_await.py (enhance)

  async def test_co_coroutine_flag_detection(self):
      """Test CO_COROUTINE flag correctly indicates coroutine code."""
      code = "await asyncio.sleep(0)"
      flags = compile('', '', 'exec').co_flags | 0x2000
      compiled = compile(code, '<test>', 'exec', flags=flags)
      
      # Check flag is set
      import inspect
      assert bool(inspect.CO_COROUTINE & compiled.co_flags)
      
      # Verify execution returns coroutine
      result = eval(compiled, {'asyncio': asyncio}, {})
      assert inspect.iscoroutine(result)

  7. CI Integration

  File: .github/workflows/unit-tests.yml (new)

  name: Unit Tests

  on:
    pull_request:
      types: [opened, synchronize, reopened]
    push:
      branches: [main, master]

  jobs:
    unit:
      runs-on: ubuntu-latest
      timeout-minutes: 30
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: '3.11'
        - run: |
            pip install -e .[dev]
            pytest -m unit -v

  8. Documentation Updates

  8.1 Specification Updates

  File: docs/async_capability_prompts/current/21_spec_resonate_integration.md

  Update all DI examples to use factory pattern:
  # Before: temporal coupling
  executor = deps.get("async_executor")
  executor.initialize(namespace)  # Error-prone

  # After: factory pattern
  executor = deps.get("async_executor")(ctx)  # Ready to use

  8.2 Implementation Summary

  File: PHASE1_IMPLEMENTATION_SUMMARY.md (new)

  Document:
  - Problem statements and solutions
  - Architectural decisions
  - Test coverage improvements
  - Known limitations
  - Future recommendations

  Implementation Order

  1. Core TLA Implementation (Day 1)
    - Correct flag value usage (0x2000)
    - CO_COROUTINE flag checking implementation
    - Direct path with eval strategy
    - asyncio.timeout() integration
    - Globals snapshot/diff mechanism
    - Basic AST fallback
  2. Edge Case Handling (Day 2)
    - AST pre-transformations
    - Conservative global hoisting
    - Lambda and def transformations
    - Exception.add_note() error enrichment
    - Test validation
  3. Enhanced Detection (Day 3)
    - Blocking I/O with aliases
    - Extended blocking patterns (databases, file I/O)
    - Execution routing improvements
    - Comprehensive tests
  4. DI and Integration (Day 4)
    - Factory pattern implementation
    - Awaitable promise adapter
    - Documentation updates
    - CI configuration
  5. Testing and Polish (Day 5)
    - CO_COROUTINE flag tests
    - asyncio.timeout() tests
    - Test stability improvements
    - Performance test adjustments
    - Final validation
    - Documentation completion

  Acceptance Criteria

  Functional Requirements

  - ✅ Both TLA paths correctly bind function __globals__ to live namespace
  - ✅ Global assignments persist across executions
  - ✅ AST fallback handles edge cases (def with await, zero-arg lambdas)
  - ✅ Blocking I/O detection covers common patterns with alias resolution
  - ✅ Factory pattern eliminates temporal coupling in DI

  Test Requirements

  - ✅ All namespace binding tests pass (no xfails)
  - ✅ CO_COROUTINE flag detection tests verify correct behavior
  - ✅ asyncio.timeout() cancellation tests demonstrate proper cleanup
  - ✅ Exception notes properly propagate through error paths
  - ✅ Blocking I/O detection tests demonstrate accuracy
  - ✅ Edge case transformations tested
  - ✅ Performance tests stable in CI (<250ms threshold)
  - ✅ CI runs unit tests automatically

  Documentation Requirements

  - ✅ DI specification uses factory pattern throughout
  - ✅ Implementation summary documents decisions
  - ✅ Code includes clear comments for complex logic
  - ✅ Test coverage >90% for AsyncExecutor

  Key Technical Decisions

  1. Use Python's actual PyCF_ALLOW_TOP_LEVEL_AWAIT value (0x2000) directly without
  translation layers
  2. Check CO_COROUTINE flag on compiled code objects for reliable coroutine detection
  (canonical IPython/Jupyter pattern)
  3. Use asyncio.timeout() for execution timeouts (Python 3.11+ best practice)
  4. Enrich exceptions with add_note() for better debugging context
  5. Eval-first strategy for TLA to enable test control and expression optimization
  6. Conservative AST transformations only for safe, common patterns
  7. Globals snapshot/diff approach ensures correct precedence without namespace
  replacement
  8. Factory pattern for DI provides clean lifecycle management
  9. Comprehensive alias tracking in blocking I/O detection for real-world code
  patterns

  Implementation Notes

  - Always use asyncio.get_running_loop() not deprecated get_event_loop()
  - Maintain merge-only namespace policy throughout
  - Filter ENGINE_INTERNALS and dunder names in global diffs
  - Use time.perf_counter() for performance measurements
  - Keep AST transformations minimal and safe
  - Document "why" not just "what" in complex sections
  - Remember: top-level await ONLY works in interactive contexts, not modules
  - Use CO_COROUTINE flag checking before runtime coroutine checks
  - Apply exception notes for all error paths to aid debugging

  Forward Compatibility Notes

  Python 3.12+ Subinterpreters (PEP 684):
  - Design with potential migration from subprocesses to subinterpreters
  - Keep session state serializable for cross-interpreter transfer
  - Consider using interpreters module when available:
    if sys.version_info >= (3, 12) and hasattr(sys, '_interpreters'):
        # Use subinterpreter for better performance
        pass
    else:
        # Continue with subprocess isolation
        pass

  Python 3.13+ Free-Threading (PEP 703 - experimental):
  - No immediate changes needed
  - Future optimization opportunity for parallel execution
  - Monitor ecosystem readiness before adopting

  Begin implementation with thorough reading of specifications, then follow the
  implementation order systematically. Create granular todo lists for each phase and
  validate each component with tests before proceeding.
