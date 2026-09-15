# Closures

A closure is a function that remembers the variables from the scope it was
defined in, even after that outer scope has finished executing.

## Example

```python
def make_counter():
    count = 0

    def increment():
        nonlocal count
        count += 1
        return count

    return increment

counter = make_counter()
print(counter())  # 1
print(counter())  # 2
```

`increment` closes over `count` from `make_counter`'s scope. Each call to
`make_counter()` creates a fresh, independent `count`.

## Key points

- The inner function must reference a variable from the enclosing scope.
- Use `nonlocal` to reassign (not just read) an enclosing variable.
- Closures are how decorators keep state between calls.
