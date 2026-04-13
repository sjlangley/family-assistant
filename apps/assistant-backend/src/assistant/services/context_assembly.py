"""Context assembly for conversation LLM calls.

Prepares the final message list using:
- Recent conversation turns (canonical Postgres)
- Latest conversation summary (canonical Postgres)
- Durable facts for the current user (canonical Postgres)

All data comes from authoritative Postgres sources.
Chroma retrieval support is deferred to future work (Step 6+).
"""

from dataclasses import dataclass
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.models.conversation_sql import Message
from assistant.models.memory_sql import ConversationMemorySummary, DurableFact

# Explicit prompt budget constants
MAX_RECENT_MESSAGES_WITH_SUMMARY = 4  # Last N messages when summary exists
MAX_RECENT_MESSAGES_NO_SUMMARY = 8  # Last N messages when no summary
MAX_DURABLE_FACTS = 5  # Maximum number of facts to include
MAX_FACT_TEXT_LENGTH = 200  # Truncate individual fact text
MAX_SUMMARY_TEXT_LENGTH = 1000  # Truncate summary text


@dataclass
class ContextAssemblyResult:
    """Result of context assembly."""

    messages: list[dict]  # Final prepared message list for LLM
    used_summary: bool  # Whether a saved summary was used
    summary_id: uuid.UUID | None  # ID of the summary if used
    fact_ids: list[uuid.UUID]  # IDs of durable facts included


class ContextAssemblyService:
    """Assembles context for conversation LLM calls from Postgres.

    Responsibilities:
    - Load recent conversation turns from Postgres
    - Load latest conversation summary from Postgres
    - Load active durable facts for user from Postgres
    - Apply explicit prompt budgets
    - Return prepared message list
    """

    def __init__(self) -> None:
        pass

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

        # Load active durable facts for this user
        facts = await self._load_active_facts(session, user_id=user_id)

        # Load recent conversation turns
        recent_turns = await self._load_recent_turns(
            session,
            conversation_id=conversation_id,
            max_turns=(
                MAX_RECENT_MESSAGES_WITH_SUMMARY
                if summary
                else MAX_RECENT_MESSAGES_NO_SUMMARY
            ),
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

        Args:
            session: Database session
            user_id: Current user ID
            user_message: The first user message

        Returns:
            ContextAssemblyResult with prepared messages and metadata
        """
        # Load active durable facts for this user
        facts = await self._load_active_facts(session, user_id=user_id)

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
        )

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
    ) -> list[DurableFact]:
        """Load active durable facts for a user.

        Facts are:
        - Filtered by user_id
        - Only active=True
        - Ordered by updated_at desc
        - Limited to MAX_DURABLE_FACTS
        """
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
            .limit(MAX_DURABLE_FACTS)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

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
