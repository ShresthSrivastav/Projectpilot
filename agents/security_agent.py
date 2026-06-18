from database.chroma_db import log_to_db
from services.file_service import BASE_DIR
from services.llm_service import call_model

SECURITY_CHECKS = [
    {
        "name": "SQL Injection",
        "severity": "HIGH",
        "pattern": r'execute\([^)]*["\'][^"\']*\{|cursor\.execute\([^)]*["\'][^"\']*%|text\+|f["\'][^"\']*(?:SELECT|INSERT|UPDATE|DELETE)',
        "recommendation": "Use parameterized queries or an ORM instead of string formatting in SQL statements."
    },
    {
        "name": "Hardcoded API Key",
        "severity": "HIGH",
        "pattern": r'(?:api_key|api_secret|apikey|secret_key|secret)\s*[=:]\s*["\'][A-Za-z0-9_\-]{16,}["\']',
        "recommendation": "Store secrets in environment variables or a secrets manager."
    },
    {
        "name": "Hardcoded Password",
        "severity": "HIGH",
        "pattern": r'password\s*[=:]\s*["\'][^"\']{3,}["\']',
        "recommendation": "Use a secrets manager or prompt for passwords at runtime."
    },
    {
        "name": "Cross-Site Scripting (XSS)",
        "severity": "HIGH",
        "pattern": r'(?:render_template|render_template_string|mark_safe|safe\s*\||Markup)',
        "recommendation": "Use auto-escaping templates and avoid marking user input as safe."
    },
    {
        "name": "Insecure Deserialization",
        "severity": "HIGH",
        "pattern": r'(?:pickle\.loads?|yaml\.load(?!.*SafeLoader)|shelve\.open|marshal\.loads?)',
        "recommendation": "Use safe deserialization like json.loads() or yaml.safe_load()."
    },
    {
        "name": "Missing Authentication",
        "severity": "MEDIUM",
        "pattern": r'@(?:app|route)\.route.*\n(?!.*@login_required|.*@require_auth)',
        "recommendation": "Decorate endpoints with @login_required or similar auth decorators."
    },
    {
        "name": "Debug Mode Enabled",
        "severity": "MEDIUM",
        "pattern": r'(?:app\.run\(.*debug\s*=\s*True|DEBUG\s*=\s*True|FLASK_DEBUG=1)',
        "recommendation": "Disable debug mode in production environments."
    },
    {
        "name": "Path Traversal",
        "severity": "HIGH",
        "pattern": r'open\([^)]*\.\.\.|os\.path\.join\([^)]*request|send_file\([^)]*request',
        "recommendation": "Validate and sanitize user-supplied file paths."
    },
    {
        "name": "Sensitive Data Exposure",
        "severity": "LOW",
        "pattern": r'(?:print|logging)\.(?:info|debug|warning)\(.*(?:password|token|secret|key|credit_card|ssn)',
        "recommendation": "Avoid logging sensitive information."
    },
    {
        "name": "SSTI (Server-Side Template Injection)",
        "severity": "HIGH",
        "pattern": r'render_template_string\([^)]*request|Template\([^)]*\.format\([^)]*request',
        "recommendation": "Use render_template with separate template files instead of inline templates with user input."
    }
]

LLM_PROMPT_TEMPLATE = """You are a security code reviewer. Analyze the following Python code for logic-level security vulnerabilities that are not obvious from static regex scanning (e.g., business logic flaws, IDOR, CSRF, race conditions, improper access control). Return findings as a JSON array of objects with keys: "name", "severity" (HIGH/MEDIUM/LOW), "file", "line", "description", "recommendation". If no issues found, return an empty array.

File: {filepath}

```python
{content}
```"""


def _scan_file(filepath, model="local"):
    findings = []
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        findings.append({
            "name": "File Read Error",
            "severity": "LOW",
            "file": filepath,
            "line": 0,
            "description": f"Could not read file: {str(e)}",
            "recommendation": "Ensure file permissions and encoding are correct."
        })
        return findings

    for check in SECURITY_CHECKS:
        import re
        for match in re.finditer(check["pattern"], content, re.MULTILINE):
            line_num = content[:match.start()].count("\n") + 1
            findings.append({
                "name": check["name"],
                "severity": check["severity"],
                "file": filepath,
                "line": line_num,
                "description": f"Potential {check['name']} vulnerability detected.",
                "recommendation": check["recommendation"]
            })

    if not findings:
        try:
            import json
            rel_path = filepath.replace(str(BASE_DIR), "").lstrip("\\/")
            prompt = LLM_PROMPT_TEMPLATE.format(filepath=rel_path, content=content)
            response = call_model(prompt, model=model)
            llm_findings = json.loads(response) if isinstance(response, str) else response
            if isinstance(llm_findings, list):
                for f in llm_findings:
                    f["file"] = filepath
                    findings.append(f)
        except Exception:
            pass

    return findings


def run(generated_files, job_id, blueprint=None, model="local"):
    log_to_db(job_id, "SecurityAgent", "Starting security scan.")
    all_findings = []
    critical_count = 0
    high_count = 0
    medium_count = 0
    low_count = 0

    for fpath in generated_files:
        if not fpath.endswith(".py"):
            continue
        results = _scan_file(fpath, model=model)
        for r in results:
            all_findings.append(r)
            if r["severity"] == "HIGH":
                high_count += 1
            elif r["severity"] == "MEDIUM":
                medium_count += 1
            elif r["severity"] == "LOW":
                low_count += 1

    report_path = str(BASE_DIR / "SECURITY_REPORT.md")
    report_lines = ["# Security Assessment Report", f"**Job ID:** {job_id}", f"**Blueprint:** {blueprint or 'N/A'}", f"**Model:** {model}", "", "## Vulnerability Summary", "", "| Severity | Count |", "|----------|-------|",
                     f"| Critical | {critical_count} |", f"| High     | {high_count} |", f"| Medium   | {medium_count} |", f"| Low      | {low_count} |", "", "## Detailed Findings", "", "| # | Severity | File | Line | Issue | Recommendation |",
                     "|---|----------|------|------|-------|---------------|"]
    for i, f in enumerate(all_findings, 1):
        report_lines.append(f"| {i} | {f['severity']} | {f['file']} | {f['line']} | {f['name']}: {f.get('description', '')} | {f['recommendation']} |")

    report_lines.append("")
    report_lines.append("---")
    report_lines.append("_Generated by ProjectPilot Security Agent_")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    log_to_db(job_id, "SecurityAgent", f"Scan complete. CRITICAL={critical_count} HIGH={high_count} MEDIUM={medium_count} LOW={low_count}")

    return {
        "report_file": "SECURITY_REPORT.md",
        "findings": all_findings,
        "critical": critical_count,
        "high": high_count,
        "medium": medium_count,
        "low": low_count
    }
