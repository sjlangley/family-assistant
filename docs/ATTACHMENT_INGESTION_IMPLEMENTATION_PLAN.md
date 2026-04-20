# Attachment Ingestion Implementation Plan

## Summary

This document defines the implementation plan for unified attachment support in
Family Assistant.

The goal is to add first-class conversation attachments for:

- native text files such as `.md`, `.txt`, `.json`, `.csv`
- image files such as `.png`, `.jpg`, `.webp`
- convertible document formats beginning with `.pdf`

The implementation must support immediate local-upload use cases while being
explicitly designed so future Google Drive ingestion can reuse the same
attachment model, extraction pipeline, and LLM integration.

The system should treat attachments as canonical conversation artifacts, not as
one-off prompt stuffing.

## Goals

- Let users attach files to a conversation turn and ask questions about them.
- Support text summarization and question answering over uploaded files.
- Support image attachments for vision-capable presets.
- Support PDF ingestion through extracted text.
- Keep storage, ingestion, and LLM-read flows source-agnostic so future Google
  Drive imports can reuse them.

## Non-Goals

- Building Google Drive integration in this phase
- Supporting every possible document format in the first release
- Creating a reusable user-wide document library in the first release
- Storing large uploaded binaries directly in PostgreSQL
- Implementing scanned PDF vision fallback in the first PDF slice

## Core design decisions

### Canonical attachment record

Every file becomes an `attachment` record regardless of where it came from.

Initial source:

- browser upload

Future sources:

- Google Drive
- other connectors

The canonical attachment row must therefore include source metadata from day
one, even if only local uploads are active initially.

### Separation of concerns

The implementation must separate:

- source acquisition
- attachment storage
- ingestion/extraction
- transcript linkage
- LLM access

This avoids hard-coding the system around browser uploads and lets future
Google Drive ingestion plug into the same internal pipeline after bytes are
acquired.

### Storage model

Use PostgreSQL as the canonical store for attachment metadata and small derived
artifacts.

Store original uploaded binaries on local disk behind a storage abstraction.

Do not store raw source binaries in PostgreSQL by default.

### LLM access model

Do not inject full file contents into the base conversation prompt by default.

Instead:

- include a compact attachment manifest in the prompt context
- expose bounded attachment-read tools for substantive content access
- use model-native vision payloads for image attachments where supported

This protects prompt budgets and scales better to larger files.

### Attachment scope

In the initial implementation, attachments are conversation-scoped artifacts.

They are persisted and reusable in later turns within the same conversation,
but they are not yet a cross-conversation user document library.

## Data model

### Attachment fields

The canonical `attachments` table should include fields equivalent to:

- `id`
- `conversation_id`
- `user_id`
- `message_id` or message-link join table
- `source_type`
- `source_ref`
- `source_version`
- `source_display_name`
- `original_filename`
- `mime_type`
- `byte_size`
- `kind`
- `ingestion_status`
- `storage_key`
- `preview_text`
- `extracted_text`
- `failure_reason`
- `deleted_at`
- `purge_after`
- `created_at`

### Source metadata

Source metadata must exist in the schema even if only local uploads are active.

Initial values:

- `source_type='upload'`
- `source_ref=null`
- `source_version=null`

This is required so future Google Drive files can flow through the same
attachment table with:

- `source_type='google_drive'`
- `source_ref=<drive file id>`
- `source_version=<drive revision/version>`

### Attachment kind

Supported kinds should be modeled explicitly:

- `text`
- `image`
- `document`

### Ingestion status

Supported statuses should include:

- `processing`
- `ready`
- `partial`
- `failed`

## Storage architecture

### Canonical storage

PostgreSQL stores:

- canonical metadata
- extracted text
- previews
- status
- lifecycle fields

Local filesystem storage stores:

- original source bytes
- optional derived binary artifacts such as rendered PDF page images later

### Storage abstraction

Introduce an `AttachmentStorage` abstraction with a local-disk implementation
first.

The abstraction should support operations like:

- `put`
- `get`/`open`
- `exists`
- `delete`

This keeps the implementation ready for future MinIO, S3, Azure Blob, or other
backends without forcing that complexity into the first release.

