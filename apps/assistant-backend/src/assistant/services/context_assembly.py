"""Context assembly for conversation LLM calls.

Prepares the final message list using:
- Recent conversation turns (canonical Postgres)
- Latest conversation summary (canonical Postgres)
- Durable facts for the current user (canonical Postgres)

Postgres remains the authoritative source for all injected context.
Chroma may assist with ranking durable facts for new conversations.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.models.conversation_sql import Message
from assistant.models.memory_sql import ConversationMemorySummary, DurableFact

if TYPE_CHECKING:
    from assistant.services.memory_storage import (
        MemoryStorage,
    )

logger = logging.getLogger(__name__)

# Explicit prompt budget constants
MAX_RECENT_MESSAGES_WITH_SUMMARY = 4  # Last N messages when summary exists
MAX_RECENT_MESSAGES_NO_SUMMARY = 8  # Last N messages when no summary
MAX_DURABLE_FACTS = 5  # Maximum number of facts to include in prompt
MAX_FACT_CANDIDATES = (
    15  # Pool of candidates to rank from (used by relevance selection)
)
MAX_FACT_TEXT_LENGTH = 200  # Truncate individual fact text
MAX_SUMMARY_TEXT_LENGTH = 1000  # Truncate summary text


@dataclass
class ContextAssemblyResult:
    """Result of context assembly."""

    messages: list[dict]  # Final prepared message list for LLM
    used_summary: bool  # Whether a saved summary was used
    summary_id: uuid.UUID | None  # ID of the summary if used
    fact_ids: list[uuid.UUID]  # IDs of durable facts included
    candidate_fact_ids: list[uuid.UUID] = field(
        default_factory=list
    )  # All candidate facts considered
    selection_method: str = 'recency'  # How facts were selected: 'relevance', 'recency', or 'chroma'


class ContextAssemblyService:
    """Assembles context for conversation LLM calls from Postgres.

    Responsibilities:
    - Load recent conversation turns from Postgres
    - Load latest conversation summary from Postgres
    - Load active durable facts for user from Postgres
    - Apply explicit prompt budgets
    - Return prepared message list

    Postgres is the canonical source of truth for all memory data.
    Chroma can assist with retrieval/ranking, but Postgres remains canonical.
    """

    def __init__(self, memory_storage: 'MemoryStorage | None' = None) -> None:
        """Initialize ContextAssemblyService.

        Args:
            memory_storage: Optional MemoryStorage for Chroma-assisted ranking
                           when assembling new-conversation durable facts
        """
        self.memory_storage = memory_storage

    async def assemble_context(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        conversation_id: uuid.UUID,
        new_user_message: str | None,
    ) -> ContextAssemblyResult:
        """Assemble context for an existing conversation.

        Loads summary, facts, and recent turns, then builds the final
        message list within budget constraints.

        The fact selection uses relevance-based ranking when recent turns
        are available: facts whose subjects appear in the recent messages
        are preferred over purely recency-based selection.

        Args:
            session: Database session
            user_id: Current user ID
            conversation_id: Conversation to assemble context for
            new_user_message: The new user message being added (None if
                already persisted in database)

        Returns:
            ContextAssemblyResult with prepared messages and metadata
        """
        # Load latest summary for this conversation
        summary = await self._load_latest_summary(
            session, conversation_id=conversation_id
        )

        # Load recent conversation turns FIRST (needed for relevance ranking)
        recent_turns = await self._load_recent_turns(
            session,
            conversation_id=conversation_id,
            max_turns=(
                MAX_RECENT_MESSAGES_WITH_SUMMARY
                if summary
                else MAX_RECENT_MESSAGES_NO_SUMMARY
            ),
        )

        # Load active durable facts with relevance ranking
        facts, selection_method = await self._load_active_facts(
            session, user_id=user_id, recent_turns=recent_turns
        )

        # Build final message list
        messages = self._build_message_list(
            summary=summary,
            facts=facts,
            recent_turns=recent_turns,
            new_user_message=new_user_message,
        )

        return ContextAssemblyResult(
            messages=messages,
            used_summary=summary is not None,
            summary_id=summary.id if summary else None,
            fact_ids=[f.id for f in facts],
            candidate_fact_ids=[],  # Not tracked in existing conversations for now
            selection_method=selection_method,
        )

    async def assemble_context_new_conversation(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        user_message: str,
    ) -> ContextAssemblyResult:
        """Assemble context for a new conversation (first message).

        No summary or history exists yet, but we can include durable facts.
        When Chroma is available, durable facts are ranked semantically against
        the new user message and then reloaded from canonical Postgres rows.

        Args:
            session: Database session
            user_id: Current user ID
            user_message: The first user message

        Returns:
            ContextAssemblyResult with prepared messages and metadata
        """
        (
            facts,
            candidate_fact_ids,
            selection_method,
        ) = await self._load_new_conversation_facts(
            session,
            user_id=user_id,
            user_message=user_message,
        )

        # Build message list with just facts and the new user message
        messages = self._build_message_list(
            summary=None,
            facts=facts,
            recent_turns=[],
            new_user_message=user_message,
        )

        return ContextAssemblyResult(
            messages=messages,
            used_summary=False,
            summary_id=None,
            fact_ids=[f.id for f in facts],
            candidate_fact_ids=candidate_fact_ids,
            selection_method=selection_method,
        )

    async def _load_new_conversation_facts(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        user_message: str,
    ) -> tuple[list[DurableFact], list[uuid.UUID], str]:
        """Load durable facts for a brand-new conversation.

        Prefer Chroma-ranked durable fact candidates when available, but always
        reload the actual facts from canonical Postgres before prompt assembly.
        If Chroma returns nothing or fails, fall back to recency-based loading.
        """
        if self.memory_storage is not None:
            try:
                candidates = self.memory_storage.query_durable_fact_candidates(
                    user_id=user_id,
                    query=user_message,
                    n_results=MAX_FACT_CANDIDATES,
                )
            except Exception:
                logger.warning(
                    'Falling back to recency for new-conversation facts after '
                    'Chroma retrieval failed',
                    exc_info=True,
                )
            else:
                logger.debug(
                    'Chroma returned %s durable fact candidates for new '
                    'conversation user_id=%s',
                    len(candidates),
                    user_id,
                )
                candidate_fact_ids = self._dedupe_fact_ids(
                    [candidate.fact_id for candidate in candidates]
                )
                logger.debug(
                    'Deduped Chroma durable fact candidates down to %s ids for '
                    'user_id=%s',
                    len(candidate_fact_ids),
                    user_id,
                )
                if candidate_fact_ids:
                    facts = await self._load_facts_by_ranked_ids(
                        session,
                        user_id=user_id,
                        ranked_fact_ids=candidate_fact_ids,
                    )
                    if facts:
                        logger.debug(
                            'Using %s Postgres-backed durable facts from '
                            'Chroma ranking for user_id=%s',
                            min(len(facts), MAX_DURABLE_FACTS),
                            user_id,
                        )
                        return (
                            facts[:MAX_DURABLE_FACTS],
                            candidate_fact_ids,
                            'chroma',
                        )
                    logger.debug(
                        'Chroma returned candidate ids but no active Postgres '
                        'facts were reloadable for user_id=%s; falling back to '
                        'recency',
                        user_id,
                    )
                else:
                    logger.debug(
                        'Chroma returned no durable fact candidate ids for '
                        'user_id=%s; falling back to recency',
                        user_id,
                    )

        facts, selection_method = await self._load_active_facts(
            session, user_id=user_id, recent_turns=None
        )
        logger.debug(
            'Using %s durable facts via %s fallback for new conversation '
            'user_id=%s',
            len(facts),
            selection_method,
            user_id,
        )
        return facts, [], selection_method

    async def _load_latest_summary(
        self,
        session: AsyncSession,
        *,
        conversation_id: uuid.UUID,
    ) -> ConversationMemorySummary | None:
        """Load the latest summary for a conversation."""
        stmt = (
            select(ConversationMemorySummary)
            .where(
                # pyrefly: ignore [bad-argument-type]
                ConversationMemorySummary.conversation_id == conversation_id
            )
            # pyrefly: ignore [missing-attribute]
            .order_by(ConversationMemorySummary.version.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_active_facts(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        recent_turns: list[Message] | None = None,
    ) -> tuple[list[DurableFact], str]:
        """Load active durable facts for a user, ranked by relevance if possible.

        Selection strategy:
        1. Load recent candidates (ordered by updated_at DESC)
        2. If recent_turns provided, rank by relevance to the conversation
           - Preferred: facts whose subjects have any word appearing in recent content
           - Fallback: facts ordered by recency
        3. Take top MAX_DURABLE_FACTS for the prompt

        Args:
            session: Database session
            user_id: User ID to load facts for
            recent_turns: Optional recent conversation turns for relevance ranking

        Returns:
            Tuple of (selected facts, selection method) where selection method is
            'relevance' (subject words matched recent turns), 'recency' (only recent),
            or 'chroma' (Chroma-assisted ranking, for future use)
        """
        # Load candidates from Postgres (canonical source)
        stmt = (
            select(DurableFact)
            .where(
                # pyrefly: ignore [bad-argument-type]
                DurableFact.user_id == user_id,
                # pyrefly: ignore [bad-argument-type]
                DurableFact.active == True,  # noqa: E712
            )
            # pyrefly: ignore [missing-attribute]
            .order_by(DurableFact.updated_at.desc())
            .limit(MAX_FACT_CANDIDATES)
        )
        result = await session.execute(stmt)
        candidates = list(result.scalars().all())

        if not candidates:
            return [], 'recency'

        # If no recent turns, use simple recency-based selection
        if not recent_turns:
            return candidates[:MAX_DURABLE_FACTS], 'recency'

        # Rank by relevance to recent turns
        # Build a set of words from all recent message content for efficient, whole-word matching.
        recent_content_words = set(
            re.findall(
                r'\b\w+\b',
                ' '.join(msg.content for msg in recent_turns).lower(),
            )
        )

        # Split subject into words for matching (e.g., "George Langley" -> ["george", "langley"])
        def _subject_words(subject: str) -> list[str]:
            """Extract lowercased words from subject."""
            return re.findall(r'\b\w+\b', subject.lower())

        # Separate facts into relevant and remaining groups
        relevant_facts = []
        remaining_facts = []

        for fact in candidates:
            # Check if any word from the subject appears in recent content
            subject_words = _subject_words(fact.subject)
            is_relevant = any(
                word in recent_content_words for word in subject_words
            )

            if is_relevant:
                relevant_facts.append(fact)
            else:
                remaining_facts.append(fact)

        # If we found relevant facts, use them. Otherwise fall back to recency.
        if relevant_facts:
            # Sort relevant facts by recency as a tiebreaker
            relevant_facts.sort(key=lambda f: f.updated_at, reverse=True)
            selected = (relevant_facts + remaining_facts)[:MAX_DURABLE_FACTS]
            return selected, 'relevance'

        # Fallback: no relevant facts, use recency
        return candidates[:MAX_DURABLE_FACTS], 'recency'

    async def _load_facts_by_ranked_ids(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        ranked_fact_ids: list[uuid.UUID],
    ) -> list[DurableFact]:
        """Reload active facts from Postgres and preserve the given ranking."""
        stmt = select(DurableFact).where(
            # pyrefly: ignore [bad-argument-type]
            DurableFact.user_id == user_id,
            # pyrefly: ignore [bad-argument-type]
            DurableFact.active == True,  # noqa: E712
            # pyrefly: ignore [missing-attribute]
            DurableFact.id.in_(ranked_fact_ids),
        )
        result = await session.execute(stmt)
        facts_by_id = {fact.id: fact for fact in result.scalars().all()}

        ranked_facts = [
            facts_by_id[fact_id]
            for fact_id in ranked_fact_ids
            if fact_id in facts_by_id
        ]
        logger.debug(
            'Reloaded %s/%s ranked durable facts from Postgres for user_id=%s',
            len(ranked_facts),
            len(ranked_fact_ids),
            user_id,
        )
        return ranked_facts

    @staticmethod
    def _dedupe_fact_ids(fact_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        """Remove duplicate fact IDs while preserving the first-seen order."""
        seen: set[uuid.UUID] = set()
        deduped: list[uuid.UUID] = []
        for fact_id in fact_ids:
            if fact_id in seen:
                continue
            seen.add(fact_id)
            deduped.append(fact_id)
        return deduped

    async def _load_recent_turns(
        self,
        session: AsyncSession,
        *,
        conversation_id: uuid.UUID,
        max_turns: int,
    ) -> list[Message]:
        """Load recent conversation turns.

        Returns the last N messages ordered by sequence number.
        """
        stmt = (
            select(Message)
            .where(
                # pyrefly: ignore [bad-argument-type]
                Message.conversation_id == conversation_id
            )
            # pyrefly: ignore [missing-attribute]
            .order_by(Message.sequence_number.desc())
            .limit(max_turns)
        )
        result = await session.execute(stmt)
        messages = list(result.scalars().all())
        # Reverse to get chronological order
        return list(reversed(messages))

    def _build_message_list(
        self,
        *,
        summary: ConversationMemorySummary | None,
        facts: list[DurableFact],
        recent_turns: list[Message],
        new_user_message: str | None,
    ) -> list[dict]:
        """Build the final message list for the LLM.

        Strategy:
        - If summary exists: include compact summary + facts + recent turns
        - If no summary: include facts + recent turns (larger window)
        - Include new_user_message if provided (new conversations only)

        Context blocks use system messages for clarity and compatibility
        with OpenAI-style chat endpoints.
        """
        messages: list[dict] = []

        # Add summary context if available
        if summary:
            summary_text = self._truncate_text(
                summary.summary_text, MAX_SUMMARY_TEXT_LENGTH
            )
            messages.append(
                {
                    'role': 'system',
                    'content': (f'[Conversation summary]: {summary_text}'),
                }
            )

        # Add durable facts context if available
        if facts:
            fact_lines = []
            for fact in facts:
                fact_text = self._truncate_text(
                    fact.fact_text, MAX_FACT_TEXT_LENGTH
                )
                # Include subject for clarity
                fact_lines.append(
                    f'- {fact.subject}: {fact_text} '
                    f'(confidence: {fact.confidence})'
                )
            facts_content = '\n'.join(fact_lines)
            messages.append(
                {
                    'role': 'system',
                    'content': (
                        f'[Known facts about the user]:\n{facts_content}'
                    ),
                }
            )

        # Add recent conversation turns
        for msg in recent_turns:
            messages.append({'role': msg.role, 'content': msg.content})

        # Add the new user message if provided (for new conversations)
        if new_user_message:
            messages.append({'role': 'user', 'content': new_user_message})

        return messages

    @staticmethod
    def _truncate_text(text: str, max_length: int) -> str:
        """Truncate text to max_length, adding ellipsis if needed."""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + '...'
