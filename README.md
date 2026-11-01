# GOOGL_AI: Engineering Agent Pipeline (Techie)

An automated engineering agent pipeline built with the **Google Agent Development Kit (ADK)** and the `google-genai` SDK. This repository orchestrates agent workflows to generate production-grade content, technical documentation, and curriculum modules for an enterprise **AS9100D / ISO 9001 Quality Management System (QMS)** manufacturing stack (React, Node.js, Microsoft SQL Server).

---

## 🛠️ Tech Stack & Architecture

- **Runtime & Environment:** Python 3.10+ managed via [`uv`](https://github.com/astral-sh/uv)
- **Agent Framework:** Google ADK (`google.adk.runners.InMemoryRunner`)
- **Model Engine:** Google GenAI SDK (`google.genai`)
- **Domain Focus:** Electronics Manufacturing Services (EMS), AS9100D/ISO 9001 compliance, WIP tracking, and industrial PCBA workflows.

---

## 📁 Repository Structure

```text
GOOGL_AI/
├── src/
│   └── googl_ai/
│       └── __init__.py       # Package definition
├── agent.py                  # Core agent pipeline & CLI runner entry point
├── pyproject.toml            # Project configuration and dependency definitions
├── uv.lock                   # Deterministic package dependency tree
├── .python-version           # Pinned Python version
├── .gitignore                # Excludes secrets (.env), venv, and generated artifacts
└── output/                   # Target directory for generated agent outputs (git-ignored)

## Use
After defining global scope in agent.py, add specific module focus component 
then run...

uv run python agent.py

