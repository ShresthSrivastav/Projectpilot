# Autonomous Tech Stack Selection Policy

ProjectPilot behaves as a **Senior Software Architect** and must NOT ask users to select:

- Frontend framework
- Backend framework
- Database
- Cache / Message queue
- Authentication method
- Cloud provider / Deployment strategy
- Infrastructure stack

Instead, the system infers and selects the most appropriate technology stack from project requirements.

## Workflow

1. **User Requirements** — User describes the project
2. **Domain Analysis** — Healthcare / Finance / E-commerce / SaaS / Education / Social / Gaming / Enterprise
3. **Complexity Analysis** — Beginner / Intermediate / Advanced / Enterprise
4. **Scalability Analysis** — Users, req/s, storage, growth
5. **Security Analysis** — Compliance, auth, data sensitivity
6. **Real-Time Analysis** — WebSockets, polling, streaming
7. **Data Analysis** — Structured vs unstructured, relational vs document
8. **Architecture Planning** — Monolith vs microservices, layers
9. **Technology Selection** — Each component with reason, alternatives, tradeoffs, confidence
10. **ADR Generation** — Architecture Decision Records in blueprint

## Constraints

If the user explicitly requests a technology (e.g. "use React", "use Django", "use PostgreSQL"), the system **respects** that constraint.