### Local storage layout

Use a deterministic layout partitioned by user and conversation, for example:

`<attachments_root>/<user_id>/<conversation_id>/<attachment_id>/...`

The exact path is internal and must never be exposed directly to the UI.

## Ingestion architecture

### Source-neutral ingestion seam

Define a source-neutral ingestion service that receives:

- conversation id
- user id
- source metadata
- filename
- MIME type
- byte stream or bytes

The ingestion service must not depend on FastAPI `UploadFile` directly.

Browser upload is only one acquisition adapter that converts incoming request
files into this internal ingestion request.

Future Google Drive ingestion should be able to call the same ingestion service
after downloading or exporting file bytes from Drive.

### Ingestion classes

#### Native text

For text-like files:

- validate MIME type and extension
- decode text
- normalize line endings
- generate preview text
- store extracted text directly
- mark attachment `ready`

#### Images

For image files:

- validate image type
- store source bytes
- persist metadata
- no text extraction required in the base path
- mark attachment `ready`

#### Convertible documents

For PDFs first:

- store source bytes
- mark attachment `processing`
- extract embedded text
- persist extracted text and preview
- transition to `ready`, `partial`, or `failed`

Later document types like `.docx`, `.pptx`, and `.xlsx` should follow the same
ingestion pattern.

## Conversation and transcript integration

### Message create APIs

Both create-conversation-with-message and add-message APIs should accept:

- `attachment_ids`

The backend must validate that referenced attachments:

- exist
- belong to the conversation
- belong to the current user
- are in a usable state where required

### Transcript read APIs

Transcript responses should include lightweight attachment summaries on user
messages.

The UI should receive only safe metadata such as:

- id
- filename
- kind
- MIME type
- source type
- status
- preview metadata where appropriate

Storage paths and internal file locations must not be exposed.

## LLM integration

### Attachment manifest

When a user turn includes attachments, conversation preparation should include
a compact manifest describing the available attachments.

The manifest should include:

- id
- filename
- kind
- MIME type
- size
- status
- short preview

### Bounded read tools

Add bounded attachment tools such as:

- `read_attachment_text`
- `read_attachment_pages`

These tools must operate on canonical attachment ids only.

They must not depend on whether the source file came from local upload or
Google Drive.

### Text attachment behavior

For text attachments:

- the model sees the manifest
- the model calls a bounded read tool when it needs substantive content
- the backend returns bounded content slices
- the model answers using that returned text

### Image attachment behavior

For image attachments:

- if the selected preset supports `vision`, the request adapter includes image
  inputs in the provider-specific multimodal request shape
- if the preset does not support `vision`, the backend rejects the image-backed
  request or the UI warns before send

### PDF behavior

For PDFs:

- if extracted text is ready, treat the PDF as a text-readable attachment via
  bounded tools
- scanned PDF fallback via rendered page images is intentionally deferred to a
  later phase

## Lifecycle and retention

### Default retention model

Attachments remain while the parent conversation exists.

When a conversation is deleted:

- linked attachments are soft-deleted
- `purge_after` is set
- a background cleanup process later removes binary artifacts and finalizes
  deletion

### Faster cleanup cases

Use shorter retention for:

- failed uploads
- incomplete uploads
- orphaned uploads never attached to a message

### Cleanup responsibilities

Cleanup must remove:

- source binary
- derived binary artifacts
- extracted text artifacts stored outside the canonical row if any

Cleanup must be idempotent and resilient to partially missing files.

## Relationship to future Google Drive ingestion

This design is intentionally structured so Google Drive integration becomes a
new source-acquisition layer, not a new document architecture.

Future Drive integration should add:

- provider auth and token handling
- Drive file discovery/import flows
- Drive export/download logic
- source identity and version tracking
- sync/reingestion logic

It should not need to replace:

- attachment schema
- storage abstraction
- extraction pipeline
- transcript linkage
- LLM attachment manifest
- attachment-read tools
- retention lifecycle

The guiding rule is:

Google Drive files should become canonical attachments and then follow the same
ingestion and LLM-read path as browser-uploaded files.

## Incremental implementation plan

### Step 1: Attachment schema and storage abstraction

Implement:

