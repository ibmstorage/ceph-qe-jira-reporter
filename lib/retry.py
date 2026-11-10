import logging
import time
from functools import wraps


def retry(exception_to_check, tries=5, delay=10):
    def deco_retry(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            remaining = tries
            while remaining > 1:
                try:
                    return func(*args, **kwargs)
                except exception_to_check as exc:
                    logging.warning(
                        "Exception caught: %s. Retrying %s more times.",
                        exc,
                        remaining - 1,
                    )
                    time.sleep(delay)
                    remaining -= 1
            return func(*args, **kwargs)

        return wrapper

    return deco_retry
