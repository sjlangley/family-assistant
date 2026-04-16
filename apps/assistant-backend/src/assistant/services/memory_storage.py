import uuid

import chromadb
from sqlalchemy import and_, func, select, text
from sqlalchemy.dialects.postgresql import insert
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
        Upsert a conversation summary atomically with idempotency.

        Uses PostgreSQL's atomic ON CONFLICT for production, falls back
        to read-check-insert for other databases (tests).

        - If no summary exists, create with version=1
        - On conflict (by conversation_id), update and increment version
        - Atomic upsert prevents race conditions on concurrent retries

        Args:
            session: AsyncSession for database operations
            conversation_id: UUID of the conversation
            user_id: User ID
            summary_text: New summary text
            source_message_id: Optional ID of message that generated this summary

        Returns:
            Persisted ConversationMemorySummary row
        """
        # Use atomic PostgreSQL upsert when the bound dialect supports it.
        bind = session.bind
        if bind is not None and bind.dialect.name == 'postgresql':
            stmt = (
                insert(ConversationMemorySummary)
                .values(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    summary_text=summary_text,
                    source_message_id=source_message_id,
                    version=1,
                )
                .on_conflict_do_update(
                    index_elements=['conversation_id'],
                    set_={
                        'summary_text': summary_text,
                        'source_message_id': source_message_id,
                        'version': (ConversationMemorySummary.version + 1),
                        'updated_at': func.now(),
                    },
                )
                .returning(ConversationMemorySummary)
            )

            result = await session.execute(stmt)
            await session.flush()
            row = result.scalars().first()
            if row is not None:
                return row

        # Fallback: manual upsert for SQLite and other databases
        stmt = select(ConversationMemorySummary).where(
            # pyrefly: ignore [bad-argument-type]
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

        # Update existing summary
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
        Upsert a durable fact atomically with idempotency and deduplication.

        Uses PostgreSQL's atomic ON CONFLICT for production, falls back
        to read-check-insert for other databases (tests).

        Deduplication rules:
        - If fact_key present: dedupe by (user_id, fact_key, active=True)
        - If fact_key absent: dedupe by (user_id, subject, fact_text, active=True)

        Atomic upsert prevents race conditions on concurrent retries.

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
        # Prepare values for atomic upsert
        values = {
            'user_id': user_id,
            'subject': subject,
            'fact_key': fact_key,
            'fact_text': fact_text,
            'confidence': confidence,
            'source_type': source_type,
            'source_conversation_id': source_conversation_id,
            'source_message_id': source_message_id,
            'source_excerpt': source_excerpt,
            'active': True,
        }

        update_values = {
            'subject': subject,
            'fact_key': fact_key,
            'fact_text': fact_text,
            'confidence': confidence,
            'source_type': source_type,
            'source_conversation_id': source_conversation_id,
            'source_message_id': source_message_id,
            'source_excerpt': source_excerpt,
        }

        # Try atomic PostgreSQL upsert first
        try:
            # Use different conflict resolution based on fact_key presence
            # Must include index_where to match partial unique indexes exactly
            if fact_key is not None:
                # Conflict on keyed facts:
                # (user_id, fact_key, active) WHERE fact_key IS NOT NULL AND active = true
                stmt = (
                    insert(DurableFact)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=['user_id', 'fact_key', 'active'],
                        index_where=text(
                            'fact_key IS NOT NULL AND active = true'
                        ),
                        set_=update_values,
                    )
                    .returning(DurableFact)
                )
            else:
                # Conflict on keyless facts:
                # (user_id, subject, fact_text, active)
                # WHERE active = true AND fact_key IS NULL
                stmt = (
                    insert(DurableFact)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=[
                            'user_id',
                            'subject',
                            'fact_text',
                            'active',
                        ],
                        index_where=text('active = true AND fact_key IS NULL'),
                        set_=update_values,
                    )
                    .returning(DurableFact)
                )

            result = await session.execute(stmt)
            await session.flush()
            row = result.scalars().first()
            if row is not None:
                return row
        except Exception:
            # Fall through to manual upsert for SQLite or other DBs
            pass

        # Fallback: manual upsert for SQLite and other databases
        if fact_key is not None:
            # Dedupe by fact_key for keyed facts
            stmt = select(DurableFact).where(
                and_(
                    # pyrefly: ignore [bad-argument-type]
                    DurableFact.user_id == user_id,
                    # pyrefly: ignore [bad-argument-type]
                    DurableFact.fact_key == fact_key,
                    # pyrefly: ignore [bad-argument-type]
                    DurableFact.active == True,  # noqa: E712
                )
            )
        else:
            # Dedupe by subject and fact_text for keyless facts
            stmt = select(DurableFact).where(
                and_(
                    # pyrefly: ignore [bad-argument-type]
                    DurableFact.user_id == user_id,
                    # pyrefly: ignore [bad-argument-type]
                    DurableFact.subject == subject,
                    # pyrefly: ignore [bad-argument-type]
                    DurableFact.fact_text == fact_text,
                    # pyrefly: ignore [bad-argument-type]
                    DurableFact.active == True,  # noqa: E712
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

        # Update existing fact
        for key, value in update_values.items():
            setattr(existing_fact, key, value)
        await session.flush()

        return existing_fact

    def index_conversation_summary(
        self,
        summary: ConversationMemorySummary,
    ) -> None:
        """
        Index a conversation summary into Chroma.

        Uses stable document ID derived from Postgres row ID to support
        idempotent retries and upserts.

        Args:
            summary: ConversationMemorySummary row to index
        """
        doc_id = f'summary_{summary.id}'

        metadata = {
            'type': 'summary',
            'summary_id': str(summary.id),
            'user_id': summary.user_id,
            'conversation_id': str(summary.conversation_id),
            'version': summary.version,
        }

        if summary.source_message_id:
            metadata['source_message_id'] = str(summary.source_message_id)

        # Upsert (overwrites existing doc with same ID)
        self.collection.upsert(
            ids=[doc_id],
            documents=[summary.summary_text],
            metadatas=[metadata],
        )

    def index_durable_fact(
        self,
        fact: DurableFact,
    ) -> None:
        """
        Index an active durable fact into Chroma.

        Uses stable document ID derived from Postgres row ID to support
        idempotent retries and upserts. Only indexes active facts.

        Args:
            fact: DurableFact row to index (must be active)

        Raises:
            ValueError: If fact is not active
        """
        if not fact.active:
            raise ValueError('Cannot index inactive durable fact')

        doc_id = f'fact_{fact.id}'

        metadata = {
            'type': 'durable_fact',
            'fact_id': str(fact.id),
            'user_id': fact.user_id,
            'subject': fact.subject,
            'confidence': fact.confidence,
            'source_type': fact.source_type,
            'active': fact.active,
        }

        if fact.fact_key:
            metadata['fact_key'] = fact.fact_key

        if fact.source_conversation_id:
            metadata['source_conversation_id'] = str(
                fact.source_conversation_id
            )

        if fact.source_message_id:
            metadata['source_message_id'] = str(fact.source_message_id)

        # Upsert (overwrites existing doc with same ID)
        self.collection.upsert(
            ids=[doc_id],
            documents=[fact.fact_text],
            metadatas=[metadata],
        )

    def remove_durable_fact_from_chroma(
        self,
        fact_id: str,
    ) -> None:
        """
        Remove a durable fact from Chroma index.

        Call this to clean up indexed docs when a fact is deactivated.
        Uses the stable document ID format.

        Args:
            fact_id: String representation of the DurableFact.id UUID
        """
        doc_id = f'fact_{fact_id}'
        try:
            self.collection.delete(ids=[doc_id])
        except Exception:
            # Silently ignore if doc does not exist
            pass
