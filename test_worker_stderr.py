"""
Test worker startup and check stderr for errors
"""
import asyncio
import sys

async def test_worker_stderr():
    """Start worker and capture stderr"""
    print("Starting worker subprocess...")
    
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "src.subprocess.worker", "test-session",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    print(f"Worker PID: {process.pid}")
    
    # Give it a moment to start
    await asyncio.sleep(0.5)
    
    # Check if process is still alive
    if process.returncode is not None:
        print(f"Worker exited with code: {process.returncode}")
        
    # Read any stderr output
    stderr_data = await process.stderr.read()
    if stderr_data:
        print("\n=== STDERR OUTPUT ===")
        print(stderr_data.decode('utf-8', errors='replace'))
    else:
        print("\nNo stderr output")
    
    # Check stdout
    try:
        stdout_data = await asyncio.wait_for(process.stdout.read(100), timeout=0.5)
        if stdout_data:
            print("\n=== STDOUT OUTPUT (first 100 bytes) ===")
            print(repr(stdout_data))
    except asyncio.TimeoutError:
        print("\nNo stdout data available")
    
    # Kill process
    process.kill()
    await process.wait()

if __name__ == "__main__":
    asyncio.run(test_worker_stderr())
