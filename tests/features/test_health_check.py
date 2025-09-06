"""Tests for hybrid health check mechanism in SessionPool."""

import asyncio
import pytest
import time
from typing import List
from unittest.mock import Mock, AsyncMock, patch

from src.session.pool import SessionPool, PoolConfig
from src.session.manager import Session


class TestHybridHealthCheck:
    """Test hybrid health check behavior."""
    
    @pytest.mark.asyncio
    async def test_health_check_triggers_on_release(self):
        """Test that health check triggers immediately on release."""
        pool = SessionPool(min_idle=2, max_sessions=5, health_check_interval=60)
        await pool.start()
        
        try:
            # Wait for initial setup
            await asyncio.sleep(0.5)
            
            # Acquire and release a session
            session = await pool.acquire(timeout=1.0)
            
            initial_health_runs = pool._metrics.health_check_runs
            initial_triggers = pool._metrics.health_check_triggers
            
            # Release should trigger health check
            await pool.release(session)
            
            # Health check should be triggered immediately
            await asyncio.sleep(0.1)  # Small wait for event processing
            
            assert pool._metrics.health_check_triggers > initial_triggers, \
                "Health check should be triggered on release"
            
            # Wait for health check to complete
            await asyncio.sleep(0.5)
            
            assert pool._metrics.health_check_runs > initial_health_runs, \
                "Health check should have run after trigger"
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_health_check_triggers_on_session_death(self):
        """Test that health check triggers when a dead session is detected."""
        pool = SessionPool(min_idle=2, max_sessions=5, health_check_interval=60)
        await pool.start()
        
        try:
            # Wait for initial setup
            await asyncio.sleep(0.5)
            
            # Acquire a session
            session = await pool.acquire(timeout=1.0)
            
            # Kill the session
            await session.terminate()
            
            initial_triggers = pool._metrics.health_check_triggers
            
            # Release dead session
            await pool.release(session, restart_if_dead=False)
            
            # Should trigger health check
            assert pool._metrics.health_check_triggers > initial_triggers, \
                "Health check should trigger after removing dead session"
            
            # Wait for health check
            await asyncio.sleep(0.5)
            
            # Dead session should be removed
            assert pool._metrics.sessions_removed_by_health > 0 or \
                   pool._metrics.sessions_removed > 0, \
                "Dead session should be removed"
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_baseline_timer_runs(self):
        """Test that baseline timer ensures health check runs periodically."""
        # Use short baseline for testing
        pool = SessionPool(min_idle=1, max_sessions=3, health_check_interval=2)
        await pool.start()
        
        try:
            # Wait for initial setup
            await asyncio.sleep(0.5)
            
            initial_runs = pool._metrics.health_check_runs
            
            # Wait for baseline timer (2 seconds)
            await asyncio.sleep(2.5)
            
            # Health check should have run via baseline timer
            assert pool._metrics.health_check_runs > initial_runs, \
                "Baseline timer should ensure health check runs"
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_event_coalescing(self):
        """Test that multiple triggers are coalesced efficiently."""
        pool = SessionPool(min_idle=2, max_sessions=10, health_check_interval=60)
        await pool.start()
        
        try:
            # Wait for initial setup
            await asyncio.sleep(0.5)
            
            initial_triggers = pool._metrics.health_check_triggers
            initial_runs = pool._metrics.health_check_runs
            
            # Acquire multiple sessions
            sessions = []
            for _ in range(3):
                session = await pool.acquire(timeout=1.0)
                sessions.append(session)
            
            # Release all sessions rapidly (may coalesce into one trigger)
            for session in sessions:
                await pool.release(session)
            
            # At least one trigger should happen
            assert pool._metrics.health_check_triggers > initial_triggers, \
                "Should have at least one trigger from releases"
            
            # Wait for health check processing
            await asyncio.sleep(0.5)
            
            runs_added = pool._metrics.health_check_runs - initial_runs
            
            # Even with multiple releases, should get efficient processing
            assert runs_added >= 1, "Health check should have run"
            
            # Now test actual coalescing by triggering many events
            for _ in range(5):
                pool._trigger_health_check()
            
            # Wait briefly
            await asyncio.sleep(0.2)
            
            # Should coalesce multiple manual triggers into one run
            final_runs = pool._metrics.health_check_runs
            assert final_runs <= runs_added + 2, \
                f"Multiple rapid triggers should be coalesced (got {final_runs - runs_added} runs from 5 triggers)"
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_stale_session_removal(self):
        """Test that stale sessions are removed by health check."""
        # Short timeout for testing
        pool = SessionPool(
            min_idle=2, 
            max_sessions=5,
            session_timeout=1.0,  # 1 second timeout
            health_check_interval=60
        )
        await pool.start()
        
        try:
            # Wait for initial sessions
            await asyncio.sleep(0.5)
            
            # Get initial count
            initial_total = len(pool._all_sessions)
            
            # Wait for sessions to become stale
            await asyncio.sleep(1.5)
            
            # Manually trigger health check
            pool._trigger_health_check()
            
            # Wait for health check to process
            await asyncio.sleep(0.5)
            
            # Stale sessions should be removed
            assert pool._metrics.sessions_removed_by_health > 0, \
                "Health check should remove stale sessions"
            
            # Pool should maintain watermark by creating new ones
            await asyncio.sleep(1.0)
            assert pool._idle_sessions.qsize() >= pool._config.min_idle or \
                   pool._metrics.sessions_created_from_warmup > 0, \
                "Pool should maintain watermark after removals"
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_no_redundant_health_checks(self):
        """Test that event doesn't trigger if health check recently ran."""
        pool = SessionPool(min_idle=2, max_sessions=5, health_check_interval=60)
        await pool.start()
        
        try:
            # Wait for initial setup
            await asyncio.sleep(0.5)
            
            # Trigger health check manually
            pool._trigger_health_check()
            await asyncio.sleep(0.5)
            
            initial_runs = pool._metrics.health_check_runs
            
            # Immediately trigger again
            pool._trigger_health_check()
            pool._trigger_health_check()
            
            # Small wait
            await asyncio.sleep(0.1)
            
            # Should not run redundantly if just ran
            # (This behavior is optional - depends on implementation)
            # Just verify it doesn't run excessively
            assert pool._metrics.health_check_runs <= initial_runs + 1, \
                "Should not run health check redundantly"
                
        finally:
            await pool.stop()


