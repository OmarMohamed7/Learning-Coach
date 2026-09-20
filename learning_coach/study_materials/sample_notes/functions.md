# Functions

A function is a reusable, named block of code that takes inputs (parameters)
and optionally returns a value.

## Example

```python
def greet(name, greeting="Hello"):
    return f"{greeting}, {name}!"

print(greet("Ada"))              # Hello, Ada!
print(greet("Ada", "Hi"))        # Hi, Ada!
```

## Key points

- `def` defines a function; parameters can have default values.
- `return` sends a value back to the caller — a function with no `return`
  implicitly returns `None`.
- Arguments can be passed positionally or by keyword: `greet(name="Ada")`.
- `*args` collects extra positional arguments, `**kwargs` collects extra
  keyword arguments.
- Functions are first-class objects in Python — they can be assigned to
  variables, passed as arguments, and returned from other functions.
