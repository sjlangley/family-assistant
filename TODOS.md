# TODOs

## Phase 1.5 image generation tool after web-search tool pipeline is stable

What:
Add an image-generation tool as the next tool integration after the phase 1 memory spine and `web_search` tool are stable.

Why:
The approved design intentionally reduced phase 1 to memory + one read-only tool to avoid breadth-first sprawl. Image generation is still part of the product vision, but it should reuse the same tool-calling, annotation, and trust contract instead of being built as a parallel special case.

Pros:
- Reuses the exact tool architecture proved by `web_search`
- Expands the assistant toward the original sovereign ChatGPT replacement vision
- Gives the product a creative capability without reopening the phase 1 architecture decisions

Cons:
- Adds another external/local model integration to configure and test
- Increases UI complexity if artifacts or previews are introduced
- Not necessary to validate the memory spine

Context:
This was explicitly deferred during `/plan-eng-review` after scope reduction. Phase 1 was narrowed to prompt assembly, canonical Postgres-backed summaries and durable facts, model-native tool calling, and structured response annotations. Image generation is phase 1.5, not phase 1, because the tool pipeline should be proven first with a simpler read-only tool.

Depends on / blocked by:
- Phase 1 memory spine complete
- `web_search` tool path stable
- Structured message annotations landed

## Phase 2 Google Drive genealogy ingestion + cited research answers + WikiTree photo prep

What:
Add the first domain wedge on top of the assistant core: Google Drive ingestion for genealogy material, source-grounded research answers, and photo triage/cleanup support for WikiTree publishing.

Why:
This is the sharpest real user job the approved design is supposed to serve. Without it, the repo risks drifting into a generic local assistant instead of proving itself on the builder's actual archive/research workflow.

Pros:
- Delivers the strongest personal value in the whole product direction
- Forces the provenance model to prove itself on real source material
- Creates a clear differentiator beyond “local ChatGPT clone”

Cons:
- Requires connector/indexing work plus domain-specific UX
- Increases scope substantially if attempted before phase 1 is trustworthy
- May expose gaps in provenance, artifact handling, and memory confirmation flows

Context:
This was intentionally deferred during `/office-hours` and confirmed again in `/plan-eng-review`. The product sequence is: first build a trustworthy assistant core with context compression, durable fact memory, structured annotations, and one controlled tool. Then use genealogy over Google Drive as the first serious proving ground.

Depends on / blocked by:
- Canonical durable fact storage in Postgres
- Summary + fact prompt assembly complete
- Structured annotations for sources/tool usage complete
- Phase 1 stable enough that trust issues are not conflated with ingestion issues

## Post-implementation visual QA for dark mode, mobile transcript layout, and evidence panels

What:
Run a focused design QA pass after the first implementation of the trustworthy assistant UI lands, specifically checking dark mode, mobile transcript spacing, and the bottom-sheet or detail-panel evidence flow.

Why:
These are the parts most likely to drift between a good plan and a slightly awkward shipped interface. They depend on real CSS, real content lengths, and real interaction timing.

Pros:
- Catches visual trust regressions before they become “the product feels off”
- Validates that responsive and accessibility decisions survived implementation
- Gives the new design system a concrete enforcement pass instead of leaving it aspirational

Cons:
- Adds a follow-up review step before calling the UI truly polished
- May produce a few rounds of cleanup work after the first implementation

Context:
This was explicitly identified during `/plan-design-review` after the design system was created in `DESIGN.md` and the plan locked in mobile hierarchy, polite live-region announcements, message-level proof rows, and evidence-panel behavior. The plan is strong, but these interaction details still need a visual pass in the real product.

Depends on / blocked by:
- Initial implementation of the phase 1 trustworthy assistant UI
- Dark mode and responsive layouts present in the built frontend
