# Prompt Token Reduction Plan

## Summary

This document explains how we can reduce the number of tokens sent to the
language model without losing useful context, and outlines a practical plan to
implement that work later.

It is written for readers who may understand the backend architecture but do
not already know how token counting or prompt compression works.

## What Token Compression Means

Large language models do not read text the way humans do. Before a prompt is
processed, the model turns it into smaller pieces called tokens. Some words
become one token, some become several, and message formatting also consumes
tokens.

When we talk about token compression, we are really talking about two separate
steps:

1. Measuring how large a prompt is in tokens.
2. Reducing the number of tokens we send while keeping the meaning we need.

These are related, but they are not the same thing.

## Tokenization Measures Size

Tokenization is the step that tells us how big a prompt is. It is a
measurement tool, not a compression tool.

In this system, the backend would build the candidate prompt first. Then it
would run that prompt through a tokenizer locally to estimate or calculate how
many tokens the model will see. This happens in our application before the
request is sent to the model.

That means we are not asking the model to tokenize the prompt for us. There is
no extra model call just to count tokens. We do the counting locally, use it
to make decisions, and then send the final prompt once.

A simple way to think about it is:

- tokenization is the ruler
- compression is the scissors

The ruler tells us the size. The scissors decide what to cut.

## Compression Reduces Size

If the prompt is larger than we want, or if we see obvious waste, we reduce it
by changing what we send.

That can include:

- keeping fewer recent turns verbatim
- replacing older turns with a rolling summary
- removing duplicate or overlapping durable facts
- rewriting summaries and facts into denser forms
- removing verbose labels or prompt scaffolding
- optionally making fixed instruction text terser

This is the part that actually lowers token usage.

## Why We Still Need Measurement

Even if we want to reduce waste by default, measurement still matters.

Without token counting, we do not know:

- which parts of the prompt are consuming the budget
- whether a compression step helped enough
- whether the prompt still fits safely within the target budget
- when we can stop compressing and preserve more detail

The intended flow is:

1. Build the candidate prompt.
2. Measure it locally in tokens.
3. Reduce low-value content if needed.
4. Measure again.
5. Send the final prompt.

## What We Should Always Reduce

We should reduce low-value tokens whenever we can, even if we are not near a
hard limit.

Examples include:

- repeated boilerplate
- irrelevant old turns
- overlapping facts
- wordy section labels
- summaries that say more than they need to

This is safe optimization. It lowers cost and usually improves focus.

## What We Should Protect

We should not reduce high-value context just because it is large.

Examples include:

- the user's latest request
- the immediately relevant prior exchange
- facts the answer depends on
- tool output or evidence needed for the response

The goal is not to make the prompt as small as possible. The goal is to remove
waste while preserving signal.

## How This Applies To This Repository

In this repository, the main opportunity is not the transport layer. The main
opportunity is prompt assembly.

`ContextAssemblyService` already decides which summaries, facts, and recent
turns are included. That makes it the right place to:

- measure prompt size
- identify which sections are expensive
- compress or omit low-value context
- preserve the most relevant context verbatim

`LLMService` should continue to send only the final prepared messages.

## Where Caveman Fits

