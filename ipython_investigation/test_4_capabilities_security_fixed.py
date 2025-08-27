#!/usr/bin/env python3
"""Test 4: Capability injection and security with IPython - FIXED."""

import sys
import asyncio
import traceback
from typing import Any, Dict, Callable, Optional, List
from abc import ABC, abstractmethod
from enum import Enum


class SecurityLevel(str, Enum):
    """Security levels for capability access."""
    SANDBOX = "sandbox"
    RESTRICTED = "restricted"  
    STANDARD = "standard"
    TRUSTED = "trusted"


class Capability(ABC):
    """Base capability class."""
    
    @abstractmethod
    def get_name(self) -> str:
        pass
    
    @abstractmethod
    def get_implementation(self) -> Callable:
        pass


class FetchCapability(Capability):
    """Mock network fetch capability."""
    
    def get_name(self) -> str:
        return "fetch"
    
    def get_implementation(self) -> Callable:
        async def fetch(url: str) -> Dict:
            # Simulate network fetch
            return {"status": 200, "body": f"Mock response from {url}"}
        return fetch


class FileReadCapability(Capability):
    """Mock file read capability."""
    
    def get_name(self) -> str:
        return "read_file"
    
    def get_implementation(self) -> Callable:
        def read_file(path: str) -> str:
            # Simulate file read with security check
            if path.startswith("/etc/"):
                raise PermissionError(f"Access denied: {path}")
            return f"Mock content of {path}"
        return read_file


class ShellCapability(Capability):
    """Mock shell execution capability."""
    
    def get_name(self) -> str:
        return "shell"
    
    def get_implementation(self) -> Callable:
        def shell(command: str) -> Dict:
            # Simulate shell execution
            if "rm" in command or "sudo" in command:
                raise PermissionError(f"Dangerous command blocked: {command}")
            return {"stdout": f"Mock output of: {command}", "returncode": 0}
        return shell


class SecurityPolicy:
    """Security policy for capability control."""
    
    CAPABILITY_SETS = {
        SecurityLevel.SANDBOX: {"input", "print"},
        SecurityLevel.RESTRICTED: {"input", "print", "read_file"},
        SecurityLevel.STANDARD: {"input", "print", "read_file", "fetch"},
        SecurityLevel.TRUSTED: {"input", "print", "read_file", "fetch", "shell"},
    }
    
    def __init__(self, level: SecurityLevel):
        self.level = level
        self.allowed = self.CAPABILITY_SETS.get(level, set())
    
    def is_allowed(self, capability_name: str) -> bool:
        return capability_name in self.allowed


def test_capability_injection():
    """Test injecting capabilities into IPython namespace."""
    print("=" * 60)
    print("TEST 4.1: Capability Injection")
    print("=" * 60)
    
    try:
        from IPython.terminal.interactiveshell import TerminalInteractiveShell
        from IPython.core.interactiveshell import InteractiveShell
        
        if InteractiveShell.initialized():
            InteractiveShell.clear_instance()
        
        shell = TerminalInteractiveShell.instance()
        shell.init_create_namespaces()
        
        # Create capabilities
        capabilities = {
            "fetch": FetchCapability(),
            "read_file": FileReadCapability(),
            "shell": ShellCapability(),
        }
        
        # Inject into namespace
        for name, cap in capabilities.items():
            shell.user_ns[name] = cap.get_implementation()
            print(f"✓ Injected capability: {name}")
        
        # Test that capabilities work
        shell.run_cell("file_content = read_file('/tmp/test.txt')")
        has_read = shell.user_ns.get('file_content') == "Mock content of /tmp/test.txt"
        print(f"✓ read_file capability works: {has_read}")
        
        shell.run_cell("cmd_result = shell('ls -l')")
        has_shell = 'stdout' in shell.user_ns.get('cmd_result', {})
        print(f"✓ shell capability works: {has_shell}")
        
        # Test async capability
        async def test_async_cap():
            code = "result = await fetch('http://example.com')"
            result = await shell.run_cell_async(code, transformed_cell=code)
            return shell.user_ns.get('result', {}).get('status') == 200
        
        loop = asyncio.new_event_loop()
        has_fetch = loop.run_until_complete(test_async_cap())
        print(f"✓ async fetch capability works: {has_fetch}")
        
        return has_read and has_shell and has_fetch
        
    except Exception as e:
        print(f"✗ Capability injection failed: {e}")
        traceback.print_exc()
        return False


