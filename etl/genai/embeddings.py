"""Semantic product search via Azure OpenAI embeddings stored in Delta Lake.

Workflow:
1. Read Silver products table
2. For each product, generate an embedding of "name + description"
   using text-embedding-ada-002 via the existing Azure AI services account
3. Store the 1536-dim vector in dim_product.embedding_vector (Delta Lake)
4. Expose a search() function for semantic similarity queries

Why embeddings?
  Traditional search matches exact keywords. Embeddings represent meaning as
  vectors in high-dimensional space — similar meaning → similar vectors.
  Example: "hand truck" and "sack barrow" are unrelated by keyword but
  close in embedding space because they serve the same purpose.
"""

import os
from functools import lru_cache

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, FloatType

from etl.utils.keyvault import get_ai_services_config
from etl.utils.logging import get_logger
from etl.utils.spark import get_spark

logger = get_logger(__name__)

EMBEDDING_MODEL = "text-embedding-ada-002"
EMBEDDING_DIMS = 1536
BATCH_SIZE = 16  # Azure OpenAI rate limit: keep batches small


@lru_cache(maxsize=1)
def _get_openai_client():
    """Create an Azure OpenAI client (cached so we don't reconnect per row)."""
    from openai import AzureOpenAI

    cfg = get_ai_services_config()
    return AzureOpenAI(
        azure_endpoint=cfg["endpoint"],
        api_key=cfg["api_key"],
        api_version="2024-02-01",
    )


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Call Azure OpenAI to embed a batch of texts."""
    client = _get_openai_client()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def _embed_products_pandas(products_df) -> list[list[float]]:
    """Embed all products in batches; returns list aligned with input rows."""
    texts = [
        f"{row.name}. {row.description or ''}".strip()
        for row in products_df.itertuples()
    ]
    embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        embeddings.extend(_embed_texts(batch))
        logger.info(f"Embedded {min(i + BATCH_SIZE, len(texts))}/{len(texts)} products")
    return embeddings


def generate_product_embeddings(spark: SparkSession, storage_account: str) -> None:
    """Generate embeddings for all Silver products and store in Gold dim_product."""
    silver_path = f"abfss://silver@{storage_account}.dfs.core.windows.net/products"
    gold_path = f"abfss://gold@{storage_account}.dfs.core.windows.net/dim_product"

    products_df = spark.read.format("delta").load(silver_path).select(
        "product_id", "name", "description"
    )
    pandas_df = products_df.toPandas()

    logger.info(f"Generating embeddings for {len(pandas_df)} products")
    pandas_df["embedding_vector"] = _embed_products_pandas(pandas_df)

    embed_spark_df = spark.createDataFrame(
        pandas_df[["product_id", "embedding_vector"]]
    ).withColumn("embedding_vector", F.col("embedding_vector").cast(ArrayType(FloatType())))

    # Merge embedding vectors into dim_product
    from delta.tables import DeltaTable

    target = DeltaTable.forPath(spark, gold_path)
    target.alias("t").merge(
        embed_spark_df.alias("s"), "t.product_id = s.product_id"
    ).whenMatchedUpdate(set={"embedding_vector": "s.embedding_vector"}).execute()

    logger.info("Embeddings written to dim_product")


def search_products(
    spark: SparkSession,
    storage_account: str,
    query: str,
    top_k: int = 5,
) -> "pyspark.sql.DataFrame":
    """Semantic product search: returns top-k products similar to the query.

    Args:
        query: Natural language search query (e.g. "something to move heavy boxes")
        top_k: Number of results to return

    Returns:
        Spark DataFrame with columns: product_id, sku, name, category, similarity_score
    """
    import math

    query_embedding = _embed_texts([query])[0]

    gold_path = f"abfss://gold@{storage_account}.dfs.core.windows.net/dim_product"
    dim_product = spark.read.format("delta").load(gold_path).filter(
        F.col("embedding_vector").isNotNull()
    )

    # Cosine similarity in PySpark (no external vector DB required)
    # cos(A, B) = dot(A, B) / (|A| * |B|)
    # Since ada-002 vectors are already L2-normalised, |A|=|B|=1 → cos = dot
    query_vec_lit = F.array([F.lit(v) for v in query_embedding])

    def dot_product_col(vec_col, query_vec):
        """Element-wise multiply then sum (dot product via zip_with + aggregate)."""
        return F.aggregate(
            F.zip_with(vec_col, query_vec, lambda x, y: x * y),
            F.lit(0.0),
            lambda acc, x: acc + x,
        )

    result = (
        dim_product.withColumn(
            "similarity_score",
            dot_product_col(F.col("embedding_vector"), query_vec_lit),
        )
        .select("product_id", "sku", "name", "category", "list_price", "similarity_score")
        .orderBy(F.col("similarity_score").desc())
        .limit(top_k)
    )
    return result


def run(storage_account: str | None = None) -> None:
    from etl.utils.keyvault import get_secret
    spark = get_spark("genai-embeddings")
    if storage_account is None:
        storage_account = get_secret("storage-account-name")
    generate_product_embeddings(spark, storage_account)
