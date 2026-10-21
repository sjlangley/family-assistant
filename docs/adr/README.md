# Architecture Decision Records

Each file in this directory records one architecture decision: the context, the options considered,
the decision and its consequences. Accepted ADRs are in force. To change a decision, add a new ADR
that supersedes the old one. Do not edit an accepted ADR. `adr-check` enforces the format, and
[ADR 0001](0001-record-architecture-decisions-in-adrs-and-use-issues-for-specs.md) explains why the
repository uses ADRs.

All ADRs below are accepted. ADRs 0002 to 0017 were written retrospectively and carry the original
decision date.

- [0001](0001-record-architecture-decisions-in-adrs-and-use-issues-for-specs.md) Record architecture
  decisions in ADRs and use issues for specs
- [0002](0002-separate-fastapi-backend-and-react-vite-frontend-in-one-repository.md) Separate
  FastAPI backend and React Vite frontend in one repository
- [0003](0003-exchange-google-id-token-for-signed-session-cookie.md) Exchange a Google ID token for
  a signed session cookie
- [0004](0004-isolate-conversations-and-memory-per-user.md) Isolate conversations and memory per
  user
- [0005](0005-use-postgresql-as-source-of-truth-with-chroma-as-derived-index.md) Use PostgreSQL as
  source of truth with Chroma as a derived index
- [0006](0006-manage-schema-with-alembic-and-bootstrap-base-tables-at-startup.md) Manage schema with
  Alembic and bootstrap base tables at startup
- [0007](0007-use-local-openai-compatible-llm-runtime-behind-one-service-seam.md) Use a local
  OpenAI-compatible LLM runtime behind one service seam
- [0008](0008-use-native-model-tool-calls-with-allowlist-and-bounded-rounds.md) Use native model
  tool calls with an allowlist and bounded rounds
- [0009](0009-use-duckduckgo-search-and-public-only-web-fetch-tool.md) Use DuckDuckGo search and a
  public-only web fetch tool
- [0010](0010-store-memory-as-rolling-summary-and-durable-user-facts.md) Store memory as a rolling
  conversation summary and durable user facts
- [0011](0011-run-memory-extraction-as-in-process-background-tasks.md) Run memory extraction as
  in-process background tasks
- [0012](0012-assemble-prompt-context-within-fixed-count-budgets.md) Assemble prompt context within
  fixed count budgets
- [0013](0013-persist-trust-annotations-on-assistant-messages.md) Persist trust annotations on
  assistant messages
- [0014](0014-stream-replies-over-app-level-sse-protocol-on-existing-endpoints.md) Stream replies
  over an app-level SSE protocol on the existing endpoints
- [0015](0015-persist-user-message-immediately-and-assistant-message-at-stream-end.md) Persist the
  user message immediately and the assistant message at stream end
- [0016](0016-keep-reasoning-traces-separate-from-answers-and-out-of-later-prompts.md) Keep
  reasoning traces separate from answers and out of later prompts
- [0017](0017-release-each-app-independently-with-release-please.md) Release each app independently
  with release-please
- [0018](0018-group-dependabot-updates-while-keeping-major-versions-separate.md) Group Dependabot
  updates while keeping major versions separate
