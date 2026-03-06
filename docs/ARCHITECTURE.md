# Family AI Assistant Architecture

## Overview

This assistant is **multi-user, multi-modal, fully self-hosted**, designed to run on local or cloud hardware with Google OAuth access. It separates **user memory**, **household memory**, and **tool orchestration**.

---

## High-Level Architecture

```mermaid
flowchart TD
    A[Web / App UI<br>(React + TypeScript)] -->|OAuth Token / Auth Request| B[FastAPI Backend<br>(Python)]
    B --> C[Agent Orchestration<br>(LangGraph / Custom)]

    C --> D[LLM Runtime<br>(llama.cpp / Ollama)]
    C --> E[Image Generation<br>(Stable Diffusion)]
    C --> F[Audio / TTS Generation<br>(Coqui / Bark)]
    C --> G[Video Generation<br>(Gen-1 / Kaiber)]

    B --> H[Session Memory<br>(last N messages)]
    B --> I[User Memory<br>(Vector DB + Structured DB)]
    B --> J[Household Memory<br>(Shared lists, calendar, devices)]

    D -->|Uses| H
    D -->|Uses| I
    D -->|Uses| J
    E -->|Uses| I
    F -->|Uses| I
    G -->|Uses| I

    style A fill:#f9f,stroke:#333,stroke-width:1px
    style B fill:#bbf,stroke:#333,stroke-width:1px
    style C fill:#bfb,stroke:#333,stroke-width:1px
    style D fill:#ffe4b3,stroke:#333,stroke-width:1px
    style E fill:#ffcccc,stroke:#333,stroke-width:1px
    style F fill:#ccffcc,stroke:#333,stroke-width:1px
    style G fill:#cce0ff,stroke:#333,stroke-width:1px
    style H fill:#fff2cc,stroke:#333,stroke-width:1px
    style I fill:#d9ead3,stroke:#333,stroke-width:1px
    style J fill:#cfe2f3,stroke:#333,stroke-width:1px
    ```


---

## Memory Model

- **Session memory:** last N messages per conversation
- **User memory:** personal facts, preferences, history (vector DB + structured DB)
- **Household memory:** shared info like grocery lists, calendars, devices

All memory is **retrieved and injected dynamically** for LLM prompts.

---

## Tool Orchestration

- LLM decides which **tool or modality** to use per user request
- Example tools:
  - Calendar queries
  - Grocery/shopping list management
  - Home automation endpoints

---

## Security

- Google OAuth 2.0 authentication
- Domain-restricted access (Workspace users only)
- Memory isolation per user

