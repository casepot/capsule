# Security Model Specification

## Document Information
- **Version**: 1.0.0
- **Status**: Draft
- **Last Updated**: 2025-01-03
- **Classification**: Security Specification

## Executive Summary

This specification defines the comprehensive security model for PyREPL3, implementing defense-in-depth through capability-based access control, runtime validation, and audit mechanisms. The fundamental principle is that **security is enforced at capability injection time**, not through code analysis or preprocessing, as string-level security measures are easily bypassed.

## Security Philosophy

### Core Principles

1. **Capability-Based Security**: If a capability isn't injected, it cannot be used
2. **Injection-Time Enforcement**: Security decisions made when capabilities are injected
3. **No Code Preprocessing**: String-level security is ineffective and easily bypassed
4. **Defense in Depth**: Multiple layers of security controls
5. **Principle of Least Privilege**: Grant minimal required capabilities
6. **Audit Everything**: Comprehensive logging for security analysis

### Why Traditional Approaches Fail

```python
# Traditional Approach (INEFFECTIVE)
def preprocess_code(code):
    # Try to detect dangerous operations
    if 'eval' in code or 'exec' in code:
        raise SecurityError("Dangerous code detected")
    return code

# EASILY BYPASSED:
code = "e" + "v" + "a" + "l('malicious')"  # Bypasses string check
code = "__builtins__['eval']('malicious')" # Bypasses string check
code = "getattr(__builtins__, 'ev' + 'al')('malicious')" # Bypasses
```

### Capability-Based Approach (EFFECTIVE)

```python
# Our Approach: Don't inject dangerous capabilities
namespace = {}
# eval, exec, __import__ are simply not available
# No amount of string manipulation can create them
```

## Security Architecture

### Security Layers

```
┌─────────────────────────────────────────────────┐
│           Security Policy Layer                 │
│         (Defines what's allowed)                │
├─────────────────────────────────────────────────┤
│        Capability Injection Layer               │
│      (Enforces policy at injection)             │
├─────────────────────────────────────────────────┤
│         Runtime Validation Layer                │
│    (Validates capability invocations)           │
├─────────────────────────────────────────────────┤
│           Audit & Monitoring Layer              │
│      (Logs all security events)                 │
├─────────────────────────────────────────────────┤
│          Resource Limits Layer                  │
│    (Prevents resource exhaustion)               │
└─────────────────────────────────────────────────┘
```

## Security Levels

### Level Definitions

```python
class SecurityLevel(Enum):
    """Pre-defined security levels with increasing privileges."""
    
    SANDBOX = "sandbox"           # Minimal - output only
    RESTRICTED = "restricted"      # Local I/O, no network
    STANDARD = "standard"         # Network read, local I/O
    TRUSTED = "trusted"          # Most capabilities, HITL
    UNRESTRICTED = "unrestricted"  # All capabilities
```

### Level Capabilities Matrix

| Level | Input | Output | File Read | File Write | Network | Database | System |
|-------|-------|--------|-----------|------------|---------|----------|--------|
| SANDBOX | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| RESTRICTED | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| STANDARD | ✅ | ✅ | ✅ | ✅ | ✅ (read) | ❌ | ❌ |
| TRUSTED | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| UNRESTRICTED | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### Detailed Capability Sets

```python
CAPABILITY_SETS = {
    SecurityLevel.SANDBOX: {
        'print',      # Basic output
        'display',    # Rich display output
        'log',        # Logging output
    },
    
    SecurityLevel.RESTRICTED: {
        'print', 'display', 'log',
        'input',      # User input
        'read_file',  # File reading only
        'list_files', # Directory listing
        'time',       # Time functions
        'random',     # Random generation
    },
    
    SecurityLevel.STANDARD: {
        'print', 'display', 'log', 'input',
        'read_file', 'write_file', 'list_files',
        'fetch',      # HTTP GET only
        'dns',        # DNS lookups
        'query',      # Read-only database queries
        'time', 'random',
        'hash',       # Cryptographic hashing
    },
    
    SecurityLevel.TRUSTED: {
        'print', 'display', 'log', 'input',
        'read_file', 'write_file', 'list_files', 'delete_file',
        'fetch', 'websocket', 'http_server',
        'dns', 'smtp',
        'query', 'execute', 'transaction',
        'approve', 'review',  # HITL workflows
        'time', 'random', 'hash', 'encrypt',
        'env',        # Environment variables (read)
    },
    
    SecurityLevel.UNRESTRICTED: '*'  # All capabilities
}
```

