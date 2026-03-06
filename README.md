# Family AI Assistant

A fully self-hosted, multi-user, multi-modal AI assistant designed for household use.  
Supports **text, image, audio, and video generation**, with **per-user memory**, **customizable personality**, and **tool orchestration**.

---

## Features

- **Multi-user support**  
  Each family member has a separate memory and personality.  
- **Memory system**  
  Persistent user memory and shared household memory stored in vector DB + structured DB.  
- **Multi-modal capabilities**  
  - Text: llama.cpp / Ollama  
  - Images: Stable Diffusion  
  - Audio: TTS (Coqui, Bark)  
  - Video: Gen-1 / Kaiber style models  
- **Tool orchestration**  
  Calendar, grocery lists, home automation, and other household tasks.  
- **Authentication & security**  
  Google Workspace OAuth for access control.  

---

## Tech Stack

- **Backend:** Python + FastAPI  
- **Frontend:** TypeScript + Node + React  
- **LLM Runtime:** llama.cpp / Ollama  
- **Memory:** Qdrant / Chroma for semantic memory, SQLite/Postgres for structured memory  
- **Multi-modal Models:** Stable Diffusion, Coqui/Bark TTS, Gen-1 video  
- **Authentication:** Google OAuth 2.0  
- **Linting & Formatting:** Google Python style, `pyproject.toml`, ESLint/Prettier for TS

---

## Getting Started

1. Clone the repo  
2. Install Python dependencies (poetry / pip)  
3. Install Node dependencies for frontend  
4. Configure Google OAuth credentials  
5. Set up vector DB for memory  
6. Start backend + frontend servers  
