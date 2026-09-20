# Lists and Dictionaries

Lists and dictionaries are Python's most common built-in collection types.

## Example

```python
# List: ordered, mutable sequence
fruits = ["apple", "banana", "cherry"]
fruits.append("date")
print(fruits[1])        # banana

# Dictionary: key-value mapping
person = {"name": "Ada", "age": 36}
person["age"] = 37
print(person["name"])   # Ada
```

## Key points

- Lists are ordered and indexed from `0`; use `.append()`, `.remove()`,
  slicing (`fruits[1:3]`) to work with them.
- Dictionaries map unique keys to values; keys must be hashable (strings,
  numbers, tuples).
- List comprehensions build a new list concisely:
  `squares = [x**2 for x in range(5)]`.
- Use `.get(key, default)` on a dict to avoid `KeyError` on missing keys.
