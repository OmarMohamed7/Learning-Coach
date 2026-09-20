# Variables and Data Types

A variable is a name bound to a value in memory. Python is dynamically typed:
you don't declare a type, the interpreter infers it from the value assigned.

## Example

```python
name = "Ada"          # str
age = 36               # int
height = 1.7           # float
is_learning = True     # bool

print(type(age))       # <class 'int'>
```

## Key points

- Variable names are case-sensitive and must start with a letter or underscore.
- Python's core built-in types: `int`, `float`, `str`, `bool`, `list`, `tuple`,
  `dict`, `set`, `None`.
- Reassigning a variable to a value of a different type is legal — the name
  just points to the new object.
- Use `type(x)` to inspect a variable's current type at runtime.
