import json
import os
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return res.stdout, res.stderr, res.returncode
    except Exception as e:
        return "", str(e), -1

def collect_repo_metrics():
    metrics = {
        "source_files": 0,
        "source_loc": 0,
        "test_files": 0,
        "test_loc": 0,
        "total_size_kb": 0
    }
    
    src_dirs = ["agents", "backend", "database", "frontend", "services"]
    
    for root, dirs, files in os.walk("."):
        # Skip hidden and cache dirs
        if any(part.startswith('.') or part == '__pycache__' for part in Path(root).parts):
            continue
            
        for file in files:
            file_path = Path(root) / file
            try:
                size = file_path.stat().st_size
                metrics["total_size_kb"] += size / 1024
            except Exception:
                pass
                
            if file.endswith(".py"):
                is_test = "test_" in file or file.endswith("_test.py") or "tests" in Path(root).parts
                try:
                    lines = len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
                    if is_test:
                        metrics["test_files"] += 1
                        metrics["test_loc"] += lines
                    else:
                        # Check if it belongs to source dirs
                        if any(src_dir in Path(root).parts for src_dir in src_dirs):
                            metrics["source_files"] += 1
                            metrics["source_loc"] += lines
                except Exception:
                    pass
                    
    metrics["total_size_kb"] = round(metrics["total_size_kb"], 2)
    return metrics

def generate_report(output_path):
    print("Collecting repo metrics...")
    metrics = collect_repo_metrics()
    
    print("Running pip-audit for vulnerabilities...")
    # Run pip-audit and capture JSON
    audit_out, _, audit_code = run_cmd(["pip-audit", "-r", "requirements.txt", "-f", "json"])
    vulnerabilities = []
    if audit_code == 0 or audit_out:
        try:
            audit_data = json.loads(audit_out)
            # pip-audit json output format can vary, but generally lists packages with vulnerabilities
            for item in audit_data.get("dependencies", []):
                vulns = item.get("vulns", [])
                if vulns:
                    for v in vulns:
                        vulnerabilities.append({
                            "package": item.get("name"),
                            "version": item.get("version"),
                            "id": v.get("id"),
                            "description": v.get("description", "No description provided.")
                        })
        except Exception as e:
            print(f"Error parsing pip-audit output: {e}", file=sys.stderr)
            
    print("Running pip list --outdated...")
    outdated_out, _, _ = run_cmd(["pip", "list", "--outdated", "--format=json"])
    outdated_packages = []
    if outdated_out:
        try:
            outdated_packages = json.loads(outdated_out)
        except Exception as e:
            print(f"Error parsing pip outdated output: {e}", file=sys.stderr)
            
    print("Running bandit for security checks...")
    # Run bandit (exclude tests to keep report relevant to source code)
    bandit_out, _, _ = run_cmd(["bandit", "-r", "agents", "backend", "database", "frontend", "services", "-f", "json"])
    security_issues = []
    if bandit_out:
        try:
            bandit_data = json.loads(bandit_out)
            for issue in bandit_data.get("results", []):
                security_issues.append({
                    "file": issue.get("filename"),
                    "line": issue.get("line_number"),
                    "issue_text": issue.get("issue_text"),
                    "severity": issue.get("issue_severity"),
                    "confidence": issue.get("issue_confidence")
                })
        except Exception as e:
            print(f"Error parsing bandit output: {e}", file=sys.stderr)

    # Compile the Markdown Report
    report = []
    report.append("# ProjectPilot Repository Health & Security Report")
    report.append("\n**Generated on:** Weekly Scheduled Run")
    report.append("\n## 1. Repository Metrics")
    report.append("| Metric | Count / Value |")
    report.append("|---|---|")
    report.append(f"| Source Files | {metrics['source_files']} |")
    report.append(f"| Source Lines of Code (LOC) | {metrics['source_loc']} |")
    report.append(f"| Test Files | {metrics['test_files']} |")
    report.append(f"| Test Lines of Code (LOC) | {metrics['test_loc']} |")
    report.append(f"| Total Repository Size | {metrics['total_size_kb']} KB |")
    
    report.append("\n## 2. Dependency Vulnerabilities (pip-audit)")
    if vulnerabilities:
        report.append(f"⚠️ **Found {len(vulnerabilities)} vulnerabilities!**\n")
        report.append("| Package | Version | Vulnerability ID | Description |")
        report.append("|---|---|---|---|")
        for v in vulnerabilities:
            desc = v['description'][:100] + "..." if len(v['description']) > 100 else v['description']
            report.append(f"| `{v['package']}` | {v['version']} | [{v['id']}](https://github.com/advisories/{v['id']}) | {desc} |")
    else:
        report.append("✅ No known vulnerabilities found in `requirements.txt` dependencies.")
        
    report.append("\n## 3. Outdated Packages")
    if outdated_packages:
        report.append(f"ℹ️ **{len(outdated_packages)} packages are outdated.**\n")
        report.append("| Package | Current Version | Latest Version | Type |")
        report.append("|---|---|---|---|")
        for p in outdated_packages:
            report.append(f"| `{p.get('name')}` | {p.get('version')} | {p.get('latest_version')} | {p.get('latest_file_type')} |")
    else:
        report.append("✅ All dependencies are up to date.")
        
    report.append("\n## 4. Static Security Analysis (Bandit)")
    if security_issues:
        report.append(f"⚠️ **Found {len(security_issues)} potential security issues.**\n")
        report.append("| File:Line | Issue | Severity | Confidence |")
        report.append("|---|---|---|---|")
        for s in security_issues:
            report.append(f"| `{s['file']}:{s['line']}` | {s['issue_text']} | **{s['severity']}** | {s['confidence']} |")
    else:
        report.append("✅ No security issues identified by Bandit static scanning.")
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
        
    print(f"Health report successfully written to {output_path}")

if __name__ == "__main__":
    out_file = "repo-health-report.md"
    if len(sys.argv) > 1:
        out_file = sys.argv[1]
    generate_report(out_file)
