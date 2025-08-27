"""Tests for on-demand rate limiter implementation."""

import asyncio
import pytest
import time
from typing import List
from unittest.mock import Mock, patch

from src.protocol.framing import RateLimiter


class TestRateLimiterBasics:
    """Test basic rate limiting functionality."""
    
    @pytest.mark.asyncio
    async def test_basic_rate_limiting(self):
        """Test that rate limiter enforces the configured rate."""
        limiter = RateLimiter(max_messages_per_second=10, burst_size=1)
        
        start = time.perf_counter()
        
        # First acquire should be immediate (burst)
        await limiter.acquire()
        first_time = time.perf_counter() - start
        assert first_time < 0.01, "First acquire should be immediate"
        
        # Second acquire should wait ~100ms (1/10 second)
        await limiter.acquire()
        second_time = time.perf_counter() - start
        assert 0.09 < second_time < 0.12, f"Second acquire should wait ~100ms, got {second_time*1000:.1f}ms"
        
        # Third acquire should wait another ~100ms
        await limiter.acquire()
        third_time = time.perf_counter() - start
        assert 0.19 < third_time < 0.22, f"Third acquire should total ~200ms, got {third_time*1000:.1f}ms"
    
    @pytest.mark.asyncio
    async def test_burst_capacity(self):
        """Test that burst capacity allows multiple immediate acquires."""
        limiter = RateLimiter(max_messages_per_second=10, burst_size=3)
        
        start = time.perf_counter()
        
        # First 3 acquires should be immediate (burst capacity)
        for i in range(3):
            await limiter.acquire()
            elapsed = time.perf_counter() - start
            assert elapsed < 0.01, f"Burst acquire {i+1} should be immediate"
        
        # Fourth acquire should wait
        await limiter.acquire()
        elapsed = time.perf_counter() - start
        assert elapsed > 0.09, "Fourth acquire should wait after burst exhausted"
    
    @pytest.mark.asyncio
    async def test_token_replenishment(self):
        """Test that tokens replenish at the correct rate."""
        limiter = RateLimiter(max_messages_per_second=10, burst_size=2)
        
        # Exhaust burst
        await limiter.acquire()
        await limiter.acquire()
        
        # Wait for partial replenishment (50ms = 0.5 tokens)
        await asyncio.sleep(0.05)
        
        start = time.perf_counter()
        await limiter.acquire()
        elapsed = time.perf_counter() - start
        
        # Should wait ~50ms for the remaining 0.5 tokens
        assert 0.04 < elapsed < 0.07, f"Should wait ~50ms for remaining tokens, got {elapsed*1000:.1f}ms"
    
    @pytest.mark.asyncio
    async def test_try_acquire(self):
        """Test non-blocking try_acquire method."""
        limiter = RateLimiter(max_messages_per_second=10, burst_size=1)
        
        # First should succeed
        assert limiter.try_acquire() is True, "First try_acquire should succeed"
        
        # Second should fail immediately
        assert limiter.try_acquire() is False, "Second try_acquire should fail"
        
        # Wait for token replenishment
        await asyncio.sleep(0.11)
        
        # Should succeed again
        assert limiter.try_acquire() is True, "try_acquire should succeed after replenishment"