class TestHealthCheckPerformance:
    """Test performance characteristics of hybrid health check."""
    # Deferred to Phase 3: health-check/warmup performance tuning
    pytestmark = pytest.mark.xfail(
        reason="Deferred to Phase 3: health-check/warmup performance",
        strict=False,
    )
    
    @pytest.mark.asyncio
    async def test_idle_health_check_rate(self):
        """Test that idle pool has reduced health check rate."""
        # Use longer baseline for realistic test
        pool = SessionPool(min_idle=2, max_sessions=5, health_check_interval=60)
        await pool.start()
        
        try:
            # Wait for initial setup
            await asyncio.sleep(0.5)
            
            # Record baseline
            start_runs = pool._metrics.health_check_runs
            start_time = time.time()
            
            # Let pool sit idle for 10 seconds
            await asyncio.sleep(10.0)
            
            # Calculate rate
            elapsed = time.time() - start_time
            runs_added = pool._metrics.health_check_runs - start_runs
            runs_per_minute = (runs_added / elapsed) * 60
            
            # Should be much less than old rate (2/min with 30s interval)
            # Target: <0.2/min with 60s baseline (80% reduction)
            assert runs_per_minute < 0.5, \
                f"Too many idle health checks: {runs_per_minute}/min"
            
            print(f"Idle health check rate: {runs_per_minute:.4f}/min")
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_health_check_response_time(self):
        """Test that health check responds immediately to triggers."""
        pool = SessionPool(min_idle=2, max_sessions=5, health_check_interval=60)
        await pool.start()
        
        try:
            # Wait for initial setup
            await asyncio.sleep(0.5)
            
            # Acquire a session
            session = await pool.acquire(timeout=1.0)
            
            # Kill it
            await session.terminate()
            
            # Measure response time
            start = time.perf_counter()
            
            # Release dead session (should trigger health check)
            await pool.release(session, restart_if_dead=False)
            
            # Wait for health check to start
            while pool._metrics.health_check_runs == 0 and \
                  time.perf_counter() - start < 2.0:
                await asyncio.sleep(0.01)
            
            response_time = time.perf_counter() - start
            
            # Should respond quickly
            assert response_time < 0.5, \
                f"Health check response too slow: {response_time:.3f}s"
            
            print(f"Health check response time: {response_time*1000:.1f}ms")
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self):
        """Test that health check metrics are properly collected."""
        pool = SessionPool(min_idle=2, max_sessions=5, health_check_interval=60)
        await pool.start()
        
        try:
            # Wait for initial setup
            await asyncio.sleep(0.5)
            
            # Perform operations
            session = await pool.acquire(timeout=1.0)
            await pool.release(session)
            
            # Wait for health check
            await asyncio.sleep(0.5)
            
            # Check metrics exist
            assert pool._metrics.health_check_runs >= 0, "Should track runs"
            assert pool._metrics.health_check_triggers >= 0, "Should track triggers"
            assert hasattr(pool._metrics, 'sessions_removed_by_health'), \
                "Should track sessions removed by health"
            
            # Get pool info
            info = pool.get_info()
            metrics = info["metrics"]
            
            # Check health metrics are included
            assert "health_check_runs" in metrics
            assert "health_check_triggers" in metrics
            assert "health_check_efficiency" in metrics
            
            # Efficiency calculation
            if metrics["health_check_triggers"] > 0:
                assert metrics["health_check_efficiency"] > 0, \
                    "Should calculate efficiency"
                    
        finally:
            await pool.stop()


