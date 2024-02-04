import os

import os
from llama_index.vector_stores import AstraDBVectorStore
from llama_index import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
)

from llama_index.schema import TextNode, NodeRelationship, RelatedNodeInfo
import openai 

ASTRA_DB_APPLICATION_TOKEN = os.environ.get("ASTRA_DB_APPLICATION_TOKEN")
ASTRA_DB_API_ENDPOINT = os.environ.get("ASTRA_DB_API_ENDPOINT")

astra_db_store = AstraDBVectorStore(
    token=ASTRA_DB_APPLICATION_TOKEN,
    api_endpoint=ASTRA_DB_API_ENDPOINT,
    collection_name="demo",
    embedding_dimension=1536,
)
storage_context = StorageContext.from_defaults(vector_store=astra_db_store)

def get_notes_most_relevant(query_string: str, top_k: int = 3) -> list[str]:
    index = VectorStoreIndex.from_vector_store(vector_store=astra_db_store)
    
    retriever = index.as_retriever(
        vector_store_query_mode="mmr",
        similarity_top_k=top_k,
    )

    nodes_with_scores = retriever.retrieve(query_string)
    
    note_ids = [node.node_id for node in nodes_with_scores]

    return note_ids

def add_notes_to_rag(notes: list[dict]):
    nodes = [TextNode(text=note["data"]["title"] + "\n\n" + note["data"]["content"], id_=note["id"]) for note in notes]
    index = VectorStoreIndex(
        nodes, storage_context=storage_context
    )

def update_note_to_rag(note: dict):
    node = TextNode(text=note["data"]["title"] + "\n\n" + note["data"]["content"], id_=note["id"])
    index = VectorStoreIndex.from_vector_store(vector_store=astra_db_store)
    index._delete_node(note["id"])
    index = VectorStoreIndex(
        [node], storage_context=storage_context
    )
    
