from agent_to_worker import scan_agent_to_worker
from async_flow_scanner import scan_risky_async
from cache_use_scanner import scan_risky_cache_patterns
from deploy_old_way import scan_deploy_v3_candidates
from deprecated_import_scanner import scan_risky_import
from failed_task_flow_scanner import scan_flow_error
from shared_mutable_scanner import scan_shared_mutable

if __name__ == "__main__":
    scan_risky_import()
    scan_deploy_v3_candidates()
    scan_risky_cache_patterns()
    scan_shared_mutable()
    scan_risky_async()
    scan_agent_to_worker()
    scan_flow_error()
