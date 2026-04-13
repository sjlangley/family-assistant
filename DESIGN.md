# Design System — Family Assistant

## Product Context
- **What this is:** A self-hosted family AI assistant that combines local chat, durable memory, and controlled tools into a calmer, more trustworthy daily-use product.
- **Who it's for:** Household users first, including family members using the assistant for learning, everyday questions, and family-history research.
- **Space/industry:** Consumer AI assistant, local-first tooling, family knowledge management, research assistant.
- **Project type:** Web app.

## Aesthetic Direction
- **Direction:** Archive modern.
- **Decoration level:** Intentional, low.
- **Mood:** Calm, credible, warm, and inspectable. The product should feel like a personal archive you can talk to, not a flashy AI startup demo and not a server dashboard.
- **Reference sites:** [OpenAI ChatGPT Search](https://openai.com/index/introducing-chatgpt-search/), [Perplexity Help Center](https://www.perplexity.ai/help-center/en/articles/10352155-what-is-perplexity), [NotebookLM](https://blog.google/innovation-and-ai/products/notebooklm-beginner-tips/), [Open WebUI](https://github.com/open-webui/open-webui)

## Core Principles
- Keep the chat transcript as the primary workspace.
- Put proof next to the answer it explains.
- Treat sources, tool use, and memory as factual instrumentation, not decorative badges.
- Use warmth in surfaces and typography, not in clutter.
- Avoid generic AI product tropes: purple gradients, glossy card grids, icon soup, and overexcited copy.

## Typography
- **Display/Hero:** `Instrument Serif`
  - Use for welcome states, empty states, section titles, and rare emphasis moments.
  - Rationale: adds memory, gravity, and a slightly archival tone without turning the UI ornate.
- **Body:** `Instrument Sans`
  - Use for transcript text, controls, settings, helper copy, and all standard interface language.
  - Rationale: highly readable, contemporary, and neutral enough to support long conversations.
- **UI/Labels:** `Instrument Sans`
  - Use semibold for section labels, buttons, tabs, and headings inside the app shell.
- **Data/Tables:** `IBM Plex Mono`
  - Use for timestamps, trust metadata rows, source counts, model/tool labels, and compact structured data.
  - Rationale: makes evidence feel factual and inspectable.
- **Code:** `IBM Plex Mono`
- **Loading:** Google Fonts or self-hosted equivalent in production.

### Type Scale
- `display-xl`: 72px / 1.0 / `Instrument Serif`
- `display-lg`: 56px / 1.02 / `Instrument Serif`
- `display-md`: 40px / 1.05 / `Instrument Serif`
- `heading-lg`: 32px / 1.1 / `Instrument Serif`
- `heading-md`: 24px / 1.15 / `Instrument Sans`
- `heading-sm`: 18px / 1.2 / `Instrument Sans`
- `body-lg`: 18px / 1.55 / `Instrument Sans`
- `body-md`: 16px / 1.55 / `Instrument Sans`
- `body-sm`: 14px / 1.5 / `Instrument Sans`
- `meta`: 12px / 1.4 / `IBM Plex Mono`

## Color
- **Approach:** Restrained, warm-neutral, one grounded accent.
- **Primary:** `#24453A`
  - Meaning: trust, steadiness, grounded capability.
  - Usage: primary actions, active states, focused controls, key highlights.
- **Secondary:** `#B86A3E`
  - Meaning: warmth, human context, subtle emphasis.
  - Usage: rare highlights, supporting emphasis, secondary accents.
- **Neutrals:**
  - `#FBF8F2` paper surface
  - `#F6F2EA` parchment canvas
  - `#F0E8DA` raised surface
  - `#DED6C7` soft border
  - `#C9BFAE` strong border
  - `#6E675D` muted text
  - `#1F1C18` primary ink
- **Semantic:**
  - success `#2F6B53`
  - warning `#A36A2B`
  - error `#A54034`
  - info `#315C85`

### Dark Mode
- Keep the same hierarchy, but redesign surfaces rather than inverting blindly.
- Use near-black warm surfaces, not blue-black.
- Reduce accent saturation by roughly 10 to 20 percent so the product stays calm.
- Preserve mono metadata legibility and semantic contrast.

## Spacing
- **Base unit:** 8px
- **Density:** Comfortable
- **Scale:** `2xs 4px`, `xs 8px`, `sm 12px`, `md 16px`, `lg 24px`, `xl 32px`, `2xl 48px`, `3xl 64px`

## Layout
- **Approach:** Grid-disciplined app shell.
- **Primary shell:** left conversation rail, central transcript workspace, optional right-side details drawer or inline expansion.
- **Grid:** 12-column desktop, 8-column tablet, 4-column mobile.
- **Max content width:** 1240px overall shell, 760px ideal transcript reading width.
- **Border radius:**
  - small `8px`
  - medium `14px`
  - large `20px`
  - pill `9999px`

### Screen Structure
- Left rail: conversations and a few grounded starter prompts.
- Main transcript: message flow, in-thread status placeholder, composer.
- Evidence layer: compact metadata row directly below assistant answers, richer details in a drawer or expander.
- Settings/admin screens: same surfaces, same spacing, same restrained hierarchy. No alternate visual language.

## Component Guidance

### Message Bubbles
- User messages use the primary accent fill with light text.
- Assistant messages sit on raised neutral surfaces with a visible border.
- Error assistant messages use semantic error styling, but keep the same overall component shape.

### Trust Metadata Row
- Lives directly under assistant answers.
- Uses mono labels and low-chroma styling.
- Default items:
  - tool used
  - source count
  - memory hit count
- Never style these like celebratory feature badges.

### Drawer / Expander
- Open only when the user asks for more proof.
- Use for source detail, memory provenance, tool detail, and partial-confidence notes.
- Treat this as secondary context, not a permanent dashboard.

### Empty State
- One sentence explaining the trust model in plain language.
- Offer 2 to 3 concrete starter prompts tied to learning and family research.
- Use `Instrument Serif` only for the main welcome line, not for every line of copy.

### Loading State
- Use a single in-thread assistant placeholder.
- Status copy should change based on real stages when available:
  - `Thinking`
  - `Searching the web`
  - `Writing answer`
- Avoid spinner-only waiting states.

### Error State
- Preserve the user’s last message and conversation context.
- Use clear language that says what failed and what did not.
- Good example: “Web search failed, but your conversation is still intact.”

## Motion
- **Approach:** Minimal-functional.
- **Easing:** enter `ease-out`, exit `ease-in`, move `ease-in-out`
- **Duration:**
  - micro `50ms to 100ms`
  - short `150ms to 250ms`
  - medium `250ms to 400ms`
  - long `400ms to 700ms`

### Motion Rules
- Motion should clarify state changes, not decorate the app.
- Safe uses:
  - assistant placeholder entering the transcript
  - trust row expanding into details
  - drawer opening and closing
  - subtle active-state shifts in the conversation rail
- Avoid scroll-driven effects, floating ornament, or flashy tool-call animations.

## Responsive Behavior
- **Mobile:**
  - Collapse the conversation rail behind a clear top-level trigger.
  - Keep the transcript full-width with comfortable message margins.
  - Trust metadata remains directly under the answer and wraps to multiple lines if needed.
  - Details drawer becomes a bottom sheet or full-screen detail view.
- **Tablet:**
  - Prefer left rail + main transcript.
  - Show details inline rather than a permanent third column unless space clearly allows it.
- **Desktop:**
  - Use the full three-zone layout only when there is enough width for readable transcript lines.

## Accessibility
- Minimum touch target: `44px`
- All semantic colors must pass accessible contrast on both light and dark themes.
- Keyboard navigation must support:
  - conversation switching
  - composer interaction
  - trust row focus
  - opening and closing detail panels
- Use clear ARIA labels for tool/source/memory detail toggles.
- Never rely on color alone to communicate confidence, error, or provenance.

## Copy Tone
- Calm, direct, plain English.
- No hype language.
- No “AI magic” phrasing.
- Prefer:
  - “I found 2 sources”
  - “This detail conflicts with saved memory”
  - “I’m searching the web”
- Avoid:
  - “Unlock powerful insights”
  - “Smart memory engine”
  - “Seamless AI workflow”

## Anti-Patterns
- Purple or blue-purple gradient branding.
- Decorative card mosaics as the main screen structure.
- Colorful source/tool badges that look like marketing stickers.
- Overusing serif text inside dense app surfaces.
- Centering everything.
- Uniform large-radius bubbly UI.
- Generic “clean modern AI app” defaults with no point of view.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-13 | Adopted the `archive modern` design direction | It best fits a trustworthy assistant for learning and family research. |
| 2026-04-13 | Chose `Instrument Serif`, `Instrument Sans`, and `IBM Plex Mono` | This combination balances warmth, legibility, and factual UI instrumentation. |
| 2026-04-13 | Chose a warm neutral palette with moss accent and clay secondary | It avoids generic AI visuals and better supports the product’s memory and archive feel. |
| 2026-04-13 | Kept proof attached to each answer instead of moving it to a separate debug screen | Trust should live where the user makes meaning. |
