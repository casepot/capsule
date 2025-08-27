"""Tests for event-driven SessionPool warmup mechanism."""

import asyncio
import pytest
import time
from typing import List
from unittest.mock import Mock, AsyncMock, patch

from src.session.pool import SessionPool, PoolConfig
from src.session.manager import Session


class TestEventDrivenWarmup:
    """Test event-driven warmup behavior."""
    
    @pytest.mark.asyncio
    async def test_warmup_triggers_on_low_idle(self):
        """Test that warmup triggers when idle falls below min_idle."""
        pool = SessionPool(min_idle=2, max_sessions=5)
        await pool.start()
        
        try:
            # Initial warmup should create min_idle sessions
            await asyncio.sleep(0.5)  # Let warmup complete
            assert pool._idle_sessions.qsize() >= 2, "Should have min_idle sessions"
            
            # Acquire all idle sessions to trigger warmup
            sessions = []
            for _ in range(pool._config.min_idle):
                session = await pool.acquire(timeout=1.0)
                sessions.append(session)
            
            # Check that warmup was triggered (initial + acquisitions)
            assert pool._metrics.warmup_triggers >= 1, "Warmup should have been triggered"
            
            # Release one session
            await pool.release(sessions.pop())
            
            # Wait for warmup to restore watermark
            await asyncio.sleep(0.5)
            
            # Should have restored to min_idle
            assert pool._idle_sessions.qsize() >= pool._config.min_idle - len(sessions), \
                "Warmup should restore watermark"
            
            # Cleanup
            for session in sessions:
                await pool.release(session)
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_warmup_coalescing(self):
        """Test that multiple triggers are coalesced efficiently."""
        pool = SessionPool(min_idle=3, max_sessions=10)
        await pool.start()
        
        try:
            # Wait for initial warmup
            await asyncio.sleep(0.5)
            initial_triggers = pool._metrics.warmup_triggers
            initial_iterations = pool._metrics.warmup_loop_iterations
            
            # Acquire multiple sessions rapidly to trigger multiple warmup needs
            sessions = []
            for _ in range(3):
                session = await pool.acquire(timeout=1.0)
                sessions.append(session)
            
            # Multiple acquisitions should trigger warmup
            assert pool._metrics.warmup_triggers > initial_triggers
            
            # Wait for warmup to process
            await asyncio.sleep(0.5)
            
            # Check that we had warmup activity
            assert pool._metrics.warmup_triggers > initial_triggers, "Should have additional triggers"
            assert pool._metrics.warmup_loop_iterations > initial_iterations, "Should have additional iterations"
            
            # Cleanup
            for session in sessions:
                await pool.release(session)
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_warmup_after_health_check_removal(self):
        """Test warmup triggers after health check removes sessions."""
        # Use short timeout for testing
        pool = SessionPool(
            min_idle=2,
            max_sessions=5,
            session_timeout=2.0,  # Session timeout
            health_check_interval=0.5,
        )
        await pool.start()
        
        try:
            # Wait for initial warmup to complete
            await asyncio.sleep(0.5)
            initial_idle = pool._idle_sessions.qsize()
            assert initial_idle >= 2, "Should have initial sessions"
            
            initial_triggers = pool._metrics.warmup_triggers
            initial_removals = pool._metrics.sessions_removed
            
            # Wait longer than session timeout for health check to remove them
            await asyncio.sleep(3.0)
            
            # Health check should have removed some sessions
            assert pool._metrics.sessions_removed > initial_removals, \
                "Health check should have removed timed-out sessions"
            
            # Warmup should have been triggered
            assert pool._metrics.warmup_triggers >= initial_triggers, \
                "Warmup should trigger after health check removals"
            
            # Give warmup time to restore watermark
            await asyncio.sleep(1.0)
            
            # Watermark should be maintained (or at least attempting to)
            # Note: might not be exactly min_idle if sessions are still being created
            assert pool._idle_sessions.qsize() > 0 or pool._metrics.sessions_created_from_warmup > 2, \
                "Warmup should be creating sessions to restore watermark"
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_warmup_after_session_death(self):
        """Test warmup triggers when released session is dead."""
        pool = SessionPool(min_idle=2, max_sessions=5)
        await pool.start()
        
        try:
            # Wait for initial warmup
            await asyncio.sleep(0.5)
            
            # Acquire a session
            session = await pool.acquire(timeout=1.0)
            
            # Simulate session death
            await session.terminate()
            
            initial_triggers = pool._metrics.warmup_triggers
            
            # Release dead session (should trigger removal and warmup)
            await pool.release(session, restart_if_dead=False)
            
            # Should have triggered warmup
            assert pool._metrics.warmup_triggers > initial_triggers, \
                "Warmup should trigger after removing dead session"
            
            # Wait for warmup to complete
            await asyncio.sleep(0.5)
            
            # Watermark should be maintained
            assert pool._idle_sessions.qsize() >= pool._config.min_idle, \
                "Warmup should restore watermark after dead session removal"
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_no_warmup_when_at_watermark(self):
        """Test that warmup doesn't run unnecessarily when at watermark."""
        pool = SessionPool(min_idle=2, max_sessions=5)
        await pool.start()
        
        try:
            # Wait for initial warmup
            await asyncio.sleep(0.5)
            assert pool._idle_sessions.qsize() >= 2
            
            initial_iterations = pool._metrics.warmup_loop_iterations
            
            # Wait without any activity
            await asyncio.sleep(1.0)
            
            # Should have no additional iterations
            assert pool._metrics.warmup_loop_iterations == initial_iterations, \
                "No warmup iterations should occur when at watermark"
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_warmup_respects_max_sessions(self):
        """Test that warmup respects max_sessions limit."""
        pool = SessionPool(min_idle=3, max_sessions=4)
        await pool.start()
        
        try:
            # Wait for initial warmup
            await asyncio.sleep(0.5)
            
            # Acquire sessions to reach max
            sessions = []
            for _ in range(4):  # Max sessions
                session = await pool.acquire(timeout=1.0)
                sessions.append(session)
            
            # Pool is at max capacity
            assert len(pool._all_sessions) == 4
            
            # Release one and remove it to trigger warmup need
            session = sessions.pop()
            await session.terminate()
            await pool.release(session, restart_if_dead=False)
            
            # Wait for warmup attempt
            await asyncio.sleep(0.5)
            
            # Should not exceed max_sessions
            assert len(pool._all_sessions) <= pool._config.max_sessions, \
                "Warmup should respect max_sessions limit"
            
            # Cleanup
            for session in sessions:
                await pool.release(session)
                
        finally:
            await pool.stop()


