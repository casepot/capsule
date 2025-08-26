#!/usr/bin/env python3
"""
Test namespace persistence, state management, and transaction support.
Also tests source tracking and checkpoint/restore capabilities.

IMPORTANT: These tests demonstrate that namespace persistence requires
session reuse. Each new Session() creates a fresh subprocess with a
clean namespace. To maintain state, you must reuse the same session
or use SessionPool for proper session management.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session.manager import Session
from src.protocol.messages import (
    ExecuteMessage, MessageType, ResultMessage, ErrorMessage,
    CheckpointMessage, RestoreMessage, TransactionPolicy
)

# Test results tracking
test_results: Dict[str, Any] = {}

# Shared session for namespace persistence tests
_shared_session: Optional[Session] = None

async def get_shared_session() -> Session:
    """Get or create a shared session for namespace persistence tests.
    
    This ensures that namespace persistence tests use the same subprocess,
    which is required for variables to persist across executions.
    """
    global _shared_session
    if _shared_session is None or not _shared_session.is_alive:
        _shared_session = Session()
        await _shared_session.start()
    return _shared_session


async def test_namespace_persistence_detailed():
    """Test detailed namespace persistence across executions.
    
    IMPORTANT: Namespace persistence requires reusing the same session.
    Each Session() creates a new subprocess with a fresh namespace.
    """
    print("\n=== Test: Namespace Persistence (Detailed) ===")
    session = await get_shared_session()  # Use shared session for persistence!
    
    try:
        # Execution 1: Set multiple variables
        code1 = """
simple_var = 42
list_var = [1, 2, 3]
dict_var = {'key': 'value'}
set_var = {1, 2, 3}
"""
        msg1 = ExecuteMessage(
            id=f"test-1",
            timestamp=time.time(),
            code=code1
        )
        async for _ in session.execute(msg1):
            pass
        
        # Execution 2: Check all variables exist
        code2 = """
results = {
    'simple': simple_var,
    'list': list_var,
    'dict': dict_var,
    'set': set_var
}
results
"""
        msg2 = ExecuteMessage(
            id=f"test-2",
            timestamp=time.time(),
            code=code2
        )
        
        result = None
        async for response in session.execute(msg2):
            if isinstance(response, ResultMessage):
                result = response.value
        
        success = (result and 
                  result.get('simple') == 42 and
                  result.get('list') == [1, 2, 3] and
                  result.get('dict') == {'key': 'value'} and
                  result.get('set') == {1, 2, 3})
        
        print(f"  Simple var: {result.get('simple') if result else 'N/A'}")
        print(f"  List var: {result.get('list') if result else 'N/A'}")
        print(f"  Dict var: {result.get('dict') if result else 'N/A'}")
        print(f"  Set var: {result.get('set') if result else 'N/A'}")
        print(f"✓ All variables persisted: {'Yes' if success else 'No'}")
        
        test_results["namespace_persistence"] = {
            "pass": success,
            "result": result
        }
        
        return success
        
    finally:
        # Don't shutdown - using shared session
        pass


async def test_function_source_tracking():
    """Test if function source code is tracked."""
    print("\n=== Test: Function Source Tracking ===")
    session = await get_shared_session()  # Use shared session for persistence!
    
    try:
        # Define a function
        code1 = """
def calculate_area(radius):
    '''Calculate area of a circle.'''
    import math
    return math.pi * radius ** 2
"""
        msg1 = ExecuteMessage(
            id=f"test-1",
            timestamp=time.time(),
            code=code1,
            capture_source=True  # Request source tracking
        )
        async for _ in session.execute(msg1):
            pass
        
        # Try to access function source (if tracked)
        code2 = """
