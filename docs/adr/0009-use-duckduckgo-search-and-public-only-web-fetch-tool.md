---
status: accepted
date: "2026-04-15"
supersedes: []
superseded_by:
---

# 0009. Use DuckDuckGo search and a public-only web fetch tool

## Context

Recorded retrospectively. The decision was made in #75 (2026-04-15), which added the `web_search`
and `web_fetch` tools to the tool layer from ADR 0008.

`web_search` (`services/tools/web_search.py`) queries DuckDuckGo through the `ddgs` library and
returns the results to the model. `web_fetch` (`services/tools/web_fetch.py`) downloads a page the
model names. Because the URL comes from the model, `web_fetch` refuses anything that is not a public
web page:

- only `http` and `https` URLs, with a hostname and no embedded credentials;
- no `localhost`, and no host that resolves to a private, loopback, link-local, multicast, reserved
  or unspecified address;
- redirects are followed by hand, at most 5, and each target is checked again;
- the response must be HTML, and the extracted content is cut to 2000 characters.

## Considered options

### DuckDuckGo through `ddgs`, with a guarded fetch tool

No alternatives are recorded as weighed at the time.

- Good: it works without an API key or an account, so the self-hosted stack stays zero-config.
- Bad: the search depends on the `ddgs` library continuing to work with DuckDuckGo.

## Decision

We will use DuckDuckGo, through the `ddgs` library, for `web_search`.

We will let `web_fetch` retrieve only public `http` and `https` pages, applying the checks above to
the first URL and to every redirect.

## Consequences

- Good: no key, no cost and no setup for the search tool.
- Good: a URL naming `localhost` or a private address, or redirecting to one, is refused, which
  protects the backend's own network (the containers for PostgreSQL and Chroma, for example).
- Bad: the address is checked, then `httpx` resolves the hostname again when it connects, so DNS
  rebinding can bypass the check (#136).
- Bad: only HTML is read, and only the first 2000 characters of the main content.
- The search provider may be replaced. A configurable SearXNG provider is proposed in #87 and #88,
  which are open.
