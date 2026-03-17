import uuid

import chromadb

from assistant.utils.datetime_utils import utc_now


class MemoryStorage:
    """Memory storage using ChromaDB."""

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
