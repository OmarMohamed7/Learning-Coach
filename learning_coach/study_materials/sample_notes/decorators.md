# Decorators

A decorator wraps a function to extend its behavior without modifying its
source code. It's just a function that takes a function and returns a
function.

## Example

```python
import time
from functools import wraps

def timed(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper

@timed
def slow_add(a, b):
    time.sleep(0.1)
    return a + b

slow_add(2, 3)
```

`@timed` is sugar for `slow_add = timed(slow_add)`.

## Key points

- Decorators rely on closures: `wrapper` closes over `func`.
- Always use `functools.wraps` so the wrapped function keeps its original
  name and docstring.
- A decorator can take its own arguments by adding another layer of nesting
  (a "decorator factory").