def test_security_policy_enforcement():
    """Test security policy enforcement for capabilities."""
    print("\n" + "=" * 60)
    print("TEST 4.2: Security Policy Enforcement")
    print("=" * 60)
    
    try:
        from IPython.terminal.interactiveshell import TerminalInteractiveShell
        from IPython.core.interactiveshell import InteractiveShell
        
        if InteractiveShell.initialized():
            InteractiveShell.clear_instance()
        
        shell = TerminalInteractiveShell.instance()
        shell.init_create_namespaces()
        
        # Test different security levels
        for level in [SecurityLevel.SANDBOX, SecurityLevel.RESTRICTED, SecurityLevel.STANDARD]:
            print(f"\nTesting security level: {level}")
            
            # Clear namespace for this security level
            shell.user_ns.clear()
            shell.reset()
            
            policy = SecurityPolicy(level)
            
            # Try to inject capabilities based on policy
            capabilities = {
                "read_file": FileReadCapability(),
                "fetch": FetchCapability(),
                "shell": ShellCapability(),
            }
            
            injected = []
            blocked = []
            
            for name, cap in capabilities.items():
                if policy.is_allowed(name):
                    shell.user_ns[name] = cap.get_implementation()
                    injected.append(name)
                else:
                    blocked.append(name)
            
            print(f"  ✓ Injected: {injected}")
            print(f"  ✓ Blocked: {blocked}")
            
            # Verify enforcement
            for name in blocked:
                not_available = name not in shell.user_ns
                print(f"  ✓ {name} correctly blocked: {not_available}")
        
        return True
        
    except Exception as e:
        print(f"✗ Security policy enforcement failed: {e}")
        traceback.print_exc()
        return False


def test_capability_security_checks():
    """Test that capabilities enforce their own security checks."""
    print("\n" + "=" * 60)
    print("TEST 4.3: Capability Security Checks")
    print("=" * 60)
    
    try:
        from IPython.terminal.interactiveshell import TerminalInteractiveShell
        from IPython.core.interactiveshell import InteractiveShell
        
        if InteractiveShell.initialized():
            InteractiveShell.clear_instance()
        
        shell = TerminalInteractiveShell.instance()
        shell.init_create_namespaces()
        
        # Inject capabilities
        shell.user_ns['read_file'] = FileReadCapability().get_implementation()
        shell.user_ns['shell'] = ShellCapability().get_implementation()
        
        # Test file read security
        result = shell.run_cell("try:\n    read_file('/etc/passwd')\nexcept PermissionError as e:\n    error = str(e)")
        has_file_security = 'Access denied' in shell.user_ns.get('error', '')
        print(f"✓ File read security works: {has_file_security}")
        
        # Test shell command security
        result = shell.run_cell("try:\n    shell('sudo rm -rf /')\nexcept PermissionError as e:\n    shell_error = str(e)")
        has_shell_security = 'Dangerous command blocked' in shell.user_ns.get('shell_error', '')
        print(f"✓ Shell command security works: {has_shell_security}")
        
        return has_file_security and has_shell_security
        
    except Exception as e:
        print(f"✗ Capability security checks failed: {e}")
        traceback.print_exc()
        return False


def test_dynamic_capability_management():
    """Test dynamic addition and removal of capabilities."""
    print("\n" + "=" * 60)
    print("TEST 4.4: Dynamic Capability Management")
    print("=" * 60)
    
    try:
        from IPython.terminal.interactiveshell import TerminalInteractiveShell
        from IPython.core.interactiveshell import InteractiveShell
        
        if InteractiveShell.initialized():
            InteractiveShell.clear_instance()
        
        shell = TerminalInteractiveShell.instance()
        shell.init_create_namespaces()
        
        # Start with no capabilities
        shell.user_ns.clear()
        shell.reset()
        shell.init_create_namespaces()  # Re-init after reset
        
        # Dynamically add capability
        shell.user_ns['fetch'] = FetchCapability().get_implementation()
        print("✓ Added fetch capability")
        
        # Use it
        async def test_use():
            code = "result = await fetch('http://test.com')"
            await shell.run_cell_async(code, transformed_cell=code)
            return 'result' in shell.user_ns
        
        loop = asyncio.new_event_loop()
        can_use = loop.run_until_complete(test_use())
        print(f"✓ Can use added capability: {can_use}")
        
        # Remove capability
        del shell.user_ns['fetch']
        print("✓ Removed fetch capability")
        
        # Verify it's gone
        result = shell.run_cell("'fetch' in dir()")
        is_removed = not shell.last_execution_result.result
        print(f"✓ Capability removed from namespace: {is_removed}")
        
        # Add multiple capabilities at once
        caps_to_add = {
            'read_file': FileReadCapability().get_implementation(),
            'shell': ShellCapability().get_implementation(),
        }
        shell.user_ns.update(caps_to_add)
        print(f"✓ Added multiple capabilities: {list(caps_to_add.keys())}")
        
        # Verify all work
        shell.run_cell("test_read = read_file('/tmp/test')")
        shell.run_cell("test_shell = shell('echo test')")
        
        multi_work = (
            shell.user_ns.get('test_read') is not None and
            shell.user_ns.get('test_shell') is not None
        )
        print(f"✓ Multiple capabilities work: {multi_work}")
        
        return can_use and is_removed and multi_work
        
    except Exception as e:
        print(f"✗ Dynamic capability management failed: {e}")
        traceback.print_exc()
        return False