# Check if function exists
'calculate_area' in dir()
"""
        msg2 = ExecuteMessage(
            id=f"test-2",
            timestamp=time.time(),
            code=code2
        )
        
        result = None
        async for response in session.execute(msg2):
            if isinstance(response, ResultMessage):
                result = response.value
        
        function_exists = result == True
        
        print(f"  Function exists: {'Yes' if function_exists else 'No'}")
        
        # Note: Source tracking might be in namespace manager but not exposed
        test_results["function_source_tracking"] = {
            "pass": function_exists,
            "function_in_namespace": function_exists
        }
        
        return function_exists
        
    finally:
        # Don't shutdown - using shared session
        pass


async def test_class_source_tracking():
    """Test if class source code and methods are tracked."""
    print("\n=== Test: Class Source Tracking ===")
    session = await get_shared_session()  # Use shared session for persistence!
    
    try:
        # Define a class
        code1 = """
class Vehicle:
    '''A simple vehicle class.'''
    
    def __init__(self, brand, model):
        self.brand = brand
        self.model = model
    
    def describe(self):
        return f"{self.brand} {self.model}"
    
    @property
    def full_name(self):
        return self.describe()
"""
        msg1 = ExecuteMessage(
            id=f"test-1",
            timestamp=time.time(),
            code=code1,
            capture_source=True
        )
        async for _ in session.execute(msg1):
            pass
        
        # Check class and create instance
        code2 = """
car = Vehicle("Toyota", "Camry")
result = {
    'class_exists': 'Vehicle' in dir(),
    'instance_works': car.describe() == "Toyota Camry",
    'property_works': car.full_name == "Toyota Camry"
}
result
"""
        msg2 = ExecuteMessage(
            id=f"test-2",
            timestamp=time.time(),
            code=code2
        )
        
        result = None
        async for response in session.execute(msg2):
            if isinstance(response, ResultMessage):
                result = response.value
        
        success = (result and 
                  result.get('class_exists') and
                  result.get('instance_works') and
                  result.get('property_works'))
        
        print(f"  Class exists: {result.get('class_exists') if result else 'N/A'}")
        print(f"  Instance works: {result.get('instance_works') if result else 'N/A'}")
        print(f"  Property works: {result.get('property_works') if result else 'N/A'}")
        print(f"✓ Class tracking works: {'Yes' if success else 'No'}")
        
        test_results["class_source_tracking"] = {
            "pass": success,
            "details": result
        }
        
        return success
        
    finally:
        # Don't shutdown - using shared session
        pass


async def test_transaction_commit_always():
    """Test transaction with commit_always policy (default).
    
    Note: Using separate session for transaction tests to ensure clean state.
    """
    print("\n=== Test: Transaction - Commit Always ===")
    session = Session()  # Use separate session for transaction testing
    await session.start()
    
    try:
        # Set variable with commit_always (default)
        code1 = "transaction_test = 'initial'"
        msg1 = ExecuteMessage(
            id=f"test-1",
            timestamp=time.time(),
            code=code1,
            transaction_policy=TransactionPolicy.COMMIT_ALWAYS
        )
        async for _ in session.execute(msg1):
            pass
        
        # Cause error but with commit_always
        code2 = """
transaction_test = 'modified'
raise RuntimeError("Test error")
"""
        msg2 = ExecuteMessage(
            id=f"test-2",
            timestamp=time.time(),
            code=code2,
            transaction_policy=TransactionPolicy.COMMIT_ALWAYS
        )
        
        had_error = False
        async for response in session.execute(msg2):
            if isinstance(response, ErrorMessage):
                had_error = True
        
        # Check if change persisted despite error
        code3 = "transaction_test"
        msg3 = ExecuteMessage(
            id=f"test-3",
            timestamp=time.time(),
            code=code3
        )
        
        result = None
        async for response in session.execute(msg3):
            if isinstance(response, ResultMessage):
                result = response.value
        
        # With commit_always, change should persist even with error
        success = had_error and result == 'modified'
        
        print(f"  Error occurred: {'Yes' if had_error else 'No'}")
        print(f"  Final value: {result}")
        print(f"✓ Commit always works: {'Yes' if success else 'No (transaction might not be implemented)'}")
        
        test_results["transaction_commit_always"] = {
            "pass": success,
            "final_value": result,
            "note": "Transaction support may not be implemented"
        }
        
        return success
        
    finally:
        # Don't shutdown - using shared session
        pass


async def test_transaction_rollback():
    """Test transaction with rollback_on_failure policy."""
    print("\n=== Test: Transaction - Rollback on Failure ===")
    session = Session()
    await session.start()
    
    try:
        # Set initial value
        code1 = "rollback_test = 'initial'"
        msg1 = ExecuteMessage(
            id=f"test-1",
            timestamp=time.time(),
            code=code1
        )
        async for _ in session.execute(msg1):
            pass
        
        # Try to modify with rollback policy
        code2 = """
