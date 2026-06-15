"""Deployment Service — generate deployment configs and deploy targets.

Supports:
  - docker       : Dockerfile + docker-compose.yml generation
  - render       : render.yaml for Render.com
  - railway      : railway.json for Railway.app
"""
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.file_service import BASE_DIR
from services.llm_service import call_model

logger = logging.getLogger(__name__)

DEPLOY_DIR = BASE_DIR / "_deployments"


def deploy_project(
    job_id: str,
    target: str = "docker",
    model: str = "local",
) -> Dict[str, Any]:
    job_dir = BASE_DIR / job_id
    if not job_dir.exists():
        return {"job_id": job_id, "status": "error", "error": "Project files not found."}

    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    deploy_path = DEPLOY_DIR / job_id
    deploy_path.mkdir(parents=True, exist_ok=True)

    try:
        if target == "docker":
            return _generate_docker(job_id, job_dir, deploy_path, model)
        elif target == "render":
            return _generate_render(job_id, job_dir, deploy_path, model)
        elif target == "railway":
            return _generate_railway(job_id, job_dir, deploy_path, model)
        else:
            return {"job_id": job_id, "status": "error", "error": f"Unknown target: {target}"}
    except Exception as exc:
        logger.error("Deploy failed for %s: %s", job_id, exc)
        return {"job_id": job_id, "status": "error", "error": str(exc)[:500]}


def _read_project_files(job_dir: Path) -> Dict[str, str]:
    files = {}
    for fp in sorted(job_dir.rglob("*")):
        if fp.is_file() and "__pycache__" not in str(fp):
            try:
                files[str(fp.relative_to(job_dir))] = fp.read_text(encoding="utf-8")
            except Exception:
                pass
    return files


def _detect_stack(files: Dict[str, str]) -> Dict[str, str]:
    stack = {"backend": "python", "port": "8000", "build": "", "start": ""}
    for name in files:
        if "requirements.txt" in name:
            stack["build"] = "pip install -r requirements.txt"
        elif "package.json" in name:
            stack["backend"] = "node"
            stack["build"] = "npm install"
            data = json.loads(files[name])
            stack["start"] = data.get("scripts", {}).get("start", "npm start")
        elif "main.py" in name or "app.py" in name:
            stack["start"] = f"python {name}"
    if not stack["start"]:
        stack["start"] = "python main.py"
    return stack


def _generate_docker(job_id: str, job_dir: Path, deploy_path: Path, model: str) -> Dict[str, Any]:
    files = _read_project_files(job_dir)
    stack = _detect_stack(files)
    has_requirements = any("requirements.txt" in f for f in files)

    dockerfile_parts = [f"FROM python:3.11-slim"]
    dockerfile_parts.append("WORKDIR /app")
    dockerfile_parts.append("COPY . .")
    if has_requirements:
        dockerfile_parts.append(f"RUN pip install --no-cache-dir -r requirements.txt")
    else:
        dockerfile_parts.append("RUN pip install --no-cache-dir fastapi uvicorn")
    dockerfile_parts.append(f"EXPOSE {stack['port']}")
    dockerfile_parts.append(f'CMD ["{stack['start'].split()[0]}", "{stack['start'].split()[1]}", "--host", "0.0.0.0", "--port", "{stack['port']}"]')

    dockerfile_path = deploy_path / "Dockerfile"
    dockerfile_path.write_text("\n".join(dockerfile_parts), encoding="utf-8")

    compose = {
        "version": "3.8",
        "services": {
            "app": {
                "build": ".",
                "ports": [f"{stack['port']}:{stack['port']}"],
                "environment": ["PYTHONUNBUFFERED=1"],
                "restart": "unless-stopped",
            }
        },
    }
    compose_path = deploy_path / "docker-compose.yml"
    compose_path.write_text(json.dumps(compose, indent=2), encoding="utf-8")

    return {
        "job_id": job_id,
        "target": "docker",
        "status": "generated",
        "files": ["Dockerfile", "docker-compose.yml"],
        "paths": [str(deploy_path / "Dockerfile"), str(deploy_path / "docker-compose.yml")],
    }


def _generate_render(job_id: str, job_dir: Path, deploy_path: Path, model: str) -> Dict[str, Any]:
    files = _read_project_files(job_dir)
    stack = _detect_stack(files)
    render = {
        "services": [{
            "type": "web",
            "name": job_id[:20],
            "env": "python",
            "buildCommand": stack["build"] or "pip install -r requirements.txt",
            "startCommand": stack["start"] or "python main.py",
            "healthCheckPath": "/health",
        }]
    }
    render_path = deploy_path / "render.yaml"
    import yaml
    render_path.write_text(yaml.dump(render), encoding="utf-8")
    return {
        "job_id": job_id,
        "target": "render",
        "status": "generated",
        "files": ["render.yaml"],
        "paths": [str(render_path)],
    }


def _generate_railway(job_id: str, job_dir: Path, deploy_path: Path, model: str) -> Dict[str, Any]:
    railway = {
        "build": {
            "builder": "NIXPACKS",
            "buildCommand": "pip install -r requirements.txt" if (job_dir / "requirements.txt").exists() else "echo 'no deps'"
        },
        "deploy": {
            "startCommand": "python main.py",
            "healthcheckPath": "/health",
            "restartPolicyType": "ON_FAILURE",
        }
    }
    railway_path = deploy_path / "railway.json"
    railway_path.write_text(json.dumps(railway, indent=2), encoding="utf-8")
    return {
        "job_id": job_id,
        "target": "railway",
        "status": "generated",
        "files": ["railway.json"],
        "paths": [str(railway_path)],
    }
