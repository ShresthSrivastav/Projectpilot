import pathlib

base = pathlib.Path("generated_projects")
count = 0
for f in base.rglob("*.py"):
    if "__pycache__" in str(f):
        continue
    raw = f.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
        f.write_text(text, encoding="utf-8")
        count += 1
        print(f"Fixed: {f.relative_to(base)}")

print(f"Fixed {count} files")