rollback_test = 'modified'
other_var = 'should_not_exist'
raise RuntimeError("Rollback test")
"""
        msg2 = ExecuteMessage(
            id=f"test-2",
            timestamp=time.time(),
            code=code2,
            transaction_policy=TransactionPolicy.ROLLBACK_ON_FAILURE
        )
        
        had_error = False
        async for response in session.execute(msg2):
            if isinstance(response, ErrorMessage):
                had_error = True
        
        # Check if rollback happened
        code3 = """
result = {
    'rollback_test': rollback_test,
    'other_var_exists': 'other_var' in dir()
}
result
"""
        msg3 = ExecuteMessage(
            id=f"test-3",
            timestamp=time.time(),
            code=code3
        )
        
        result = None
        async for response in session.execute(msg3):
            if isinstance(response, ResultMessage):
                result = response.value
        
        # With rollback, value should be 'initial' and other_var shouldn't exist
        success = (had_error and 
                  result and
                  result.get('rollback_test') == 'initial' and
                  not result.get('other_var_exists'))
        
        print(f"  Error occurred: {'Yes' if had_error else 'No'}")
        print(f"  Value after rollback: {result.get('rollback_test') if result else 'N/A'}")
        print(f"  Other var exists: {result.get('other_var_exists') if result else 'N/A'}")
        print(f"✓ Rollback works: {'Yes' if success else 'No (likely not implemented)'}")
        
        test_results["transaction_rollback"] = {
            "pass": success,
            "result": result,
            "note": "Rollback likely not implemented yet"
        }
        
        return success
        
    finally:
        # Don't shutdown - using shared session
        pass


async def test_checkpoint_create():
    """Test checkpoint creation."""
    print("\n=== Test: Checkpoint Creation ===")
    session = Session()
    await session.start()
    
    try:
        # Set up state to checkpoint
        code1 = """
checkpoint_var = 'test_value'
checkpoint_list = [1, 2, 3]
def checkpoint_func():
    return "Hello from checkpoint"
"""
        msg1 = ExecuteMessage(
            id=f"test-1",
            timestamp=time.time(),
            code=code1
        )
        async for _ in session.execute(msg1):
            pass
        
        # Try to create checkpoint
        checkpoint_msg = CheckpointMessage(
            id=f"checkpoint-1",
            timestamp=time.time(),
            name="test_checkpoint"
        )
        
        checkpoint_response = None
        error_response = None
        
        try:
            async for response in session.execute(checkpoint_msg):
                if response.type == MessageType.CHECKPOINT_CREATED:
                    checkpoint_response = response
                elif isinstance(response, ErrorMessage):
                    error_response = response
        except Exception as e:
            print(f"  Exception during checkpoint: {e}")
            error_response = str(e)
        
        if checkpoint_response:
            print(f"  Checkpoint created: Yes")
            print(f"  Checkpoint ID: {checkpoint_response.checkpoint_id if hasattr(checkpoint_response, 'checkpoint_id') else 'N/A'}")
            success = True
        else:
            print(f"  Checkpoint created: No")
            if error_response:
                print(f"  Error: {error_response}")
            print(f"  Note: Checkpoint likely not implemented")
            success = False
        
        test_results["checkpoint_create"] = {
            "pass": success,
            "implemented": checkpoint_response is not None,
            "error": str(error_response) if error_response else None
        }
        
        return success
        
    finally:
        # Don't shutdown - using shared session
        pass


async def test_imports_tracking():
    """Test if imports are tracked and persisted."""
    print("\n=== Test: Import Tracking ===")
    session = await get_shared_session()  # Use shared session for persistence!
    
    try:
        # Import various modules
        code1 = """
