# Control Flow

Control flow statements decide which code runs, and how many times, based on
conditions.

## Example

```python
score = 82

if score >= 90:
    grade = "A"
elif score >= 80:
    grade = "B"
else:
    grade = "C"

print(grade)  # B
```

```python
for i in range(3):
    print(i)   # 0, 1, 2

count = 0
while count < 3:
    count += 1
```

## Key points

- `if` / `elif` / `else` branch on boolean conditions; only truthy values
  execute a branch.
- `for` loops iterate over any iterable (list, string, range, dict, ...).
- `while` loops run until their condition becomes false — watch for infinite
  loops if the condition never changes.
- `break` exits a loop early, `continue` skips to the next iteration.
