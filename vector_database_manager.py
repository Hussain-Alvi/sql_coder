"""
Store and retrieve embeddings in ChromaDB.
"""
import os
import re
import logging
from typing import Tuple, List
import pandas as pd
from tqdm import tqdm

import chromadb
import pandas as pd
from dynaconf import Dynaconf
from tqdm import tqdm

from chromadb import Documents, EmbeddingFunction, Embeddings
from sentence_transformers import SentenceTransformer

# global variables
model: SentenceTransformer = None
collection: chromadb.api.models.Collection.Collection = None
pd.options.mode.chained_assignment = None  # Suppress pandas warnings


class MPNetEmbeddingFunction(EmbeddingFunction):
    """
    ChromaDb custom embedding function.
    """

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = model.encode(input)
        return embeddings.tolist()


def load_embedding_model(logger: logging.getLogger, ):
    """Initialize embeddings model."""
    global model
    logger.info("Loading embedding model.")
    model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')


def create_vector_db_collection(settings: Dynaconf):
    """Create embeddings database collection."""
    global collection

    client = chromadb.PersistentClient(settings.get("VECTORS_DB_PATH"))
    # client.delete_collection("client_sql_queries")  # Delete collection
    collection = client.get_or_create_collection("client_sql_queries", embedding_function=MPNetEmbeddingFunction())


def get_embeddings(text: str):
    """
    Given string return embedding.
    """
    return model.encode([text])


def check_and_load_query_data(settings: Dynaconf, logger: logging.Logger):
    """
    Check number of stored queries in collection and if not present, load them from CSV.
    CSV must have two columns: client_query, sql_query
    """
    global collection
    rows = collection.count()
    if rows != 0:
        logger.info(f"Number of rows in the query collection: {rows}")
        return

    logger.info("Query collection empty, adding client queries + SQL mappings.")
    logger.info("This will take some time ...")

    # Load CSV
    csv_path = settings.get("CLIENT_SQL_CSV_PATH")
    df = pd.read_csv(csv_path)

    if "client_query" not in df.columns or "sql_query" not in df.columns:
        raise ValueError("CSV must contain 'client_query' and 'sql_query' columns.")

    batch_size = 16
    with tqdm(total=len(df), desc="Saving query embeddings in database.") as pbar:
        for i in range(0, len(df), batch_size):
            batch_df = df.iloc[i:i + batch_size]
            client_queries = batch_df["client_query"].tolist()
            ids = [f"q_{i + j}" for j in range(len(batch_df))]

            # Store sql_query in metadata
            metadatas = batch_df[["sql_query"]].to_dict(orient="records")

            collection.add(
                documents=client_queries,
                ids=ids,
                metadatas=metadatas
            )

            pbar.update(len(batch_df))

    logger.info("Client queries + SQL mappings added.")
    logger.info(f"Number of rows in the collection: {collection.count()}")


def search_client_queries(settings: Dynaconf, logger: logging.Logger, query: str) -> list:
    """
    Search stored client queries using embeddings and return both client_query + sql_query.
    """
    logger.info(f"Searching relevant client query using embeddings.")
    global collection

    vector = get_embeddings(query)

    results = collection.query(
        query_embeddings=vector.tolist(),
        n_results=2,
        include=["documents", "distances", "metadatas"]
    )

    documents = results['documents'][0]
    distances = results['distances'][0]
    metadatas = results['metadatas'][0]

    # Filter by distance threshold
    filtered = []
    for doc, distance, meta in zip(documents, distances, metadatas):
        if distance < 1.2:
            filtered.append({
                "client_query": doc,
                "sql_query": meta.get("sql_query", None),
            })

    return filtered
