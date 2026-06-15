import ast, pathlib, sys

base = pathlib.Path("generated_projects")
errors = []
total_py = 0

for d in sorted(base.iterdir()):
    if not d.is_dir():
        continue
    for f in sorted(d.rglob("*.py")):
        if "__pycache__" in str(f):
            continue
        total_py += 1
        try:
            ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e:
            rel = f.relative_to(base)
            errors.append(f"{rel}: {e}")

if errors:
    print(f"SYNTAX ERRORS ({len(errors)}):")
    for e in errors:
        print(f"  {e}")
else:
    print("All generated project Python files have valid syntax")
print(f"Total: {total_py} Python files checked across {len(list(base.iterdir()))} projects")