- attachment SQLModel and Pydantic types
- Alembic migration
- source fields
- storage abstraction
- local filesystem implementation
- storage and retention settings

Review boundary:

- no upload API
- no UI
- no LLM changes

### Step 2: Source-neutral ingestion service contract

Implement:

- internal ingestion request model
- `AttachmentIngestionService`
- tests using bytes or streams instead of framework upload objects

Review boundary:

- backend-only
- still no user-visible flow

### Step 3: Backend browser-upload adapter for text files

Implement:

- upload endpoint
- validation
- conversion from multipart upload to internal ingestion request
- `source_type='upload'`

Review boundary:

- local upload only
- text files only

### Step 4: Message linkage and transcript metadata

Implement:

- `attachment_ids` on message-create APIs
- backend validation
- message linkage persistence
- transcript attachment summaries

Review boundary:

- transcript behavior only
- still no LLM attachment use

### Step 5: Frontend local-upload UX

Implement:

- file picker
- upload-before-send flow
- attachment chips
- error handling
- transcript rendering

Review boundary:

- first user-visible end-to-end slice
- LLM still ignores attachments

### Step 6: Text attachment LLM integration

Implement:

- attachment manifest
- bounded text-read tool(s)
- tool-loop integration
- prompt guidance for using attachment tools

Review boundary:

- text attachments become fully usable for summary and Q&A

### Step 7: Image attachment support and vision gating

Implement:

- image upload validation
- image metadata persistence
- manifest support
- vision-capable request adapter path
- preset capability enforcement

Review boundary:

- images supported for vision-capable presets only

### Step 8: PDF embedded-text ingestion

Implement:

- PDF extraction path
- processing/ready/failed state handling
- page-aware read support

Review boundary:

- embedded-text PDFs only
- scanned-PDF fallback deferred

### Step 9: Drive-ready source identity hooks

Implement:

- source identity lookup by `source_type`, `source_ref`, `source_version`
- reingestion decision helpers
- duplicate/version-aware attachment-side hooks

Review boundary:

- no Google Drive connector yet
- backend future-proofing only

### Step 10: Retention and cleanup

Implement:

- soft delete
- purge scheduling
- background cleanup
- idempotent deletion of source and derived artifacts

Review boundary:

- lifecycle hardening only

### Step 11: UX polish and capability-aware messaging

Implement:

- better status chips
- clearer processing/failure states
- preset mismatch warnings
- wording that uses `attachments` or `files`, not only `uploads`

Review boundary:

- presentation and polish only

## Suggested PR breakdown

### PR 1

Attachment schema, source fields, storage abstraction

### PR 2

Source-neutral ingestion service contract

### PR 3

Backend browser-upload adapter for text files

### PR 4

Message linkage and transcript metadata

### PR 5

Frontend local-upload UX

### PR 6

Text attachment LLM integration

### PR 7

Image attachments and vision gating

### PR 8

PDF embedded-text ingestion

### PR 9

Drive-ready source identity hooks

### PR 10

Retention and cleanup

### PR 11

UX polish and capability-aware messaging

## Testing strategy

Each step should follow strict TDD:

- write a failing test first
- implement the minimum code to pass
- refactor while preserving passing tests

Testing should explicitly verify that provider-specific acquisition concerns do
not leak into:

- extraction
- transcript linkage
- LLM tools
- retention logic

The implementation should preserve this invariant:

A future Google Drive file should be able to become a canonical attachment and
then use the same downstream path as a browser-uploaded file.

## Validation requirements

If backend files are changed, run from `apps/assistant-backend`:

```bash
ruff format src/ tests/
ruff check src/ tests/
ruff format --check src/ tests/
pyrefly check src/
pytest -v
```

If frontend files are changed, run from `apps/assistant-ui`:

```bash
npm run format
npm run lint
npm run typecheck
npm run test:coverage
npm run build
```

## Assumptions and defaults

- Original uploaded binaries are stored on local disk.
- PostgreSQL stores metadata and small derived text artifacts.
- Attachments are conversation-scoped in the first implementation.
- Browser upload is the only live source initially.
- Google Drive support will later add a new acquisition path on top of the
  same canonical attachment and ingestion model.
