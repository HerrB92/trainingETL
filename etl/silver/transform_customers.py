"""Silver layer: customers and addresses cleansing and upsert."""

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from etl.utils.logging import get_logger
from etl.utils.spark import get_spark

logger = get_logger(__name__)


def _build_silver_path(storage_account: str, entity: str) -> str:
    return f"abfss://silver@{storage_account}.dfs.core.windows.net/{entity}"


def _build_bronze_path(storage_account: str, entity: str) -> str:
    return f"abfss://bronze@{storage_account}.dfs.core.windows.net/{entity}"


def _cleanse_customers(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Cleanse customers: normalise, validate, separate invalid rows."""
    # Normalise
    df = df.withColumn("email", F.lower(F.trim(F.col("email"))))
    df = df.withColumn("name", F.trim(F.col("name")))
    df = df.withColumn("company", F.trim(F.col("company")))

    # Validation rules
    valid_mask = (
        F.col("customer_id").isNotNull()
        & F.col("email").rlike(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
        & (F.length(F.col("email")) <= 200)
        & F.col("company").isNotNull()
        & (F.length(F.col("company")) > 0)
    )

    valid_df = df.filter(valid_mask)
    quarantine_df = df.filter(~valid_mask).withColumn(
        "_quarantine_reason", F.lit("Failed customer validation")
    )
    return valid_df, quarantine_df


def _cleanse_addresses(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Cleanse addresses: trim strings, validate country codes."""
    df = df.withColumn("street", F.trim(F.col("street")))
    df = df.withColumn("city", F.trim(F.col("city")))
    df = df.withColumn("zip", F.trim(F.col("zip")))
    df = df.withColumn("country_code", F.upper(F.trim(F.col("country_code"))))

    valid_mask = (
        F.col("address_id").isNotNull()
        & F.col("city").isNotNull()
        & (F.length(F.col("country_code")) == 2)
    )

    valid_df = df.filter(valid_mask)
    quarantine_df = df.filter(~valid_mask).withColumn(
        "_quarantine_reason", F.lit("Failed address validation")
    )
    return valid_df, quarantine_df


def _upsert_to_silver(
    spark: SparkSession,
    incoming: DataFrame,
    silver_path: str,
    merge_key: str,
) -> None:
    """Merge incoming records into the Silver Delta table (upsert)."""
    from delta.tables import DeltaTable

    incoming.createOrReplaceTempView("incoming")

    if DeltaTable.isDeltaTable(spark, silver_path):
        target = DeltaTable.forPath(spark, silver_path)
        target.alias("target").merge(
            incoming.alias("source"),
            f"target.{merge_key} = source.{merge_key}",
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
    else:
        incoming.write.format("delta").mode("overwrite").save(silver_path)


def _write_quarantine(df: DataFrame, storage_account: str, entity: str) -> None:
    if df.count() == 0:
        return
    path = f"abfss://quarantine@{storage_account}.dfs.core.windows.net/{entity}"
    df.write.format("delta").mode("append").option("mergeSchema", "true").save(path)
    logger.warning("Quarantined rows", extra={"entity": entity, "count": df.count()})


def transform_customers(spark: SparkSession, storage_account: str) -> None:
    addresses_bronze = spark.read.format("delta").load(
        _build_bronze_path(storage_account, "addresses")
    )
    customers_bronze = spark.read.format("delta").load(
        _build_bronze_path(storage_account, "customers")
    )

    addr_valid, addr_quarantine = _cleanse_addresses(addresses_bronze)
    cust_valid, cust_quarantine = _cleanse_customers(customers_bronze)

    # Enrich customers with city/country from addresses
    addr_lookup = addr_valid.select("address_id", "city", "country_code")
    cust_enriched = cust_valid.join(addr_lookup, on="address_id", how="left")

    _upsert_to_silver(spark, addr_valid, _build_silver_path(storage_account, "addresses"), "address_id")
    _upsert_to_silver(spark, cust_enriched, _build_silver_path(storage_account, "customers"), "customer_id")

    _write_quarantine(addr_quarantine, storage_account, "addresses")
    _write_quarantine(cust_quarantine, storage_account, "customers")

    logger.info(
        "Customer transform complete",
        extra={"valid_customers": cust_valid.count(), "valid_addresses": addr_valid.count()},
    )


def run(storage_account: str | None = None) -> None:
    from etl.utils.keyvault import get_secret
    spark = get_spark("silver-customers")
    if storage_account is None:
        storage_account = get_secret("storage-account-name")
    transform_customers(spark, storage_account)
