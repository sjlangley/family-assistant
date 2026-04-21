# Changelog

## [0.1.1](https://github.com/sjlangley/family-assistant/compare/assistant-backend-v0.1.0...assistant-backend-v0.1.1) (2026-04-21)


### Bug Fixes

* **backend:** avoid expired conversation loads in streams ([#116](https://github.com/sjlangley/family-assistant/issues/116)) ([4e97318](https://github.com/sjlangley/family-assistant/commit/4e97318b301577b392d9278d679ab87647091902))

## [0.1.0](https://github.com/sjlangley/family-assistant/compare/assistant-backend-v0.0.1...assistant-backend-v0.1.0) (2026-04-21)


### Features

* Add annotations field to ConversationMessage ([#57](https://github.com/sjlangley/family-assistant/issues/57)) ([f555f39](https://github.com/sjlangley/family-assistant/commit/f555f390f67e36a5578fe87a21a88bb99af8bc0f))
* add authenticated chat UI with system prompt ([#26](https://github.com/sjlangley/family-assistant/issues/26)) ([e5542fe](https://github.com/sjlangley/family-assistant/commit/e5542fecc7d94f07bacad7bff27a764a8b8e68e1))
* add chat completions endpoint with LLM backend integration ([#24](https://github.com/sjlangley/family-assistant/issues/24)) ([0487d76](https://github.com/sjlangley/family-assistant/commit/0487d76e3787caf4239b6e58488461b86060c2bb))
* add conversation management with database persistence ([#36](https://github.com/sjlangley/family-assistant/issues/36)) ([f8abd9b](https://github.com/sjlangley/family-assistant/commit/f8abd9b84f69e3453ef2a5df5a6ab1b6debd9876))
* add conversation support to the UI ([#37](https://github.com/sjlangley/family-assistant/issues/37)) ([36dd86d](https://github.com/sjlangley/family-assistant/commit/36dd86df8d33f8ad95642a454e088bcc804e97b3))
* **assistant-backend:** implement streaming conversation lifecycle persistence ([#106](https://github.com/sjlangley/family-assistant/issues/106)) ([3f7213a](https://github.com/sjlangley/family-assistant/commit/3f7213a581601dfb233dc4f0fca7eed75d010297))
* **assistant:** add token-limit handling and truncation recovery ([#112](https://github.com/sjlangley/family-assistant/issues/112)) ([73acdef](https://github.com/sjlangley/family-assistant/commit/73acdef13fe811d4cc7cb57507ba87fc4405e000))
* **backend:** Add ContextAssemblyService for bounded prompt assembly (Phase 1, Step 3) ([#71](https://github.com/sjlangley/family-assistant/issues/71)) ([9ac3f32](https://github.com/sjlangley/family-assistant/commit/9ac3f32a7081a1e9621f862f007217be584e3067))
* **backend:** add initial tool layer and current time tool ([#73](https://github.com/sjlangley/family-assistant/issues/73)) ([ba92ce2](https://github.com/sjlangley/family-assistant/commit/ba92ce24ce9f1a34c1ce333aa285dcf4093bbd99))
* **backend:** add streaming response models and parser (Phase 1) ([#99](https://github.com/sjlangley/family-assistant/issues/99)) ([50ea3df](https://github.com/sjlangley/family-assistant/commit/50ea3df82725822d5c3376ba44d2c1cc5485c7f2))
* **backend:** AssistantAnnotationService for structured conversation annotations ([#77](https://github.com/sjlangley/family-assistant/issues/77)) ([cee9a71](https://github.com/sjlangley/family-assistant/commit/cee9a7136d62455df4f9a9b06619bfe65c0b268c))
* **backend:** Complete Alembic migration infrastructure ([#67](https://github.com/sjlangley/family-assistant/issues/67)) ([aa99602](https://github.com/sjlangley/family-assistant/commit/aa99602ee515798ad83e743ebf095a32615d88f8))
* **backend:** implement SSEEncoder and debug streaming endpoint (Phase 3) ([#103](https://github.com/sjlangley/family-assistant/issues/103)) ([88152a1](https://github.com/sjlangley/family-assistant/commit/88152a118e55e75c9ccf5e5b1efcd4955110cebf))
* **backend:** implement stream_messages generator in LLMService (Phase 2) ([#102](https://github.com/sjlangley/family-assistant/issues/102)) ([1f46c9a](https://github.com/sjlangley/family-assistant/commit/1f46c9a45ca9622e1a9bd7c73dddfbef1dc4db22))
* **backend:** Implement web search and fetch tools with security validation ([#75](https://github.com/sjlangley/family-assistant/issues/75)) ([a0b0661](https://github.com/sjlangley/family-assistant/commit/a0b0661622e93451fc8d701cb8e762df18dede09))
* implement authentication and session management ([#4](https://github.com/sjlangley/family-assistant/issues/4)) ([f196654](https://github.com/sjlangley/family-assistant/commit/f196654bd361b75f990997861ec3c1a5fe6d709d))
* initial implmentation of a vector memory store ([#43](https://github.com/sjlangley/family-assistant/issues/43)) ([51ffa52](https://github.com/sjlangley/family-assistant/commit/51ffa525a14e3b005155f925d7dafaf8a108e77c))
* Step 6 — Surface truthful memory_saved annotations from background extraction ([#80](https://github.com/sjlangley/family-assistant/issues/80)) ([dc0296f](https://github.com/sjlangley/family-assistant/commit/dc0296fe84db53584170da346d266db31fb63037))
* **streaming:** add stop control for active responses ([#113](https://github.com/sjlangley/family-assistant/issues/113)) ([ff9e4b7](https://github.com/sjlangley/family-assistant/commit/ff9e4b79ddd576632d60b6d292f3517835ee0be1))
* **ui:** implement useStreamingConversation hook and SSE client (Phase 4) ([#104](https://github.com/sjlangley/family-assistant/issues/104)) ([946fc1b](https://github.com/sjlangley/family-assistant/commit/946fc1ba9436d7567ba71f391c0ee5dbd2306c60))


### Bug Fixes

* **backend:** switch local tool runtime to Ollama ([#74](https://github.com/sjlangley/family-assistant/issues/74)) ([10e7fff](https://github.com/sjlangley/family-assistant/commit/10e7fff8176b53b2895469e5f689194ca0a330bd))
* update prompt to suggest using tools ([#76](https://github.com/sjlangley/family-assistant/issues/76)) ([b994e4c](https://github.com/sjlangley/family-assistant/commit/b994e4c41d1b5f92fc45aae353477535ff6f4ec1))


### Documentation

* Streaming Responses PRD and design ([#95](https://github.com/sjlangley/family-assistant/issues/95)) ([bc3e162](https://github.com/sjlangley/family-assistant/commit/bc3e162d0e0f4abbc2761d9b69350f7debc2b924))
* sync shipped assistant docs ([#89](https://github.com/sjlangley/family-assistant/issues/89)) ([4d87e61](https://github.com/sjlangley/family-assistant/commit/4d87e61c449b44f7f069e0868a4d1bdf77011244))
* update all READMEs to reflect current implementation ([#39](https://github.com/sjlangley/family-assistant/issues/39)) ([e1baa83](https://github.com/sjlangley/family-assistant/commit/e1baa83b73f2b0bb31bb7b09d2c9f73ebaadc7a4))
