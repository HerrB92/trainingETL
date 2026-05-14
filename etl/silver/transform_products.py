"""Silver layer: products and categories cleansing and upsert."""

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from etl.utils.logging import get_logger
from etl.utils.spark import get_spark

logger = get_logger(__name__)


def _silver_path(storage_account: str, entity: str) -> str:
    return f"abfss://silver@{storage_account}.dfs.core.windows.net/{entity}"


def _bronze_path(storage_account: str, entity: str) -> str:
    return f"abfss://bronze@{storage_account}.dfs.core.windows.net/{entity}"


def _cleanse_products(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Normalise and validate product records."""
    df = df.withColumn("name", F.trim(F.col("name")))
    df = df.withColumn("sku", F.upper(F.trim(F.col("sku"))))
    df = df.withColumn(
        "description",
        F.when(F.col("description").isNull(), F.lit("")).otherwise(F.trim(F.col("description"))),
    )

    valid_mask = (
        F.col("product_id").isNotNull()
        & F.col("sku").isNotNull()
        & (F.length(F.col("sku")) > 0)
        & F.col("supplier_id").isNotNull()
        & (F.col("list_price") >= 0)
        & (F.col("stock_qty") >= 0)
    )

    valid_df = df.filter(valid_mask)
    quarantine_df = df.filter(~valid_mask).withColumn(
        "_quarantine_reason", F.lit("Failed product validation")
    )
    return valid_df, quarantine_df


def _upsert(spark: SparkSession, incoming: DataFrame, path: str, key: str) -> None:
    from delta.tables import DeltaTable

    if DeltaTable.isDeltaTable(spark, path):
        DeltaTable.forPath(spark, path).alias("t").merge(
            incoming.alias("s"), f"t.{key} = s.{key}"
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
    else:
        incoming.write.format("delta").mode("overwrite").save(path)


def transform_products(spark: SparkSession, storage_account: str) -> None:
    categories = spark.read.format("delta").load(_bronze_path(storage_account, "categories"))
    suppliers = spark.read.format("delta").load(_bronze_path(storage_account, "suppliers"))
    products = spark.read.format("delta").load(_bronze_path(storage_account, "products"))

    # Enrich products with category name and supplier name
    cat_lookup = categories.select(
        F.col("category_id"),
        F.col("name").alias("category_name"),
    )
    sup_lookup = suppliers.select(
        F.col("supplier_id"),
        F.col("name").alias("supplier_name"),
    )

    enriched = products.join(cat_lookup, on="category_id", how="left").join(
        sup_lookup, on="supplier_id", how="left"
    )

    valid_df, quarantine_df = _cleanse_products(enriched)

    _upsert(spark, categories, _silver_path(storage_account, "categories"), "category_id")
    _upsert(spark, suppliers, _silver_path(storage_account, "suppliers"), "supplier_id")
    _upsert(spark, valid_df, _silver_path(storage_account, "products"), "product_id")

    if quarantine_df.count() > 0:
        qpath = f"abfss://quarantine@{storage_account}.dfs.core.windows.net/products"
        quarantine_df.write.format("delta").mode("append").save(qpath)

    logger.info("Product transform complete", extra={"valid": valid_df.count()})


def run(storage_account: str | None = None) -> None:
    from etl.utils.keyvault import get_secret

    spark = get_spark("silver-products")
    if storage_account is None:
        storage_account = get_secret("storage-account-name")
    transform_products(spark, storage_account)