## Capability Security

### Capability Validation

```python
class CapabilityValidator:
    """Runtime validation for capability invocations."""
    
    def __init__(self, policy: SecurityPolicy):
        self.policy = policy
        self.validators = {}
        self._register_validators()
    
    def _register_validators(self):
        """Register validators for each capability."""
        
        # File operations
        self.validators['read_file'] = self._validate_file_read
        self.validators['write_file'] = self._validate_file_write
        
        # Network operations
        self.validators['fetch'] = self._validate_fetch
        self.validators['websocket'] = self._validate_websocket
        
        # Database operations
        self.validators['query'] = self._validate_query
        self.validators['execute'] = self._validate_execute
    
    def _validate_file_read(self, path: str) -> bool:
        """Validate file read operation."""
        # Prevent directory traversal
        if '..' in path or path.startswith('/'):
            return False
        
        # Check against allowed paths
        allowed_paths = self.policy.get_allowed_paths()
        if allowed_paths and not any(
            path.startswith(p) for p in allowed_paths
        ):
            return False
        
        # Check file extensions
        blocked_extensions = {'.key', '.pem', '.env', '.secret'}
        if any(path.endswith(ext) for ext in blocked_extensions):
            return False
        
        return True
    
    def _validate_file_write(self, path: str, content: str) -> bool:
        """Validate file write operation."""
        # All file read validations apply
        if not self._validate_file_read(path):
            return False
        
        # Check content size
        max_size = self.policy.get_max_file_size()
        if len(content) > max_size:
            return False
        
        # Prevent overwriting critical files
        protected_files = {'.gitignore', '.env', 'config.json'}
        if any(path.endswith(f) for f in protected_files):
            return False
        
        return True
    
    def _validate_fetch(self, url: str, method: str = 'GET') -> bool:
        """Validate network fetch operation."""
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        
        # Check protocol
        if parsed.scheme not in ['http', 'https']:
            return False
        
        # Check against allowed domains
        allowed_domains = self.policy.get_allowed_domains()
        if allowed_domains and parsed.netloc not in allowed_domains:
            return False
        
        # Check against blocked domains
        blocked_domains = self.policy.get_blocked_domains()
        if blocked_domains and parsed.netloc in blocked_domains:
            return False
        
        # Check method restrictions
        if self.policy.level == SecurityLevel.STANDARD:
            # Standard level only allows GET
            if method.upper() != 'GET':
                return False
        
        # Prevent local network access unless explicitly allowed
        if self._is_local_address(parsed.netloc):
            if not self.policy.allow_local_network:
                return False
        
        return True
    
    def _is_local_address(self, hostname: str) -> bool:
        """Check if hostname refers to local network."""
        import ipaddress
        
        local_patterns = [
            'localhost',
            '127.0.0.1',
            '::1',
            '0.0.0.0',
            'host.docker.internal'
        ]
        
        if hostname in local_patterns:
            return True
        
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private or ip.is_loopback
        except ValueError:
            # Not an IP address
            return hostname.endswith('.local')
    
    def _validate_query(self, sql: str) -> bool:
        """Validate database query."""
        sql_upper = sql.strip().upper()
        
        # Check for read-only queries at standard level
        if self.policy.level <= SecurityLevel.STANDARD:
            if not sql_upper.startswith('SELECT'):
                return False
        
        # Prevent dangerous operations
        dangerous_keywords = [
            'DROP', 'TRUNCATE', 'DELETE FROM',
            'INSERT INTO', 'UPDATE', 'ALTER',
            'CREATE', 'GRANT', 'REVOKE'
        ]
        
        if self.policy.level < SecurityLevel.TRUSTED:
            for keyword in dangerous_keywords:
                if keyword in sql_upper:
                    return False
        
        return True
```

### Input Sanitization