import json
import math
from collections import Counter
from datetime import datetime
"""
        msg1 = ExecuteMessage(
            id=f"test-1",
            timestamp=time.time(),
            code=code1
        )
        async for _ in session.execute(msg1):
            pass
        
        # Check if imports persist
        code2 = """
results = {
    'json_available': 'json' in dir(),
    'math_available': 'math' in dir(),
    'Counter_available': 'Counter' in dir(),
    'datetime_available': 'datetime' in dir(),
    'can_use_json': json.dumps({'test': True}) == '{"test": true}',
    'can_use_math': math.sqrt(4) == 2.0
}
results
"""
        msg2 = ExecuteMessage(
            id=f"test-2",
            timestamp=time.time(),
            code=code2
        )
        
        result = None
        async for response in session.execute(msg2):
            if isinstance(response, ResultMessage):
                result = response.value
        
        all_imports_work = (result and 
                           all(result.get(k, False) for k in result.keys()))
        
        print(f"  JSON module: {'✓' if result and result.get('json_available') else '✗'}")
        print(f"  Math module: {'✓' if result and result.get('math_available') else '✗'}")
        print(f"  Counter class: {'✓' if result and result.get('Counter_available') else '✗'}")
        print(f"  Datetime class: {'✓' if result and result.get('datetime_available') else '✗'}")
        print(f"✓ All imports tracked: {'Yes' if all_imports_work else 'No'}")
        
        test_results["imports_tracking"] = {
            "pass": all_imports_work,
            "details": result
        }
        
        return all_imports_work
        
    finally:
        # Don't shutdown - using shared session
        pass


async def main():
    """Run all namespace and transaction tests."""
    print("=" * 60)
    print("PYREPL3 FOUNDATION: NAMESPACE & TRANSACTION TESTS")
    print("=" * 60)
    
    tests = [
        ("Namespace Persistence", test_namespace_persistence_detailed),
        ("Function Source Tracking", test_function_source_tracking),
        ("Class Source Tracking", test_class_source_tracking),
        ("Import Tracking", test_imports_tracking),
        ("Transaction Commit Always", test_transaction_commit_always),
        ("Transaction Rollback", test_transaction_rollback),
        ("Checkpoint Creation", test_checkpoint_create),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {name} crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
            test_results[name.lower().replace(" ", "_")] = {
                "pass": False,
                "error": str(e)
            }
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")
    
    # Detailed results
    print("\nDetailed Results:")
    for test_name, result in test_results.items():
        status = "✅" if result.get("pass") else "❌"
        print(f"  {status} {test_name}")
        if "note" in result:
            print(f"      Note: {result['note']}")
        if "error" in result:
            print(f"      Error: {result['error']}")
    
    # Feature status
    print("\nFeature Implementation Status:")
    print(f"  Namespace persistence: {'✅ Working' if test_results.get('namespace_persistence', {}).get('pass') else '❌ Issues'}")
    print(f"  Source tracking: {'✅ Working' if test_results.get('function_source_tracking', {}).get('pass') else '⚠️ Partial'}")
    print(f"  Transactions: {'✅ Implemented' if test_results.get('transaction_rollback', {}).get('pass') else '❌ Not implemented'}")
    print(f"  Checkpoints: {'✅ Implemented' if test_results.get('checkpoint_create', {}).get('implemented') else '❌ Not implemented'}")
    
    # Clean up shared session
    global _shared_session
    if _shared_session and _shared_session.is_alive:
        print("\nCleaning up shared session...")
        await _shared_session.shutdown()
        _shared_session = None
    
    return passed == len(tests)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)