[`caveman`](https://github.com/juliusbrussee/caveman) can help make fixed
prompt text or model outputs terser, but it does not replace context selection
or memory compression.

That means it may be useful for:

- compressing static system instructions
- compressing extraction prompt text
- optionally making assistant replies terser

It should not be the primary strategy for deciding which conversation history
or memory to include.

## Proposed Implementation

### 1. Add Prompt-Budget Instrumentation

Add prompt-budget instrumentation to the conversation path so each LLM call can
report approximate size by section:

- system prompt
- memory summary
- durable facts
- recent turns
- new user message
- tool-related context, if present

This gives us visibility into where tokens are actually going.

### 2. Optimize Dynamic Prompt Content

Refactor context assembly to optimize dynamic prompt content directly:

- replace fixed-count history inclusion with adaptive selection
- keep the newest exchange verbatim
- prefer turns referenced by the latest user message
- prefer turns overlapping with selected fact subjects
- treat the saved summary as the canonical representation of older turns once
  present

### 3. Tighten Memory Payloads

Shorten memory payloads before they reach the LLM:

- rewrite conversation summaries toward state-oriented summaries instead of
  narrative recap
- normalize durable facts into short atomic statements
- deduplicate overlapping facts by subject or content before inclusion
- reduce default fact count when relevance is weak

### 4. Compress Prompt Formatting

Reduce prompt overhead created by formatting itself:

- merge summary and facts into one compact memory block when possible
- remove verbose labels and prose wrappers that do not add model value
- keep content semantically equivalent while using denser formatting

### 5. Add Optional Caveman Layer

Use `caveman` only as an optional secondary layer for static or semi-static
text:

- compress the fixed system prompt if benchmarks show no regression
- evaluate use for the background extraction prompt
- optionally support terse assistant-output mode as a product choice

Do not use `caveman` for dynamic conversation history selection or durable
memory retrieval. Those remain owned by custom backend logic.

## Recommended Scope

The current recommendation is:

- keep prompt assembly custom and lightweight
- add local token measurement using the serving model's tokenizer where
  feasible
- improve summary and fact compaction in our own code
- treat `caveman` as optional and low-blast-radius

This keeps the architecture aligned with the existing backend instead of
pulling in a large framework for a narrow problem.

## Background Reading

These references are useful for understanding existing techniques without
implying that we should adopt all of them.

### Model-Native Token Counting

Use the model's own tokenizer and chat template to estimate prompt size
accurately for non-GPT models such as Qwen.

- Hugging Face Transformers chat templating:
  [chat_templating.md](https://github.com/huggingface/transformers/blob/main/docs/source/en/chat_templating.md)
- Hugging Face Transformers Qwen examples:
  [qwen2.md](https://github.com/huggingface/transformers/blob/main/docs/source/en/model_doc/qwen2.md)

### GPT-Oriented Token Counting

`tiktoken` is a good reference for local token counting concepts and
OpenAI-style chat-message accounting, even though it is not the ground-truth
tokenizer for Qwen.

- OpenAI `tiktoken`:
  [Context7 reference](https://context7.com/openai/tiktoken/llms.txt)

### Rolling Summary Middleware

LangChain provides a reference implementation of token-triggered chat-history
summarization that keeps the latest messages verbatim while compressing older
context.

- LangChain short-term memory:
  [short-term-memory](https://docs.langchain.com/oss/python/langchain/short-term-memory)
- LangChain context engineering:
  [context-engineering](https://docs.langchain.com/oss/python/langchain/context-engineering)

### Summary-Backed Memory Buffers

LlamaIndex provides examples of token-limited memory buffers and
summary-backed chat-history retention.

- LlamaIndex memory buffer:
  [memory.ipynb](https://github.com/run-llama/llama_index/blob/main/docs/examples/memory/memory.ipynb)
- LlamaIndex summary memory buffer:
  [ChatSummaryMemoryBuffer.ipynb](https://github.com/run-llama/llama_index/blob/main/docs/examples/memory/ChatSummaryMemoryBuffer.ipynb)

### Static Prompt And Output Terseness

`caveman` is a useful reference for terse static prompt and output compression.
It is best treated as a secondary technique rather than the main
conversation-memory strategy.

- Caveman:
  [github.com/juliusbrussee/caveman](https://github.com/juliusbrussee/caveman)

We are using these as background reading and technique references, not as an
automatic adoption decision.

## Validation And Success Criteria

The implementation should be considered successful if it:

- reduces prompt tokens meaningfully for typical conversation requests
- preserves answer quality and memory recall
- keeps the newest high-signal context intact
- avoids unnecessary framework complexity
- makes prompt cost easier to observe and debug