```python
class InputSanitizer:
    """Sanitize inputs for security."""
    
    @staticmethod
    def sanitize_path(path: str) -> str:
        """Sanitize file system path."""
        import os
        import re
        
        # Remove null bytes
        path = path.replace('\0', '')
        
        # Remove control characters
        path = re.sub(r'[\x00-\x1f\x7f]', '', path)
        
        # Normalize path
        path = os.path.normpath(path)
        
        # Remove leading slashes
        path = path.lstrip('/')
        
        # Prevent directory traversal
        if '..' in path:
            raise ValueError("Directory traversal detected")
        
        return path
    
    @staticmethod
    def sanitize_url(url: str) -> str:
        """Sanitize URL."""
        from urllib.parse import urlparse, urlunparse, quote
        
        # Parse URL
        parsed = urlparse(url)
        
        # Validate scheme
        if parsed.scheme not in ['http', 'https']:
            raise ValueError(f"Invalid URL scheme: {parsed.scheme}")
        
        # Sanitize components
        sanitized = parsed._replace(
            path=quote(parsed.path, safe='/'),
            params=quote(parsed.params, safe=''),
            query=quote(parsed.query, safe='&='),
            fragment=quote(parsed.fragment, safe='')
        )
        
        return urlunparse(sanitized)
    
    @staticmethod
    def sanitize_sql(sql: str, allow_params: bool = True) -> str:
        """Sanitize SQL query."""
        # Remove comments
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        
        # Check for SQL injection patterns
        injection_patterns = [
            r'\bUNION\b.*\bSELECT\b',
            r';\s*DROP\s+',
            r';\s*DELETE\s+FROM',
            r'\bOR\b\s+1\s*=\s*1',
            r'\bOR\b\s+\'\w\'\s*=\s*\'\w\'',
        ]
        
        for pattern in injection_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                raise ValueError("Potential SQL injection detected")
        
        return sql
```

## Resource Limits

### Resource Control Implementation

```python
class ResourceLimiter:
    """Enforce resource limits for security."""
    
    def __init__(self):
        self.limits = {
            'max_execution_time': 30.0,        # seconds
            'max_memory': 512 * 1024 * 1024,   # 512MB
            'max_cpu_percent': 80,              # 80% CPU
            'max_file_size': 10 * 1024 * 1024, # 10MB
            'max_open_files': 100,
            'max_network_connections': 50,
            'max_database_connections': 10,
            'max_coroutines': 1000,
            'max_namespace_size': 100 * 1024 * 1024,  # 100MB
        }
        
        self.usage = {
            'execution_time': 0,
            'memory': 0,
            'open_files': 0,
            'network_connections': 0,
            'database_connections': 0,
            'coroutines': 0,
        }
    
    def check_time_limit(self, start_time: float):
        """Check execution time limit."""
        elapsed = time.time() - start_time
        if elapsed > self.limits['max_execution_time']:
            raise ResourceExhausted("Execution time limit exceeded")
    
    def check_memory_limit(self):
        """Check memory usage limit."""
        import psutil
        
        process = psutil.Process()
        memory_usage = process.memory_info().rss
        
        if memory_usage > self.limits['max_memory']:
            raise ResourceExhausted("Memory limit exceeded")
    
    def check_file_size(self, size: int):
        """Check file size before write."""
        if size > self.limits['max_file_size']:
            raise ResourceExhausted("File size limit exceeded")
    
    def acquire_resource(self, resource_type: str):
        """Acquire a resource slot."""
        if resource_type not in self.usage:
            return
        
        limit_key = f'max_{resource_type}'
        if limit_key not in self.limits:
            return
        
        if self.usage[resource_type] >= self.limits[limit_key]:
            raise ResourceExhausted(f"{resource_type} limit exceeded")
        
        self.usage[resource_type] += 1
    
    def release_resource(self, resource_type: str):
        """Release a resource slot."""
        if resource_type in self.usage:
            self.usage[resource_type] = max(0, self.usage[resource_type] - 1)
    
    @contextmanager
    def limited_resource(self, resource_type: str):
        """Context manager for resource limits."""
        self.acquire_resource(resource_type)
        try:
            yield
        finally:
            self.release_resource(resource_type)
```

### Rate Limiting

