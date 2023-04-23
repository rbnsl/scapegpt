import chromadb

from chromadb.config import Settings
from chromadb.utils import embedding_functions
from gpt_index.indices.vector_store import GPTSimpleVectorIndex
from gpt_index.llm_predictor.base import LLMPredictor
from gpt_index.readers.schema.base import Document
from langchain.llms.openai import OpenAIChat
from typing import List, Tuple


# OpenAI model name constants
CHAT_MODEL = "gpt-3.5-turbo"
EMBEDDING_MODEL = "text-embedding-ada-002"


class ChromaCollectionClient:
    def __init__(
        self,
        api_type: str,
        host: str,
        port: int,
        openai_api_key: str,
        collection_name: str,
    ) -> None:
        """
        Args:
            api_type (str): The type of API to use when connecting to ChromaDB
                (e.g. 'rest').
            host (str): The hostname of the database server to connect to
                (usually an IP address).
            port (int): The port number to connect to.
            openai_api_key (str): The OpenAI API key to use.
            collection_name (str): The name of the ChromaDB collection to use. If
                unavailable, a new collection will be created with this name.
        """
        self._client = chromadb.Client(
            Settings(
                chroma_api_impl=api_type,
                chroma_server_host=host,
                chroma_server_http_port=port,
            )
        )
        self._openai_api_key = openai_api_key
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=self._openai_api_key, model_name=EMBEDDING_MODEL
        )
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name, embedding_function=openai_ef
        )

    def delete(self) -> None:
        """
        Deletes the specified collection and removes the reference to this
        instance.
        """
        self._client.delete_collection(name=self._collection_name)
        del self

    def load_summaries(self, summaries: List[Tuple[str, str]]) -> None:
        """Loads content into the ChromaDB collection.

        Args:
            summaries (List[Tuple[str, str]]): A list of tuples containing
                                            filename and content pairs for each
                                            document summary.
        """
        filename_ids, documents_content = [], []
        for filename, content in summaries:
            filename_ids.append(filename)
            documents_content.append(content)
        self._collection.add(
            documents=documents_content,
            ids=filename_ids,
        )

    def query(self, prompt: str, n_results: int = 3) -> str:
        """Constructs an answer to a provided prompt based on DB content.

        Uses ChromaDB's similarity search functionality to first return 3
        documents that are most similar—or in other words, most likely to
        contain answers—to the provided prompt. The resulting documents are
        passed to LlamaIndex's (FKA GPTIndex) list index which chunks up the
        documents appropriately and creates a new index. This index is then
        queried directly with the prompt, and LlamaIndex uses OpenAI's
        completion model under the hood to generate a natural-English response
        using the content from the documents that are part of the index.

        Args:
            prompt (str): The search prompt to query the collection for.
            n_results (int): The number of results to return. Defaults to 3.

        Returns:
            str: The query result as a string.
        """
        results = self._collection.query(
            query_texts=[prompt],
            n_results=n_results,
        )

        documents = []
        for result in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
        ):
            document = Document(
                doc_id=result[0],
                text=result[1],
                extra_info=result[2],
            )
            documents.append(document)

        llm_predictor = LLMPredictor(
            llm=OpenAIChat(temperature=0.6, model_name=CHAT_MODEL)
        )
        index = GPTSimpleVectorIndex.from_documents(
            documents, llm_predictor=llm_predictor
        )

        return index.query(prompt)