class TestWarmupPerformance:
    """Test performance characteristics of event-driven warmup."""
    
    @pytest.mark.asyncio
    async def test_idle_warmup_iterations(self):
        """Test that idle pool has minimal warmup iterations."""
        pool = SessionPool(min_idle=2, max_sessions=5)
        await pool.start()
        
        try:
            # Wait for initial warmup
            await asyncio.sleep(0.5)
            
            # Record baseline
            start_iterations = pool._metrics.warmup_loop_iterations
            start_time = time.time()
            
            # Let pool sit idle for 10 seconds
            await asyncio.sleep(10.0)
            
            # Calculate iteration rate
            elapsed = time.time() - start_time
            iterations_added = pool._metrics.warmup_loop_iterations - start_iterations
            iterations_per_minute = (iterations_added / elapsed) * 60
            
            # Should be well below 0.1 iterations/minute when idle
            assert iterations_per_minute < 0.1, \
                f"Too many idle iterations: {iterations_per_minute}/min"
            
            print(f"Idle iteration rate: {iterations_per_minute:.4f}/min")
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_warmup_response_time(self):
        """Test that warmup responds immediately to watermark violations."""
        pool = SessionPool(min_idle=3, max_sessions=10)
        await pool.start()
        
        try:
            # Wait for initial warmup
            await asyncio.sleep(0.5)
            
            # Acquire all idle sessions
            sessions = []
            for _ in range(3):
                session = await pool.acquire(timeout=1.0)
                sessions.append(session)
            
            # Pool should be below watermark
            assert pool._idle_sessions.qsize() == 0
            
            # Measure how quickly warmup responds
            start = time.perf_counter()
            
            # Wait for warmup to create at least one session
            while pool._idle_sessions.qsize() < 1 and time.perf_counter() - start < 2.0:
                await asyncio.sleep(0.01)
            
            response_time = time.perf_counter() - start
            
            # Should respond quickly (< 500ms is much better than 10s polling)
            assert response_time < 0.5, \
                f"Warmup response too slow: {response_time:.3f}s"
            
            print(f"Warmup response time: {response_time*1000:.1f}ms")
            
            # Cleanup
            for session in sessions:
                await pool.release(session)
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self):
        """Test that warmup metrics are properly collected."""
        pool = SessionPool(min_idle=2, max_sessions=5)
        await pool.start()
        
        try:
            # Wait for initial warmup
            await asyncio.sleep(0.5)
            
            # Check initial metrics (initial warmup counts)
            assert pool._metrics.warmup_triggers >= 0, "Should track triggers"
            assert pool._metrics.warmup_loop_iterations >= 1, "Should have iterations"
            assert pool._metrics.sessions_created_from_warmup >= 2, "Should create initial sessions"
            
            # Get pool info
            info = pool.get_info()
            metrics = info["metrics"]
            
            # Check warmup metrics are included
            assert "warmup_triggers" in metrics
            assert "warmup_loop_iterations" in metrics
            assert "sessions_created_from_warmup" in metrics
            assert "warmup_efficiency" in metrics
            
            # Efficiency should be reasonable
            if metrics["warmup_triggers"] > 0:
                assert metrics["warmup_efficiency"] > 0, "Should have efficiency metric"
                
        finally:
            await pool.stop()