```python
class RateLimiter:
    """Rate limiting for capability invocations."""
    
    def __init__(self):
        self.limits = {
            'input': (10, 60),        # 10 per minute
            'fetch': (100, 60),       # 100 per minute
            'query': (50, 60),        # 50 per minute
            'write_file': (20, 60),   # 20 per minute
        }
        
        self.buckets = {}
    
    def check_rate_limit(self, capability: str, identifier: str):
        """Check if rate limit is exceeded."""
        if capability not in self.limits:
            return True
        
        limit, window = self.limits[capability]
        bucket_key = f"{capability}:{identifier}"
        
        now = time.time()
        
        if bucket_key not in self.buckets:
            self.buckets[bucket_key] = []
        
        # Remove old entries
        self.buckets[bucket_key] = [
            t for t in self.buckets[bucket_key]
            if now - t < window
        ]
        
        # Check limit
        if len(self.buckets[bucket_key]) >= limit:
            raise RateLimitExceeded(
                f"Rate limit exceeded for {capability}: "
                f"{limit} per {window} seconds"
            )
        
        # Add current request
        self.buckets[bucket_key].append(now)
```

## Audit System

### Audit Logger

```python
class SecurityAuditLogger:
    """Comprehensive security audit logging."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self.audit_log = []
        self.alerts = []
    
    def log_event(
        self,
        event_type: str,
        execution_id: str,
        details: Dict[str, Any],
        severity: str = "INFO"
    ):
        """Log security event."""
        event = {
            'timestamp': time.time(),
            'event_type': event_type,
            'execution_id': execution_id,
            'severity': severity,
            'details': details
        }
        
        self.audit_log.append(event)
        
        # Persist to Resonate
        self._persist_event(event)
        
        # Check for alerts
        if severity in ['WARNING', 'CRITICAL']:
            self._check_alert(event)
    
    def _persist_event(self, event: Dict):
        """Persist audit event to Resonate."""
        event_id = f"audit:{event['execution_id']}:{uuid.uuid4()}"
        
        self.resonate.promises.create(
            id=event_id,
            data=json.dumps(event),
            tags=['audit', event['event_type'], event['severity']]
        )
        
        # Immediately resolve for storage
        self.resonate.promises.resolve(
            id=event_id,
            data=json.dumps(event)
        )
    
    def _check_alert(self, event: Dict):
        """Check if event requires alert."""
        alert_conditions = [
            ('REPEATED_FAILURES', lambda e: 
                e['event_type'] == 'capability_denied' and 
                self._count_recent_denials(e['execution_id']) > 5),
            
            ('PRIVILEGE_ESCALATION', lambda e:
                e['event_type'] == 'security_level_change' and
                e['details'].get('direction') == 'elevated'),
            
            ('RESOURCE_EXHAUSTION', lambda e:
                e['event_type'] == 'resource_limit' and
                e['severity'] == 'CRITICAL'),
            
            ('SUSPICIOUS_PATTERN', lambda e:
                e['event_type'] == 'validation_failed' and
                'injection' in str(e['details']).lower()),
        ]
        
        for alert_type, condition in alert_conditions:
            if condition(event):
                self._raise_alert(alert_type, event)
    
    def _raise_alert(self, alert_type: str, event: Dict):
        """Raise security alert."""
        alert = {
            'timestamp': time.time(),
            'type': alert_type,
            'event': event,
            'status': 'active'
        }
        
        self.alerts.append(alert)
        
        # Notify security team (implementation specific)
        self._notify_security_team(alert)
```

### Audit Events

```python
class AuditEvents:
    """Standard audit event types."""
    
    # Access Control Events
    CAPABILITY_GRANTED = "capability_granted"
    CAPABILITY_DENIED = "capability_denied"
    CAPABILITY_INVOKED = "capability_invoked"
    
    # Security Policy Events
    POLICY_CREATED = "policy_created"
    POLICY_MODIFIED = "policy_modified"
    SECURITY_LEVEL_CHANGED = "security_level_changed"
    
    # Validation Events
    VALIDATION_SUCCESS = "validation_success"
    VALIDATION_FAILED = "validation_failed"
    SANITIZATION_APPLIED = "sanitization_applied"
    
    # Resource Events
    RESOURCE_LIMIT_WARNING = "resource_limit_warning"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    
    # Execution Events
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_CANCELLED = "execution_cancelled"
    
    # HITL Events
    HITL_REQUEST_CREATED = "hitl_request_created"
    HITL_RESPONSE_RECEIVED = "hitl_response_received"
    HITL_TIMEOUT = "hitl_timeout"
```

## Threat Model

### Threat Categories

#### 1. Code Injection
**Threat**: Malicious code injection through user input
**Mitigation**: 
- No eval/exec in namespace
- Input sanitization
- Capability-based restrictions

