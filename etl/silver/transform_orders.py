"""Silver layer: orders and order_items cleansing and upsert."""

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from etl.utils.logging import get_logger
from etl.utils.spark import get_spark

logger = get_logger(__name__)

VALID_STATUSES = {"PENDING", "CONFIRMED", "SHIPPED", "DELIVERED", "CANCELLED"}


def _bronze_path(storage_account: str, entity: str) -> str:
    return f"abfss://bronze@{storage_account}.dfs.core.windows.net/{entity}"


def _silver_path(storage_account: str, entity: str) -> str:
    return f"abfss://silver@{storage_account}.dfs.core.windows.net/{entity}"


def _cleanse_orders(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    df = df.withColumn("status", F.upper(F.trim(F.col("status"))))

    valid_mask = (
        F.col("order_id").isNotNull()
        & F.col("customer_id").isNotNull()
        & F.col("order_date").isNotNull()
        & F.col("status").isin(*VALID_STATUSES)
    )
    return df.filter(valid_mask), df.filter(~valid_mask).withColumn(
        "_quarantine_reason", F.lit("Failed order validation")
    )


def _cleanse_order_items(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    valid_mask = (
        F.col("order_item_id").isNotNull()
        & F.col("order_id").isNotNull()
        & F.col("product_id").isNotNull()
        & (F.col("quantity") > 0)
        & (F.col("unit_price") >= 0)
        & F.col("discount_pct").between(0, 100)
    )
    # Calculate line revenue (stored in Silver for convenience)
    valid_df = df.filter(valid_mask).withColumn(
        "line_revenue",
        F.round(
            F.col("quantity") * F.col("unit_price") * (1 - F.col("discount_pct") / 100), 2
        ),
    )
    return valid_df, df.filter(~valid_mask).withColumn(
        "_quarantine_reason", F.lit("Failed order_item validation")
    )


def _upsert(spark: SparkSession, df: DataFrame, path: str, key: str) -> None:
    from delta.tables import DeltaTable

    if DeltaTable.isDeltaTable(spark, path):
        DeltaTable.forPath(spark, path).alias("t").merge(
            df.alias("s"), f"t.{key} = s.{key}"
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
    else:
        df.write.format("delta").mode("overwrite").save(path)


def transform_orders(spark: SparkSession, storage_account: str) -> None:
    orders_bronze = spark.read.format("delta").load(_bronze_path(storage_account, "orders"))
    items_bronze = spark.read.format("delta").load(_bronze_path(storage_account, "order_items"))

    valid_orders, q_orders = _cleanse_orders(orders_bronze)
    valid_items, q_items = _cleanse_order_items(items_bronze)

    _upsert(spark, valid_orders, _silver_path(storage_account, "orders"), "order_id")
    _upsert(spark, valid_items, _silver_path(storage_account, "order_items"), "order_item_id")

    for entity, qdf in [("orders", q_orders), ("order_items", q_items)]:
        if qdf.count() > 0:
            qpath = f"abfss://quarantine@{storage_account}.dfs.core.windows.net/{entity}"
            qdf.write.format("delta").mode("append").save(qpath)

    logger.info(
        "Order transform complete",
        extra={"valid_orders": valid_orders.count(), "valid_items": valid_items.count()},
    )


def run(storage_account: str | None = None) -> None:
    from etl.utils.keyvault import get_secret
    spark = get_spark("silver-orders")
    if storage_account is None:
        storage_account = get_secret("storage-account-name")
    transform_orders(spark, storage_account)
