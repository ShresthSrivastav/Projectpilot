import pathlib

base = pathlib.Path("generated_projects")
test_files = sorted(base.rglob("test_*.py"))

for f in test_files:
    if "__pycache__" in str(f):
        continue
    text = f.read_text(encoding="utf-8")
    lines = text.strip().split("\n")
    rel = f.relative_to(base)
    test_count = sum(1 for l in lines if l.strip().startswith("def test_"))
    assert_count = sum(1 for l in lines if "assert " in l or "assert(" in l)
    print(f"  {rel}: {len(lines)} lines, {test_count} tests, {assert_count} asserts")

print(f"\nTotal: {len(test_files)} test files audited")
