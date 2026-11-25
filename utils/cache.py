import asyncio
import functools
import time
from typing import Any, Dict, Tuple

__all__ = ["ttl_cache"]


def ttl_cache(seconds: float, max_entries: int = 512):
    """Cache an async function's results for `seconds`, keyed by its arguments.

    Concurrent calls with the same arguments share one in-flight request, so a burst of
    clients asking for the same bracket costs the upstream site one request, not one each.
    Failures are not cached.

    The work runs in its own task and every caller waits on it through `shield`, so a client
    disconnecting (Sanic cancels its handler) cancels only that client's wait, never the
    fetch the other callers are sharing.
    """

    def decorator(fn):
        results: Dict[Tuple, Tuple[float, Any]] = {}
        pending: Dict[Tuple, asyncio.Task] = {}

        async def run(key, args, kwargs):
            try:
                value = await fn(*args, **kwargs)
                results[key] = (time.monotonic(), value)
                if len(results) > max_entries:
                    oldest = min(results, key=lambda k: results[k][0])
                    del results[oldest]
                return value
            finally:
                pending.pop(key, None)

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))

            hit = results.get(key)
            if hit and time.monotonic() - hit[0] < seconds:
                return hit[1]

            task = pending.get(key)
            if task is None:
                task = asyncio.ensure_future(run(key, args, kwargs))
                pending[key] = task
                # Retrieve a failure even if every caller has gone, so it isn't logged as
                # "exception never retrieved".
                task.add_done_callback(lambda t: t.cancelled() or t.exception())
            return await asyncio.shield(task)

        wrapper.cache_clear = lambda: results.clear()
        return wrapper

    return decorator
