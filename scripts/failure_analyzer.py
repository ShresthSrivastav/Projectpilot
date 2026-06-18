import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile


def get_github_api(url, token):
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "ProjectPilot-Failure-Analyzer")
    try:
        with urllib.request.urlopen(req) as response:
            return response.read(), response.info()
    except urllib.error.HTTPError as e:
        print(f"HTTP Error querying API: {e.code} - {e.reason}", file=sys.stderr)
        return None, None
    except Exception as e:
        print(f"Error querying API: {e}", file=sys.stderr)
        return None, None

def analyze_failure(run_id, repo, token, output_dir):
    print(f"Analyzing failure for run {run_id} in {repo}...")
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Fetch Run Info
    run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
    run_data_raw, _ = get_github_api(run_url, token)
    if not run_data_raw:
        print("Could not retrieve run info.", file=sys.stderr)
        return False
        
    run_info = json.loads(run_data_raw.decode('utf-8'))
    
    # 2. Fetch Jobs info
    jobs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
    jobs_data_raw, _ = get_github_api(jobs_url, token)
    if not jobs_data_raw:
        print("Could not retrieve jobs info.", file=sys.stderr)
        return False
        
    jobs_info = json.loads(jobs_data_raw.decode('utf-8'))
    
    failed_jobs = []
    for job in jobs_info.get("jobs", []):
        if job.get("conclusion") == "failure":
            failed_steps = []
            for step in job.get("steps", []):
                if step.get("conclusion") == "failure":
                    failed_steps.append({
                        "name": step.get("name"),
                        "number": step.get("number"),
                        "conclusion": step.get("conclusion")
                    })
            failed_jobs.append({
                "id": job.get("id"),
                "name": job.get("name"),
                "html_url": job.get("html_url"),
                "failed_steps": failed_steps,
                "log_summary": []
            })
            
    # 3. Fetch Logs (zip archive)
    logs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs"
    logs_zip_raw, info = get_github_api(logs_url, token)
    
    if logs_zip_raw:
        try:
            with zipfile.ZipFile(io.BytesIO(logs_zip_raw)) as z:
                # Find log files for failed jobs
                for failed_job in failed_jobs:
                    # In GitHub Actions logs zip, log files are named by job name and step number
                    # Example: "1_Lint & Test (Python 3.12).txt"
                    # We can search the zip list for names containing the job name or job ID
                    job_name_sanitized = "".join([c if c.isalnum() or c in " -_" else "_" for c in failed_job["name"]])
                    for file_name in z.namelist():
                        # Match files like "JobName/StepNum_StepName.txt" or "JobName.txt"
                        if job_name_sanitized in file_name or str(failed_job["id"]) in file_name:
                            try:
                                with z.open(file_name) as f:
                                    log_lines = [line.decode('utf-8', errors='replace').rstrip() for line in f.readlines()]
                                    # Extract tracebacks or error logs
                                    errors = []
                                    in_traceback = False
                                    traceback_lines = []
                                    for line in log_lines:
                                        # Detect python traceback or ruff/pytest error patterns
                                        if "Traceback (most recent call last)" in line or "stderr" in line.lower() or "error" in line.lower():
                                            in_traceback = True
                                        if in_traceback:
                                            traceback_lines.append(line)
                                            if len(traceback_lines) > 50:  # Cap length of single traceback block
                                                errors.append("\n".join(traceback_lines))
                                                traceback_lines = []
                                                in_traceback = False
                                        elif "failed" in line.lower() or "failure" in line.lower():
                                            errors.append(line)
                                            
                                    if traceback_lines:
                                        errors.append("\n".join(traceback_lines))
                                        
                                    failed_job["log_summary"].append({
                                        "file": file_name,
                                        "errors": errors[-20:]  # Keep last 20 identified errors/tracebacks
                                    })
                            except Exception as e:
                                print(f"Error reading log file {file_name}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error processing logs zip: {e}", file=sys.stderr)
            
    # 4. Generate structured JSON report
    report = {
        "run_id": run_id,
        "repo": repo,
        "workflow": run_info.get("name"),
        "trigger": run_info.get("event"),
        "commit": run_info.get("head_sha"),
        "branch": run_info.get("head_branch"),
        "run_number": run_info.get("run_number"),
        "conclusion": run_info.get("conclusion"),
        "failed_jobs": failed_jobs
    }
    
    report_path = os.path.join(output_dir, "failure-report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print(f"Failure report generated successfully at {report_path}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze GitHub Actions run failures")
    parser.add_argument("--run-id", required=True, type=int, help="The GHA run ID")
    parser.add_argument("--repo", required=True, help="GitHub repository (owner/name)")
    parser.add_argument("--token", required=True, help="GitHub Token")
    parser.add_argument("--output-dir", default="failure_artifacts", help="Directory to save report and logs")
    
    args = parser.parse_args()
    success = analyze_failure(args.run_id, args.repo, args.token, args.output_dir)
    sys.exit(0 if success else 1)
