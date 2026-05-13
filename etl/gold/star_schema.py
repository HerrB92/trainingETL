"""Gold layer: Kimball star schema construction.

Builds:
  dim_date      — static, 2020-2030, generated in Python
  dim_customer  — SCD Type 2 (history-preserving)
  dim_product   — SCD Type 1 (overwrite)
  dim_supplier  — SCD Type 1 (overwrite)
  fact_sales    — grain: one order line item
"""

from datetime import date, timedelta
from datetime import datetime, timezone

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    ByteType,
    DateType,
    IntegerType,
    LongType,
    ShortType,
    StringType,
    StructField,
    StructType,
)

from etl.utils.logging import get_logger
from etl.utils.spark import get_spark

logger = get_logger(__name__)

CUSTOMER_SEGMENTS = [
    (0, 10_000, "SMALL"),
    (10_001, 100_000, "MID"),
    (100_001, float("inf"), "ENTERPRISE"),
]


def _gold_path(storage_account: str, table: str) -> str:
    return f"abfss://gold@{storage_account}.dfs.core.windows.net/{table}"


def _silver_path(storage_account: str, entity: str) -> str:
    return f"abfss://silver@{storage_account}.dfs.core.windows.net/{entity}"


# ── dim_date ──────────────────────────────────────────────────