#### 2. Resource Exhaustion
**Threat**: DoS through resource consumption
**Mitigation**:
- Execution time limits
- Memory limits
- Rate limiting
- Resource quotas

#### 3. Data Exfiltration
**Threat**: Unauthorized data access/transfer
**Mitigation**:
- File path validation
- Network domain restrictions
- Capability-based access control

#### 4. Privilege Escalation
**Threat**: Gaining unauthorized capabilities
**Mitigation**:
- Injection-time enforcement
- Immutable security policies
- Audit logging

#### 5. Side-Channel Attacks
**Threat**: Information leakage through timing/resources
**Mitigation**:
- Resource normalization
- Constant-time operations where applicable
- Limited error information

### Attack Vectors and Defenses

```python
class ThreatDefense:
    """Implementation of threat defenses."""
    
    def defend_against_injection(self, code: str) -> str:
        """Defend against code injection."""
        # We don't modify code - we simply don't provide
        # dangerous capabilities
        return code
    
    def defend_against_traversal(self, path: str) -> str:
        """Defend against directory traversal."""
        sanitized = InputSanitizer.sanitize_path(path)
        
        # Additional checks
        if sanitized.startswith('/etc/') or \
           sanitized.startswith('/proc/') or \
           sanitized.startswith('/sys/'):
            raise SecurityError("Access to system directories denied")
        
        return sanitized
    
    def defend_against_ssrf(self, url: str) -> str:
        """Defend against SSRF attacks."""
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        
        # Block local addresses
        if self._is_local_address(parsed.netloc):
            raise SecurityError("Access to local network denied")
        
        # Block cloud metadata endpoints
        metadata_endpoints = [
            '169.254.169.254',  # AWS/Azure
            'metadata.google.internal',  # GCP
        ]
        
        if parsed.netloc in metadata_endpoints:
            raise SecurityError("Access to metadata endpoint denied")
        
        return url
```

## Security Configuration

### Security Configuration Schema

```python
@dataclass
class SecurityConfig:
    """Security configuration for PyREPL3."""
    
    # Base security level
    security_level: SecurityLevel = SecurityLevel.STANDARD
    
    # Capability configuration
    custom_allowed_capabilities: Set[str] = field(default_factory=set)
    custom_blocked_capabilities: Set[str] = field(default_factory=set)
    
    # File system restrictions
    allowed_paths: List[str] = field(default_factory=lambda: ['./data'])
    blocked_paths: List[str] = field(default_factory=lambda: ['/etc', '/sys'])
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    
    # Network restrictions
    allowed_domains: Optional[List[str]] = None
    blocked_domains: List[str] = field(default_factory=lambda: [
        'localhost', '127.0.0.1', '0.0.0.0'
    ])
    allow_local_network: bool = False
    
    # Resource limits
    max_execution_time: float = 30.0
    max_memory: int = 512 * 1024 * 1024
    max_cpu_percent: int = 80
    
    # Rate limits (per minute)
    rate_limits: Dict[str, int] = field(default_factory=lambda: {
        'input': 10,
        'fetch': 100,
        'query': 50,
    })
    
    # Audit configuration
    enable_audit: bool = True
    audit_level: str = "INFO"
    alert_on_suspicious: bool = True
    
    # HITL configuration
    hitl_timeout: float = 3600.0  # 1 hour
    require_approval_for: List[str] = field(default_factory=lambda: [
        'delete_file', 'execute', 'system'
    ])
```

## Testing Security

### Security Test Suite

