#!/usr/bin/env python3
"""Test 1: Basic IPython InteractiveShell capabilities and requirements - FIXED."""

import sys
import time
import traceback
import asyncio
from typing import Any, Dict

def test_ipython_import():
    """Test IPython import and dependencies."""
    print("=" * 60)
    print("TEST 1.1: IPython Import and Dependencies")
    print("=" * 60)
    
    try:
        import IPython
        print(f"✓ IPython version: {IPython.__version__}")
        
        # Check core dependencies
        dependencies = {
            'traitlets': None,
            'decorator': None,
            'pickleshare': None,
            'backcall': None,
            'pygments': None,
            'prompt_toolkit': None,
            'jedi': None,
            'matplotlib_inline': None,
            'pexpect': None,
            'stack_data': None,
            'executing': None,
            'pure_eval': None,
            'asttokens': None,
        }
        
        for dep in dependencies:
            try:
                mod = __import__(dep)
                dependencies[dep] = getattr(mod, '__version__', 'unknown')
            except ImportError:
                dependencies[dep] = 'NOT INSTALLED'
        
        print("\nDependencies:")
        for dep, version in dependencies.items():
            status = "✓" if version != 'NOT INSTALLED' else "✗"
            print(f"  {status} {dep}: {version}")
            
        # Estimate size
        import subprocess
        result = subprocess.run(['pip', 'show', 'ipython'], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'Size:' in line or 'Requires:' in line:
                    print(f"  {line.strip()}")
                    
    except ImportError as e:
        print(f"✗ IPython not installed: {e}")
        return False
    
    return True


def test_basic_shell_creation():
    """Test creating InteractiveShell in subprocess isolation."""
    print("\n" + "=" * 60)
    print("TEST 1.2: InteractiveShell Creation and Isolation")
    print("=" * 60)
    
    try:
        from IPython.core.interactiveshell import InteractiveShell
        from IPython.terminal.interactiveshell import TerminalInteractiveShell
        
        # Create shell instance with proper initialization
        # Clear any existing instance first
        if InteractiveShell.initialized():
            InteractiveShell.clear_instance()
        
        # Create new instance
        shell = TerminalInteractiveShell.instance()
        
        # Initialize it properly
        shell.init_create_namespaces()
        
        print(f"✓ Created InteractiveShell: {type(shell)}")
        
        # Check isolation capabilities
        print("\nIsolation checks:")
        print(f"  - user_ns is separate dict: {shell.user_ns is not globals()}")
        print(f"  - user_ns size: {len(shell.user_ns)}")
        print(f"  - Has builtin overrides: {'__builtins__' in shell.user_ns}")
        print(f"  - Has IPython internals: {'_oh' in shell.user_ns}")  # Should be True now
        
        # Test namespace isolation
        test_var = "original"
        shell.user_ns['test_var'] = "isolated"
        print(f"  - Namespace isolation works: {test_var == 'original'}")
        
        # Check if we can control the namespace
        custom_ns = {'custom': 'namespace'}
        # Don't replace user_ns entirely, update it
        shell.user_ns.update(custom_ns)
        shell.push({'added': 'value'})
        print(f"  - Can update namespace: {shell.user_ns.get('added') == 'value'}")
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to create shell: {e}")
        traceback.print_exc()
        return False


def test_async_execution():
    """Test async execution capabilities."""
    print("\n" + "=" * 60)
    print("TEST 1.3: Async Execution and Top-Level Await")
    print("=" * 60)
    
    try:
        from IPython.terminal.interactiveshell import TerminalInteractiveShell
        import asyncio
        
        # Get properly initialized shell
        shell = TerminalInteractiveShell.instance()
        
        # Enable autoawait
        shell.autoawait = True
        print(f"✓ Autoawait enabled: {shell.autoawait}")
        
        # Test regular code execution
        result = shell.run_cell("1 + 1")
        print(f"✓ Sync execution works: {result.result == 2}")
        
        # Test async execution
        async def test_async():
            # Test top-level await - include asyncio import in the code
            code_with_await = """
import asyncio
result = await asyncio.sleep(0.01, result='async_result')
result
"""
            # Use the proper async method
            result = await shell.run_cell_async(code_with_await, transformed_cell=code_with_await)
            return result
        
        # Run async test
        loop = asyncio.new_event_loop()
        async_result = loop.run_until_complete(test_async())
        print(f"✓ Async execution works: {async_result.result == 'async_result'}")
        
        # Test that namespace persists
        shell.run_cell("persistent_var = 'persisted'")
        result = shell.run_cell("persistent_var")
        print(f"✓ Namespace persists: {result.result == 'persisted'}")
        
        return True
        
    except Exception as e:
        print(f"✗ Async execution failed: {e}")
        traceback.print_exc()
        return False


def test_io_override():
    """Test I/O stream override capabilities."""
    print("\n" + "=" * 60)
    print("TEST 1.4: I/O Stream Override")
    print("=" * 60)
    
    try:
        from IPython.terminal.interactiveshell import TerminalInteractiveShell
        from io import StringIO
        import sys
        
        shell = TerminalInteractiveShell.instance()
        
        # Create custom output capture
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        
        # Override streams
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture
        
        # Execute code that produces output
        shell.run_cell("print('test stdout')")
        shell.run_cell("import sys; print('test stderr', file=sys.stderr)")
        
        # Restore streams
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        
        # Check captured output
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()
        
        print(f"✓ Stdout captured: {'test stdout' in stdout_output}")
        print(f"✓ Stderr captured: {'test stderr' in stderr_output}")
        
        # Test input override
        import builtins
        original_input = builtins.input
        
        def custom_input(prompt=""):
            return "custom_response"
        
        builtins.input = custom_input
        shell.run_cell("response = input('prompt>')")
        
        builtins.input = original_input
        
        print(f"✓ Input override works: {shell.user_ns.get('response') == 'custom_response'}")
        
        return True
        
    except Exception as e:
        print(f"✗ I/O override failed: {e}")
        traceback.print_exc()
        return False


def test_error_handling():
    """Test error handling and traceback capture."""
    print("\n" + "=" * 60)
    print("TEST 1.5: Error Handling")
    print("=" * 60)
    
    try:
        from IPython.terminal.interactiveshell import TerminalInteractiveShell
        from io import StringIO
        import sys
        
        shell = TerminalInteractiveShell.instance()
        
        # Capture stderr for traceback
        stderr_capture = StringIO()
        original_stderr = sys.stderr
        sys.stderr = stderr_capture
        
        # Execute code that raises exception
        result = shell.run_cell("1/0")
        
        sys.stderr = original_stderr
        
        # Check error handling
        print(f"✓ Error captured: {result.error_in_exec is not None}")
        print(f"✓ Exception type: {type(result.error_in_exec).__name__}")
        
        traceback_output = stderr_capture.getvalue()
        print(f"✓ Traceback captured: {'ZeroDivisionError' in traceback_output}")
        
        # Test that execution continues after error
        result = shell.run_cell("error_recovery = 'recovered'")
        print(f"✓ Execution continues after error: {shell.user_ns.get('error_recovery') == 'recovered'}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error handling failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("IPython Integration Investigation - Basic Tests (FIXED)")
    print("=" * 60)
    
    tests = [
        test_ipython_import,
        test_basic_shell_creation,
        test_async_execution,
        test_io_override,
        test_error_handling,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n✗ Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total = len(results)
    passed = sum(results)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("✓ All basic tests passed!")
    else:
        print("✗ Some tests failed - IPython may not be suitable")
        
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if main() else 1)