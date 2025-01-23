def linespace_to_string(func, *args, **kwargs):
    args_str = ", ".join(map(str, args))
    kwargs_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    combined = ", ".join(filter(None, [args_str, kwargs_str]))
    return f"{func.__name__}({combined})"
