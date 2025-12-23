"""
Simple in-memory metrics for Prometheus exposition.
Thread-safe counters.
"""
import threading
from typing import Dict


class Metrics:
    """Thread-safe metrics collection."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {
            "requests_total": 0,
            "requests_2xx": 0,
            "requests_4xx": 0,
            "requests_5xx": 0,
            "job_created_total": 0,
            "job_completed_total": 0,
            "job_error_total": 0,
            "agent_steps_total": 0,
        }
    
    def inc(self, name: str, value: int = 1) -> None:
        """Increment a counter."""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = 0
            self._counters[name] += value
    
    def get(self, name: str) -> int:
        """Get a counter value."""
        with self._lock:
            return self._counters.get(name, 0)
    
    def get_all(self) -> Dict[str, int]:
        """Get all counter values."""
        with self._lock:
            return self._counters.copy()
    
    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        counters = self.get_all()
        
        # Total requests
        lines.append("# HELP agent_requests_total Total HTTP requests")
        lines.append("# TYPE agent_requests_total counter")
        lines.append(f"agent_requests_total {counters['requests_total']}")
        
        # Requests by status class
        lines.append("# HELP agent_requests_by_status HTTP requests by status class")
        lines.append("# TYPE agent_requests_by_status counter")
        lines.append(f'agent_requests_by_status{{status="2xx"}} {counters["requests_2xx"]}')
        lines.append(f'agent_requests_by_status{{status="4xx"}} {counters["requests_4xx"]}')
        lines.append(f'agent_requests_by_status{{status="5xx"}} {counters["requests_5xx"]}')
        
        # Job metrics
        lines.append("# HELP agent_job_created_total Total jobs created")
        lines.append("# TYPE agent_job_created_total counter")
        lines.append(f"agent_job_created_total {counters['job_created_total']}")
        
        lines.append("# HELP agent_job_completed_total Total jobs completed successfully")
        lines.append("# TYPE agent_job_completed_total counter")
        lines.append(f"agent_job_completed_total {counters['job_completed_total']}")
        
        lines.append("# HELP agent_job_error_total Total jobs failed")
        lines.append("# TYPE agent_job_error_total counter")
        lines.append(f"agent_job_error_total {counters['job_error_total']}")
        
        # Agent step metrics
        lines.append("# HELP agent_steps_total Total agent steps executed")
        lines.append("# TYPE agent_steps_total counter")
        lines.append(f"agent_steps_total {counters['agent_steps_total']}")
        
        return "\n".join(lines) + "\n"


# Global metrics instance
metrics = Metrics()