```python
import pytest
from unittest.mock import Mock

class TestSecurityEnforcement:
    """Test security enforcement mechanisms."""
    
    def test_capability_injection_enforcement(self):
        """Test that capabilities are properly enforced."""
        policy = SecurityPolicy(SecurityLevel.SANDBOX)
        namespace = {}
        
        # Only output capabilities should be injected
        registry.inject_capabilities(namespace, "test", policy)
        
        assert 'print' in namespace
        assert 'input' not in namespace
        assert 'fetch' not in namespace
    
    def test_code_injection_prevention(self):
        """Test that code injection is prevented."""
        namespace = create_secure_namespace(SecurityLevel.STANDARD)
        
        # These should not exist
        assert 'eval' not in namespace
        assert 'exec' not in namespace
        assert '__import__' not in namespace
        
        # Try to access them indirectly
        with pytest.raises(NameError):
            exec("eval('1+1')", namespace)
    
    def test_directory_traversal_prevention(self):
        """Test directory traversal prevention."""
        validator = CapabilityValidator(SecurityPolicy())
        
        # These should be rejected
        assert not validator._validate_file_read("../etc/passwd")
        assert not validator._validate_file_read("/etc/passwd")
        assert not validator._validate_file_read("../../sensitive.txt")
    
    def test_rate_limiting(self):
        """Test rate limiting enforcement."""
        limiter = RateLimiter()
        limiter.limits = {'test': (2, 1)}  # 2 per second
        
        # First two should succeed
        limiter.check_rate_limit('test', 'user1')
        limiter.check_rate_limit('test', 'user1')
        
        # Third should fail
        with pytest.raises(RateLimitExceeded):
            limiter.check_rate_limit('test', 'user1')
    
    def test_resource_limits(self):
        """Test resource limit enforcement."""
        limiter = ResourceLimiter()
        limiter.limits['max_open_files'] = 2
        
        # Acquire resources
        limiter.acquire_resource('open_files')
        limiter.acquire_resource('open_files')
        
        # Should hit limit
        with pytest.raises(ResourceExhausted):
            limiter.acquire_resource('open_files')
```

## Security Best Practices

### For Implementers

1. **Never Trust User Input**: Always sanitize and validate
2. **Fail Secure**: Default to denying access
3. **Minimize Attack Surface**: Only inject required capabilities
4. **Defense in Depth**: Use multiple security layers
5. **Audit Everything**: Log all security-relevant events
6. **Regular Security Reviews**: Audit logs and update policies

### For Users

1. **Use Minimum Security Level**: Start with SANDBOX and elevate as needed
2. **Review Capability Requirements**: Understand what each capability allows
3. **Monitor Audit Logs**: Check for suspicious activity
4. **Update Security Policies**: Adapt to changing requirements
5. **Report Security Issues**: Use responsible disclosure

## Compliance Considerations

### Data Protection

```python
class DataProtection:
    """Data protection compliance measures."""
    
    def __init__(self):
        self.pii_patterns = [
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',  # Email
            r'\b(?:\d{4}[-\s]?){3}\d{4}\b',  # Credit Card
        ]
    
    def check_pii(self, data: str) -> List[str]:
        """Check for PII in data."""
        found_pii = []
        
        for pattern in self.pii_patterns:
            if re.search(pattern, data, re.IGNORECASE):
                found_pii.append(pattern)
        
        return found_pii
    
    def redact_pii(self, data: str) -> str:
        """Redact PII from data."""
        for pattern in self.pii_patterns:
            data = re.sub(pattern, '[REDACTED]', data, flags=re.IGNORECASE)
        
        return data
```

## Security Monitoring

### Real-time Monitoring

```python
class SecurityMonitor:
    """Real-time security monitoring."""
    
    def __init__(self, audit_logger: SecurityAuditLogger):
        self.audit_logger = audit_logger
        self.metrics = {
            'capability_invocations': {},
            'validation_failures': 0,
            'resource_limits_hit': 0,
            'suspicious_patterns': 0,
        }
    
    def monitor_execution(self, execution_id: str):
        """Monitor execution for security issues."""
        # Track capability usage
        # Detect anomalies
        # Alert on suspicious behavior
        pass
    
    def get_security_metrics(self) -> Dict:
        """Get current security metrics."""
        return {
            'metrics': self.metrics,
            'alerts': self.audit_logger.alerts,
            'recent_events': self.audit_logger.audit_log[-100:]
        }
```

## Future Security Enhancements

1. **Machine Learning Anomaly Detection**: Detect unusual patterns
2. **Homomorphic Encryption**: Compute on encrypted data
3. **Zero-Knowledge Proofs**: Verify without revealing
4. **Formal Verification**: Mathematically prove security properties
5. **Hardware Security Modules**: Hardware-based key management

## Security Checklist

- [ ] Security level appropriately configured
- [ ] Capability injection properly enforced
- [ ] Input sanitization implemented
- [ ] Resource limits configured
- [ ] Rate limiting enabled
- [ ] Audit logging active
- [ ] Alert mechanisms configured
- [ ] Security tests passing
- [ ] Threat model reviewed
- [ ] Compliance requirements met

## Version History

- **v1.0.0** (2025-01-03): Initial security model specification