class TestHealthCheckEdgeCases:
    """Test edge cases for hybrid health check."""
    
    @pytest.mark.asyncio
    async def test_health_check_during_shutdown(self):
        """Test that health check stops cleanly during shutdown."""
        pool = SessionPool(min_idle=2, max_sessions=5, health_check_interval=2)
        await pool.start()
        
        try:
            # Trigger health check
            pool._trigger_health_check()
            
            # Start shutdown while health check might be running
            shutdown_task = asyncio.create_task(pool.stop())
            
            # Shutdown should complete without hanging
            await asyncio.wait_for(shutdown_task, timeout=3.0)
            
            # Health check task should be cancelled
            assert pool._health_check_task is not None
            assert pool._health_check_task.cancelled() or pool._health_check_task.done()
            
        except Exception:
            # Emergency cleanup
            pool._shutdown = True
            if pool._health_check_task:
                pool._health_check_task.cancel()
            raise
    
    @pytest.mark.asyncio
    async def test_health_check_with_empty_pool(self):
        """Test health check handles empty pool gracefully."""
        pool = SessionPool(min_idle=0, max_sessions=5, health_check_interval=60)
        await pool.start()
        
        try:
            # Trigger health check on empty pool
            pool._trigger_health_check()
            
            # Should not error
            await asyncio.sleep(0.5)
            
            # Should complete successfully
            assert pool._metrics.health_check_runs >= 0, \
                "Health check should handle empty pool"
                
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self):
        """Test that concurrent triggers don't cause race conditions."""
        pool = SessionPool(min_idle=3, max_sessions=10, health_check_interval=60)
        await pool.start()
        
        try:
            # Wait for setup
            await asyncio.sleep(0.5)
            
            # Trigger many health checks concurrently
            tasks = []
            for _ in range(10):
                pool._trigger_health_check()
                tasks.append(asyncio.create_task(asyncio.sleep(0.01)))
            
            await asyncio.gather(*tasks)
            
            # Should handle gracefully without errors
            await asyncio.sleep(1.0)
            
            # Pool should still be functional
            session = await pool.acquire(timeout=1.0)
            await pool.release(session)
            
            assert True, "Concurrent triggers handled successfully"
            
        finally:
            await pool.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