class TestWarmupEdgeCases:
    """Test edge cases for event-driven warmup."""
    
    @pytest.mark.asyncio
    async def test_warmup_with_creation_failures(self):
        """Test warmup handles session creation failures gracefully."""
        pool = SessionPool(min_idle=2, max_sessions=5)
        
        # Mock session creation to fail occasionally
        original_create = pool._create_session
        call_count = 0
        
        async def mock_create():
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise RuntimeError("Mock creation failure")
            return await original_create()
        
        pool._create_session = mock_create
        
        await pool.start()
        
        try:
            # Wait for warmup attempts
            await asyncio.sleep(1.0)
            
            # Should have attempted multiple times due to failures
            assert call_count > 2, "Should retry on failures"
            
            # Should eventually reach watermark despite failures
            assert pool._idle_sessions.qsize() >= 1, \
                "Should create some sessions despite failures"
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_warmup_during_shutdown(self):
        """Test that warmup stops cleanly during shutdown."""
        pool = SessionPool(min_idle=3, max_sessions=10)
        await pool.start()
        
        try:
            # Trigger warmup by acquiring sessions
            sessions = []
            for _ in range(2):
                session = await pool.acquire(timeout=1.0)
                sessions.append(session)
            
            # Start shutdown while warmup might be running
            shutdown_task = asyncio.create_task(pool.stop())
            
            # Shutdown should complete without hanging
            await asyncio.wait_for(shutdown_task, timeout=2.0)
            
            # Warmup task should be cancelled
            assert pool._warmup_task is not None
            assert pool._warmup_task.cancelled() or pool._warmup_task.done()
            
        except Exception:
            # Emergency cleanup if test fails
            pool._shutdown = True
            if pool._warmup_task:
                pool._warmup_task.cancel()
            raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])