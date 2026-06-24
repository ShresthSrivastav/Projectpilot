"""Diagram Service — generates Mermaid.js architecture diagrams from blueprint data."""

from typing import Any


def _escape_mermaid(text: str) -> str:
    return text.replace('"', "#quot;").replace("(", "[").replace(")", "]")


def generate_component_diagram(blueprint: dict[str, Any]) -> str:
    files = blueprint.get("files", [])
    tech_stack = blueprint.get("tech_stack", {})
    routes = blueprint.get("routes", [])

    lines = ["graph TD", f'    A["User"] -->|"HTTP"| B["{tech_stack.get("backend", "API")}"]']

    frontend_files = [f for f in files if "frontend" in f.get("path", "")]
    database_files = [f for f in files if "database" in f.get("path", "")]

    if frontend_files:
        lines.append(f'    C["{tech_stack.get("frontend", "UI")}"] -->|"REST"| B')
        lines.append("    A --> C")

    lines.append(f'    B -->|"ORM"| D["{tech_stack.get("db", "Database")}"]')

    if database_files:
        for f in database_files:
            name = Path(f.get("path", "")).stem.capitalize()
            lines.append(f'    D --> E["{name}"]')

    if routes:
        route_count = len(routes)
        methods = set(r.get("method", "GET") for r in routes)
        lines.append(f'    B -->|"{route_count} routes [{",".join(methods)}]"| F["Endpoints"]')

    lines.append("")
    lines.append("    style A fill:#1e3a5f,color:#fff")
    lines.append("    style B fill:#2d6a4f,color:#fff")
    lines.append("    style D fill:#5c4033,color:#fff")

    return "\n".join(lines)


def generate_er_diagram(blueprint: dict[str, Any]) -> str:
    tables = blueprint.get("db_tables", [])
    if not tables:
        return "erDiagram\n    No tables defined"

    lines = ["erDiagram"]
    for table in tables:
        name = table.get("name", "table")
        columns = table.get("columns", ["id:string"])
        lines.append(f"    {name} {{")
        for col in columns:
            parts = col.split(":")
            col_name = _escape_mermaid(parts[0])
            col_type = _escape_mermaid(parts[1]) if len(parts) > 1 else "string"
            pk = "PK" if col_name.lower() in ("id", "pk", "primary_key") else ""
            lines.append(f"        {col_type} {col_name} {pk}")
        lines.append("    }")

    for i, t1 in enumerate(tables):
        for t2 in tables[i + 1 :]:
            n1 = t1.get("name", "t1")
            n2 = t2.get("name", "t2")
            lines.append(f"    {n1} ||--o{{ {n2} : has")

    return "\n".join(lines)


def generate_flow_diagram(agents: list[str]) -> str:
    lines = ["flowchart LR"]
    for i, agent in enumerate(agents):
        n = agent.replace(" ", "_")
        lines.append(f'    {n}["{agent}"]')
        if i > 0:
            prev = agents[i - 1].replace(" ", "_")
            lines.append(f"    {prev} --> {n}")
    lines.append("")
    for i, agent in enumerate(agents):
        n = agent.replace(" ", "_")
        if i % 2 == 0:
            lines.append(f"    style {n} fill:#1e3a5f,color:#fff")
        else:
            lines.append(f"    style {n} fill:#2d6a4f,color:#fff")
    return "\n".join(lines)


def generate_architecture_markdown(blueprint: dict[str, Any], agents: list[str]) -> str:
    component = generate_component_diagram(blueprint)
    er = generate_er_diagram(blueprint)
    flow = generate_flow_diagram(agents)

    tech = blueprint.get("tech_stack", {})
    routes = blueprint.get("routes", [])
    tables = blueprint.get("db_tables", [])

    md = "# Architecture Overview\n\n"
    md += "## Tech Stack\n\n"
    md += f"- **Backend:** {tech.get('backend', 'N/A')}\n"
    md += f"- **Frontend:** {tech.get('frontend', 'N/A')}\n"
    md += f"- **Database:** {tech.get('db', 'N/A')}\n"
    md += f"- **Auth:** {tech.get('auth', 'N/A')}\n\n"

    md += "## Component Diagram\n\n```mermaid\n" + component + "\n```\n\n"

    if tables:
        md += "## Entity Relationship Diagram\n\n```mermaid\n" + er + "\n```\n\n"

    if agents:
        md += "## Agent Pipeline\n\n```mermaid\n" + flow + "\n```\n\n"

    md += "## API Routes\n\n| Method | Path | Description |\n|--------|------|-------------|\n"
    for r in routes:
        md += f"| {r.get('method', 'GET')} | `{r.get('path', '/')}` | {r.get('description', '')} |\n"

    return md


def generate_project_overview_markdown(project_name: str, file_count: int, test_results: dict) -> str:
    md = f"# {project_name} — Project Overview\n\n"
    md += f"- **Files:** {file_count}\n"
    md += f"- **Tests:** {test_results.get('total', 0)} collected, "
    md += f"{test_results.get('passed', 0)} passed, "
    md += f"{test_results.get('failed', 0)} failed\n"
    if test_results.get("summary"):
        md += f"- **Test Summary:** {test_results['summary']}\n"
    return md


from pathlib import Path
