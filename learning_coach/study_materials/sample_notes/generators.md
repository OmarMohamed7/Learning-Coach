# Generators

A generator is a function that produces a sequence of values lazily, one at
a time, using `yield` instead of `return`.

## Example

```python
def fibonacci(limit):
    a, b = 0, 1
    while a < limit:
        yield a
        a, b = b, a + b

for n in fibonacci(20):
    print(n)  # 0 1 1 2 3 5 8 13
```

Each call to `next()` resumes the function right after the last `yield`,
keeping its local state between calls.

## Key points

- Generators don't compute all values upfront — good for large or infinite
  sequences.
- A function with any `yield` in its body becomes a generator function;
  calling it returns a generator object, not the result.
- Generator expressions (`(x*x for x in range(10))`) are the lazy version of
  list comprehensions.
