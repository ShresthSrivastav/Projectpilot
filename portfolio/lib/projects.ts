export interface Project {
  title: string
  year: string
  description: string
  url?: string
  tags?: string[]
}

export const projects: Project[] = [
  {
    title: "ProjectPilot",
    year: "2025-2026",
    description:
      "Autonomous AI agent platform for software engineering — multi-agent orchestration, real-time monitoring, self-healing infrastructure.",
    url: "https://zivio.tech",
    tags: ["AI", "Agents", "Full-stack"],
  },
  {
    title: "Zivio",
    year: "2024-2025",
    description:
      "Production deployment platform with CI/CD pipelines, container orchestration, and automated SSL management for microservices.",
    url: "#",
    tags: ["DevOps", "Cloud", "Infra"],
  },
  {
    title: "Design Systems Toolkit",
    year: "2024",
    description:
      "Component library and design token framework for consistent multi-brand UI at scale. Themeable, accessible, tree-shakeable.",
    url: "#",
    tags: ["Design", "Components", "CSS"],
  },
  {
    title: "Autonomous Code Review",
    year: "2023-2024",
    description:
      "LLM-powered code review bot that integrates with GitHub PRs. Static analysis + semantic understanding for actionable feedback.",
    url: "#",
    tags: ["AI", "DevTools", "Python"],
  },
]
