import uuid

import chromadb
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.models.memory_sql import (
    ConversationMemorySummary,
    DurableFact,
)
from assistant.utils.datetime_utils import utc_now


class MemoryStorage:
    """Memory storage using ChromaDB and Postgres."""

    def __init__(
        self, chroma_host: str, chroma_port: int, collection_name: str
    ):
        self.client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        self.collection = self.client.get_or_create_collection(
            name=collection_name
        )

    def add_memory(
        self,
        conversation_id: str,
        user_id: str,
        content: str,
        role: str = 'user',
    ) -> None:
        """Add a memory entry to the collection."""
        memory_id = str(uuid.uuid4())
        self.collection.add(
            ids=[memory_id],
            documents=[content],
            metadatas=[
                {
                    'conversation_id': conversation_id,
                    'user_id': user_id,
                    'role': role,
                    'timestamp': utc_now().isoformat(),
                }
            ],
        )

    def query_memory(
        self, user_id: str, query: str, n_results: int = 5
    ) -> list[str]:
        """Retrieve related memories to a query."""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where={'user_id': user_id},
            include=['documents'],
        )
        documents = results['documents'][0] if results['documents'] else []
        return documents

    async def upsert_conversation_summary(
        self,
        session: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: str,
        summary_text: str,
        source_message_id: uuid.UUID | None = None,
    ) -> ConversationMemorySummary:
        """
        Upsert a conversation summary with idempotency.

        - If no summary exists, create with version=1
        - If identical summary exists, return as no-op
        - If summary changed, update in place and increment version

        Args:
            session: AsyncSession for database operations
            conversation_id: UUID of the conversation
            user_id: User ID
            summary_text: New summary text
            source_message_id: Optional ID of message that generated this summary

        Returns:
            Persisted ConversationMemorySummary row
        """
        # Query for existing summary
        stmt = select(ConversationMemorySummary).where(
            ConversationMemorySummary.conversation_id == conversation_id
        )
        result = await session.execute(stmt)
        existing_summary = result.scalars().first()

        if existing_summary is None:
            # Create new summary with version=1
            new_summary = ConversationMemorySummary(
                conversation_id=conversation_id,
                user_id=user_id,
                summary_text=summary_text,
                source_message_id=source_message_id,
                version=1,
            )
            session.add(new_summary)
            await session.flush()
            return new_summary

        # Check if content is identical (no-op case)
        if (
            existing_summary.summary_text == summary_text
            and existing_summary.source_message_id == source_message_id
        ):
            # Identical, return as-is
            return existing_summary

        # Content changed, update in place and increment version
        existing_summary.summary_text = summary_text
        existing_summary.source_message_id = source_message_id
        existing_summary.version = existing_summary.version + 1
        await session.flush()
        return existing_summary

    async def upsert_durable_fact(
        self,
        session: AsyncSession,
        user_id: str,
        subject: str,
        fact_text: str,
        confidence,
        source_type,
        fact_key: str | None = None,
        source_conversation_id: uuid.UUID | None = None,
        source_message_id: uuid.UUID | None = None,
        source_excerpt: str | None = None,
    ) -> DurableFact:
        """
        Upsert a durable fact with idempotency and deduplication.

        Deduplication rules:
        - If fact_key present: dedupe by (user_id, fact_key, active=True)
        - If fact_key absent: dedupe by (user_id, subject, fact_text, active=True)

        - If identical fact exists, return as no-op
        - If matching fact exists but content changed, update in place
        - If no match exists, insert new active fact

        Args:
            session: AsyncSession for database operations
            user_id: User ID
            subject: Fact subject (e.g., person's name)
            fact_text: The fact content
            confidence: DurableFactConfidence enum value
            source_type: DurableFactSourceType enum value
            fact_key: Optional unique key for fact deduplication
            source_conversation_id: Optional conversation this came from
            source_message_id: Optional message this came from
            source_excerpt: Optional text excerpt that generated this fact

        Returns:
            Persisted DurableFact row
        """
        # Query for matching fact based on deduplication rules
        if fact_key is not None:
            # Dedupe by fact_key
            stmt = select(DurableFact).where(
                and_(
                    DurableFact.user_id == user_id,
                    DurableFact.fact_key == fact_key,
                    DurableFact.active == True,  # noqa: E712
                )
            )
        else:
            # Dedupe by subject and fact_text
            stmt = select(DurableFact).where(
                and_(
                    DurableFact.user_id == user_id,
                    DurableFact.subject == subject,
                    DurableFact.fact_text == fact_text,
                    DurableFact.active is True,
                )
            )

        result = await session.execute(stmt)
        existing_fact = result.scalars().first()

        if existing_fact is None:
            # No matching fact, insert new
            new_fact = DurableFact(
                user_id=user_id,
                subject=subject,
                fact_key=fact_key,
                fact_text=fact_text,
                confidence=confidence,
                source_type=source_type,
                source_conversation_id=source_conversation_id,
                source_message_id=source_message_id,
                source_excerpt=source_excerpt,
                active=True,
            )
            session.add(new_fact)
            await session.flush()
            return new_fact

        # Check if content is identical (no-op case)
        if (
            existing_fact.subject == subject
            and existing_fact.fact_text == fact_text
            and existing_fact.confidence == confidence
            and existing_fact.source_type == source_type
            and existing_fact.fact_key == fact_key
        ):
            # Identical, return as-is
            return existing_fact

        # Content changed, update in place
        existing_fact.subject = subject
        existing_fact.fact_text = fact_text
        existing_fact.confidence = confidence
        existing_fact.source_type = source_type
        existing_fact.fact_key = fact_key
        existing_fact.source_conversation_id = source_conversation_id
        existing_fact.source_message_id = source_message_id
        existing_fact.source_excerpt = source_excerpt
        await session.flush()
        return existing_fact