def build_dim_date(spark: SparkSession, storage_account: str) -> None:
    """Generate dim_date rows for 2020-01-01 through 2030-12-31."""
    from pyspark.sql import Row

    MONTH_NAMES = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    DAY_NAMES = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    # German public holidays (static set for the demo — national only)
    DE_HOLIDAYS = {
        date(y, m, d)
        for y in range(2020, 2031)
        for m, d in [(1,1),(5,1),(10,3),(12,25),(12,26)]
    }

    rows = []
    current = date(2020, 1, 1)
    end = date(2030, 12, 31)
    while current <= end:
        rows.append(
            Row(
                date_key=int(current.strftime("%Y%m%d")),
                date=current,
                year=current.year,
                quarter=((current.month - 1) // 3) + 1,
                month=current.month,
                month_name=MONTH_NAMES[current.month - 1],
                week=current.isocalendar()[1],
                day_of_week=current.isoweekday(),  # 1=Mon … 7=Sun
                day_name=DAY_NAMES[current.weekday()],
                is_weekend=current.weekday() >= 5,
                is_holiday_de=current in DE_HOLIDAYS,
            )
        )
        current += timedelta(days=1)

    dim_date_schema = StructType([
        StructField("date_key", IntegerType(), False),
        StructField("date", DateType(), False),
        StructField("year", ShortType(), False),
        StructField("quarter", ByteType(), False),
        StructField("month", ByteType(), False),
        StructField("month_name", StringType(), False),
        StructField("week", ByteType(), False),
        StructField("day_of_week", ByteType(), False),
        StructField("day_name", StringType(), False),
        StructField("is_weekend", BooleanType(), False),
        StructField("is_holiday_de", BooleanType(), False),
    ])

    df = spark.createDataFrame(rows, schema=dim_date_schema)
    path = _gold_path(storage_account, "dim_date")
    df.write.format("delta").mode("overwrite").save(path)
    logger.info("dim_date written", extra={"rows": len(rows)})


# ── dim_supplier ──────────────────────────────────────────────

def build_dim_supplier(spark: SparkSession, storage_account: str) -> None:
    suppliers = spark.read.format("delta").load(_silver_path(storage_account, "suppliers"))
    addresses = spark.read.format("delta").load(_silver_path(storage_account, "addresses"))

    df = suppliers.join(
        addresses.select("address_id", "country_code"), on="address_id", how="left"
    ).select(
        F.monotonically_increasing_id().alias("supplier_key"),
        F.col("supplier_id"),
        F.col("name"),
        F.col("country_code"),
    )
    df.write.format("delta").mode("overwrite").save(_gold_path(storage_account, "dim_supplier"))
    logger.info("dim_supplier written", extra={"rows": df.count()})


# ── dim_product ───────────────────────────────────────────────

def build_dim_product(spark: SparkSession, storage_account: str) -> None:
    products = spark.read.format("delta").load(_silver_path(storage_account, "products"))

    df = products.select(
        F.monotonically_increasing_id().alias("product_key"),
        "product_id",
        "sku",
        "name",
        F.col("category_name").alias("category"),
        F.col("supplier_name"),
        "list_price",
        "weight_kg",
        F.lit("manual").alias("categorized_by"),
    )
    df.write.format("delta").mode("overwrite").save(_gold_path(storage_account, "dim_product"))
    logger.info("dim_product written", extra={"rows": df.count()})


# ── dim_customer (SCD Type 2) ─────────────────────────────────

def build_dim_customer(spark: SparkSession, storage_account: str) -> None:
    """SCD2: preserve history when customer company or city changes.

    Incoming customers are merged with the existing dim_customer.
    Changed rows: old row gets valid_to = today, is_current = False.
    New version row inserted with valid_from = today, is_current = True.
    New customers: inserted directly.
    """
    from delta.tables import DeltaTable

    today = date.today()
    customers = spark.read.format("delta").load(_silver_path(storage_account, "customers"))

    # Assign customer segment based on annual order value (placeholder logic)
    # In production this would join to fact_sales; here we use a simple rule
    segment_df = (
        customers.withColumn(
            "customer_segment",
            F.when(F.col("customer_id") <= 5, F.lit("ENTERPRISE"))
            .when(F.col("customer_id") <= 10, F.lit("MID"))
            .otherwise(F.lit("SMALL")),
        )
        .withColumn("valid_from", F.lit(today.isoformat()).cast(DateType()))
        .withColumn("valid_to", F.lit(None).cast(DateType()))
        .withColumn("is_current", F.lit(True))
    )

    path = _gold_path(storage_account, "dim_customer")

    if not DeltaTable.isDeltaTable(spark, path):
        # First run: add surrogate key and write
        df = segment_df.withColumn(
            "customer_key", F.monotonically_increasing_id()
        )
        df.write.format("delta").mode("overwrite").save(path)
        logger.info("dim_customer initial load", extra={"rows": df.count()})
        return

    target = DeltaTable.forPath(spark, path)

    # Detect changed rows (company or city changed for current records)
    target.alias("t").merge(
        segment_df.alias("s"),
        "t.customer_id = s.customer_id AND t.is_current = true",
    ).whenMatchedUpdate(
        condition="t.company != s.company OR t.city != s.city",
        set={
            "is_current": F.lit(False),
            "valid_to": F.lit((today - timedelta(days=1)).isoformat()).cast(DateType()),
        },
    ).execute()

    # Insert new versions for changed + brand-new customers
    new_rows = segment_df.withColumn("customer_key", F.monotonically_increasing_id())
    new_rows.write.format("delta").mode("append").save(path)

    logger.info("dim_customer SCD2 merge complete")


# ── fact_sales ────────────────────────────────────────────────

def build_fact_sales(spark: SparkSession, storage_account: str) -> None:
    orders = spark.read.format("delta").load(_silver_path(storage_account, "orders"))
    items = spark.read.format("delta").load(_silver_path(storage_account, "order_items"))
    dim_customer = spark.read.format("delta").load(_gold_path(storage_account, "dim_customer"))
    dim_product = spark.read.format("delta").load(_gold_path(storage_account, "dim_product"))
    dim_supplier = spark.read.format("delta").load(_gold_path(storage_account, "dim_supplier"))

    # Current customer key only (SCD2 — is_current rows)
    cust_keys = dim_customer.filter(F.col("is_current")).select(
        "customer_id", "customer_key"
    )
    prod_keys = dim_product.select("product_id", "product_key", "supplier_name")
    sup_keys = dim_supplier.select("supplier_id", "supplier_key", F.col("name").alias("_sup_name"))

    # Join supplier key via product → supplier name (denorm path for demo)
    prod_with_sup = prod_keys.join(
        sup_keys.select("supplier_key", "_sup_name"),
        prod_keys.supplier_name == sup_keys._sup_name,
        "left",
    )

    fact = (
        items.join(orders.select("order_id", "customer_id", "order_date", "status"), on="order_id")
        .join(cust_keys, on="customer_id")
        .join(prod_with_sup.select("product_id", "product_key", "supplier_key"), on="product_id")
        .withColumn("date_key", F.date_format("order_date", "yyyyMMdd").cast(IntegerType()))
        .withColumn(
            "revenue",
            F.round(F.col("quantity") * F.col("unit_price") * (1 - F.col("discount_pct") / 100), 2),
        )
        .withColumn("cost_estimate", F.round(F.col("revenue") * 0.60, 2))
        .withColumn("ingested_at", F.lit(datetime.now(timezone.utc).isoformat()))
        .select(
            F.monotonically_increasing_id().alias("order_item_key"),
            "order_item_id",
            "order_id",
            "customer_key",
            "product_key",
            "date_key",
            "supplier_key",
            F.col("status").alias("order_status"),
            "quantity",
            "unit_price",
            "discount_pct",
            "revenue",
            "cost_estimate",
            "ingested_at",
        )
    )

    fact.write.format("delta").mode("overwrite").save(_gold_path(storage_account, "fact_sales"))
    logger.info("fact_sales written", extra={"rows": fact.count()})


# ── Orchestration entry point ─────────────────────────────────

def run(storage_account: str | None = None) -> None:
    from etl.utils.keyvault import get_secret
    spark = get_spark("gold-star-schema")
    if storage_account is None:
        storage_account = get_secret("storage-account-name")

    build_dim_date(spark, storage_account)
    build_dim_supplier(spark, storage_account)
    build_dim_product(spark, storage_account)
    build_dim_customer(spark, storage_account)
    build_fact_sales(spark, storage_account)

    logger.info("Gold layer build complete")