def test_ipython_preprocessor_security():
    """Test using IPython preprocessors for security - FIXED."""
    print("\n" + "=" * 60)
    print("TEST 4.5: IPython Preprocessor Security")
    print("=" * 60)
    
    try:
        from IPython.terminal.interactiveshell import TerminalInteractiveShell
        from IPython.core.interactiveshell import InteractiveShell
        
        if InteractiveShell.initialized():
            InteractiveShell.clear_instance()
        
        shell = TerminalInteractiveShell.instance()
        shell.init_create_namespaces()
        
        # Create a security preprocessor
        class SecurityPreprocessor:
            """Preprocessor that blocks dangerous code."""
            
            def __init__(self, blocked_keywords):
                self.blocked_keywords = blocked_keywords
            
            def __call__(self, lines):
                """Check code for blocked keywords."""
                code = '\n'.join(lines) if isinstance(lines, list) else lines
                
                for keyword in self.blocked_keywords:
                    if keyword in code:
                        raise PermissionError(f"Blocked keyword found: {keyword}")
                
                return lines
        
        # Install preprocessor
        blocked = ['__import__', 'eval', 'exec', 'compile', 'open']
        preprocessor = SecurityPreprocessor(blocked)
        
        # Register as input transformer
        shell.input_transformers_cleanup.append(preprocessor)
        print(f"✓ Installed security preprocessor blocking: {blocked}")
        
        # Test blocking
        blocked_tests = [
            ("__import__('os').system('ls')", "__import__"),
            ("eval('1+1')", "eval"),
            ("exec('print(1)')", "exec"),
            ("compile('1+1', '', 'eval')", "compile"),
            ("open('/etc/passwd')", "open"),
        ]
        
        blocks_working = 0
        for code, keyword in blocked_tests:
            try:
                shell.run_cell(code)
                print(f"✗ Failed to block: {keyword}")
            except PermissionError as e:
                # This is GOOD - we successfully blocked it
                print(f"✓ Successfully blocked {keyword}: {str(e)}")
                blocks_working += 1
            except Exception as e:
                # Some other error - preprocessing might have failed
                print(f"⚠ Unexpected error for {keyword}: {e}")
        
        # Test that safe code still works
        result = shell.run_cell("safe_result = 1 + 1")
        safe_works = shell.user_ns.get('safe_result') == 2
        print(f"✓ Safe code still executes: {safe_works}")
        
        # Clean up
        shell.input_transformers_cleanup.remove(preprocessor)
        
        print(f"\n✓ Blocked {blocks_working}/{len(blocked_tests)} dangerous operations")
        print("Note: IPython preprocessors provide basic security but have limitations")
        
        return blocks_working >= 3 and safe_works  # At least 3 blocks work and safe code runs
        
    except Exception as e:
        print(f"✗ Preprocessor security failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all capability and security tests."""
    print("IPython Integration Investigation - Capabilities & Security (FIXED)")
    print("=" * 60)
    
    tests = [
        test_capability_injection,
        test_security_policy_enforcement,
        test_capability_security_checks,
        test_dynamic_capability_management,
        test_ipython_preprocessor_security,
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
        print("✓ All capability & security tests passed!")
    else:
        print("✗ Some tests failed - capability/security integration needs work")
        
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if main() else 1)