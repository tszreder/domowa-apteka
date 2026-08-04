---
project: domowa-apteka
last_updated: 2026-07-31
---

# Learner Profile

Used by the `concept-tutor` skill to target explanations and pick analogies. Update this
file directly (or just tell the agent) if any of this changes.

## Known background

- **Role**: BI Architect.
- **Core stack**: Microsoft/Azure, mostly on the data side — Azure Data Factory (ADF),
  Azure SQL, Databricks, Azure Functions, Logic Apps.
- **Main tool**: Microsoft Fabric and Power BI — Power BI specifically is the primary
  day-to-day tool.
- **Python**: comfortable with the basics, but for scripting and data engineering — not
  for building applications.

## Explicitly NOT familiar with (assume zero prior exposure unless a doc in this folder
## already covers it, or told otherwise directly)

- Web development in general.
- Scaffolding / bootstrapping a project.
- What the components of an "app" are (as opposed to a data pipeline or report).
- What deployment involves for a web app.

## This project's stack (the "specific" half of every generic-vs-specific split)

- **Framework**: Django (Python), see `context/foundation/tech-stack.md`.
- **Deployment platform**: Railway, see `context/foundation/infrastructure.md`
  (Fly.io was the runner-up).