class TestRateLimiterConcurrency:
    """Test rate limiter under concurrent load."""
    
    @pytest.mark.asyncio
    async def test_concurrent_acquires(self):
        """Test that multiple concurrent acquires are handled correctly."""
        limiter = RateLimiter(max_messages_per_second=10, burst_size=1)
        
        acquire_times = []
        
        async def acquire_and_record():
            await limiter.acquire()
            acquire_times.append(time.perf_counter())
        
        # Start 5 concurrent acquires
        start_time = time.perf_counter()
        tasks = [
            asyncio.create_task(acquire_and_record())
            for _ in range(5)
        ]
        
        await asyncio.gather(*tasks)
        
        # Calculate intervals between acquires
        intervals = []
        for i in range(1, len(acquire_times)):
            intervals.append(acquire_times[i] - acquire_times[i-1])
        
        # First acquire should be immediate
        first_delay = acquire_times[0] - start_time
        assert first_delay < 0.01, f"First acquire should be immediate, took {first_delay*1000:.1f}ms"
        
        # Rest should be spaced ~100ms apart (with some tolerance for scheduling)
        for i, interval in enumerate(intervals):
            assert 0.08 < interval < 0.12, \
                f"Interval {i+1} should be ~100ms, got {interval*1000:.1f}ms"
    
    @pytest.mark.asyncio
    async def test_fairness_under_contention(self):
        """Test that rate limiter doesn't starve any waiters."""
        limiter = RateLimiter(max_messages_per_second=100, burst_size=1)
        
        acquire_times = {}
        start_time = time.perf_counter()
        
        async def acquire_with_id(task_id: int):
            await limiter.acquire()
            acquire_times[task_id] = time.perf_counter() - start_time
        
        # Create 10 concurrent tasks
        tasks = [
            asyncio.create_task(acquire_with_id(i))
            for i in range(10)
        ]
        
        await asyncio.gather(*tasks)
        
        # Check that no task was starved (all should complete within reasonable time)
        max_wait = max(acquire_times.values())
        min_wait = min(acquire_times.values())
        
        # With 100 msgs/sec and 10 tasks, worst case should be ~100ms
        assert max_wait < 0.15, f"Some task waited too long: {max_wait*1000:.1f}ms"
        
        # The spread shouldn't be too large (no severe starvation)
        spread = max_wait - min_wait
        assert spread < 0.1, f"Too much variance in wait times: {spread*1000:.1f}ms"
    
    @pytest.mark.asyncio
    async def test_no_busy_waiting(self):
        """Test that acquire doesn't busy-wait when rate limited."""
        limiter = RateLimiter(max_messages_per_second=10, burst_size=1)
        
        # Exhaust burst
        await limiter.acquire()
        
        # Mock sleep to count calls
        sleep_count = 0
        original_sleep = asyncio.sleep
        
        async def counting_sleep(duration):
            nonlocal sleep_count
            sleep_count += 1
            await original_sleep(duration)
        
        with patch('asyncio.sleep', counting_sleep):
            await limiter.acquire()
            
            # Should sleep exactly once (or twice with retry pattern)
            assert sleep_count <= 2, f"Should not busy-wait, but slept {sleep_count} times"


class TestRateLimiterPerformance:
    """Test performance characteristics of rate limiter."""
    
    @pytest.mark.asyncio
    async def test_wakeups_per_acquire(self):
        """Test that each acquire causes at most one wakeup."""
        limiter = RateLimiter(max_messages_per_second=10, burst_size=1)
        
        # Track sleep calls
        sleep_calls = []
        original_sleep = asyncio.sleep
        
        async def tracking_sleep(duration):
            sleep_calls.append(duration)
            await original_sleep(duration)
        
        with patch('asyncio.sleep', tracking_sleep):
            # Exhaust burst
            await limiter.acquire()
            sleep_calls.clear()
            
            # Next 5 acquires
            for _ in range(5):
                await limiter.acquire()
            
            # Should have exactly 5 sleep calls (one per acquire)
            assert len(sleep_calls) == 5, \
                f"Should have one sleep per acquire, got {len(sleep_calls)} sleeps"
            
            # Each sleep should be ~100ms
            for duration in sleep_calls:
                assert 0.09 < duration < 0.11, \
                    f"Sleep duration should be ~100ms, got {duration*1000:.1f}ms"
    
    @pytest.mark.asyncio
    async def test_exact_timing_calculation(self):
        """Test that wait time is calculated exactly, not approximated."""
        limiter = RateLimiter(max_messages_per_second=7, burst_size=1)  # Odd rate
        
        # Exhaust burst
        await limiter.acquire()
        
        start = time.perf_counter()
        await limiter.acquire()
        elapsed = time.perf_counter() - start
        
        expected = 1.0 / 7  # ~142.857ms
        assert abs(elapsed - expected) < 0.01, \
            f"Should wait exactly {expected*1000:.1f}ms, got {elapsed*1000:.1f}ms"
    
    @pytest.mark.asyncio
    async def test_no_polling_overhead(self):
        """Test that rate limiter has zero overhead when not rate limited."""
        limiter = RateLimiter(max_messages_per_second=1000, burst_size=100)
        
        # Many acquires within burst capacity
        start = time.perf_counter()
        for _ in range(50):
            await limiter.acquire()
        elapsed = time.perf_counter() - start
        
        # Should complete very quickly (no waiting)
        assert elapsed < 0.01, f"Burst acquires should have minimal overhead, took {elapsed*1000:.1f}ms"


class TestRateLimiterEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_zero_rate_handling(self):
        """Test behavior with zero or very low rate."""
        # This should either raise an error or handle gracefully
        with pytest.raises((ValueError, ZeroDivisionError)):
            limiter = RateLimiter(max_messages_per_second=0, burst_size=1)
    
    @pytest.mark.asyncio
    async def test_high_rate(self):
        """Test with very high rate limit."""
        limiter = RateLimiter(max_messages_per_second=10000, burst_size=1)
        
        # Should handle high rate without issues
        start = time.perf_counter()
        for _ in range(10):
            await limiter.acquire()
        elapsed = time.perf_counter() - start
        
        # With 10k/sec rate, 10 acquires should take ~1ms
        assert elapsed < 0.01, f"High rate acquires too slow: {elapsed*1000:.1f}ms"
    
    @pytest.mark.asyncio
    async def test_shutdown_cleanup(self):
        """Test that pending acquires are cleaned up on shutdown."""
        limiter = RateLimiter(max_messages_per_second=1, burst_size=1)
        
        # Exhaust burst
        await limiter.acquire()
        
        # Start acquire that will wait
        acquire_task = asyncio.create_task(limiter.acquire())
        
        # Give it time to start waiting
        await asyncio.sleep(0.01)
        
        # Cancel the task (simulating shutdown)
        acquire_task.cancel()
        
        try:
            await acquire_task
        except asyncio.CancelledError:
            pass  # Expected
        
        # Should be able to acquire again
        await asyncio.sleep(1.1)  # Wait for token
        await limiter.acquire()  # Should work
    
    @pytest.mark.asyncio
    async def test_time_drift_handling(self):
        """Test that rate limiter handles system time adjustments."""
        limiter = RateLimiter(max_messages_per_second=10, burst_size=2)
        
        # Normal acquires
        await limiter.acquire()
        await limiter.acquire()
        
        # Simulate time going backwards (should not break)
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.time.return_value = 0  # Time goes back
            
            # Should handle gracefully (might wait or succeed)
            try:
                result = limiter.try_acquire()
                # Should return False since tokens exhausted
                assert result is False
            except Exception as e:
                pytest.fail(f"Should handle time drift gracefully, got: {e}")


class TestRateLimiterMetrics:
    """Test metrics collection for monitoring."""
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self):
        """Test that rate limiter can collect performance metrics."""
        # This test assumes we'll add metrics to the implementation
        limiter = RateLimiter(max_messages_per_second=10, burst_size=2)
        
        # If metrics are implemented, test them
        if hasattr(limiter, 'metrics'):
            # Reset metrics
            limiter.metrics = {
                'acquires': 0,
                'waits': 0,
                'total_wait_time': 0,
            }
            
            # Do some operations
            await limiter.acquire()  # Burst
            await limiter.acquire()  # Burst
            await limiter.acquire()  # Wait
            
            assert limiter.metrics['acquires'] == 3
            assert limiter.metrics['waits'] == 1
            assert limiter.metrics['total_wait_time'] > 0
    
    @pytest.mark.asyncio
    async def test_wakeup_efficiency_metric(self):
        """Test metric for wakeups per acquire (should be ≤1)."""
        limiter = RateLimiter(max_messages_per_second=10, burst_size=1)
        
        # Track wakeups
        wakeup_count = 0
        original_sleep = asyncio.sleep
        
        async def counting_sleep(duration):
            nonlocal wakeup_count
            wakeup_count += 1
            await original_sleep(duration)  # Call original, not patched
        
        # Exhaust burst
        await limiter.acquire()
        
        with patch.object(asyncio, 'sleep', counting_sleep):
            acquires = 10
            for _ in range(acquires):
                await limiter.acquire()
            
            efficiency = wakeup_count / acquires
            assert efficiency <= 1.0, f"Wakeup efficiency should be ≤1, got {efficiency:.2f}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])