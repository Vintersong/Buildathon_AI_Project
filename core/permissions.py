from functools import wraps

DENIED_TOOLS = ["record_delete", "bulk_export", "record_merge_auto", "retention_purge"]
DENIED_PREFIXES = ["admin_", "dangerous_"]

class PermissionError(Exception):
    pass

def check_permission(tool_name: str):
    if tool_name in DENIED_TOOLS:
        raise PermissionError(f"Tool {tool_name} is explicitly denied.")
    
    for prefix in DENIED_PREFIXES:
        if tool_name.startswith(prefix):
            raise PermissionError(f"Tool {tool_name} matches denied prefix {prefix}.")

def permission_gated(tool_name: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            check_permission(tool_name)
            return func(*args, **kwargs)
        return wrapper
    return decorator
