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

- **Session memory:** last N messages per conversation, loaded from canonical Postgres rows during prompt assembly
- **Conversation memory:** latest per-conversation summary stored canonically in Postgres and refreshed after successful assistant replies
- **User memory:** durable per-user facts stored canonically in Postgres and mirrored into Chroma only for retrieval support
- **Household memory:** shared info like grocery lists, calendars, devices

All memory is **retrieved and injected dynamically** for LLM prompts.

Background extraction runs after the visible assistant response is persisted. It refreshes summaries and durable facts without blocking the request path, then mirrors saved rows into Chroma for retrieval support.

---

## Tool Orchestration

- LLM decides which **tool or modality** to use per user request
- The backend exposes an explicit allowlist of tools through `ToolFactory` and executes them through `ToolService`
- Current research tools:
  - `web_search` for candidate-source discovery
  - `web_fetch` for grounded page reads with public-web-only URL validation
- Example future tools:
  - Calendar queries
  - Grocery/shopping list management
  - Home automation endpoints

---

## Trust & Evidence UI

- Assistant messages can persist compact `annotations` payloads that describe fetched sources, tools used, memory hits, saved memory, and terminal failure metadata
- The desktop chat UI renders those persisted annotations directly as an inline trust row plus an evidence details panel
- Reloaded conversations reuse the stored annotations instead of regenerating provenance on the client
- Mobile-specific trust UI behavior is intentionally deferred and tracked in `TODOS.md`

---

## Security

- Google OAuth 2.0 authentication
- Domain-restricted access (Workspace users only)
- Memory isolation per user
