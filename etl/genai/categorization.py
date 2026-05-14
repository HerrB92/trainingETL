"""Automated product categorization using Azure OpenAI (GPT-4o).

For products where category_id is NULL (uncategorized), we send the
product name and description to an LLM and ask it to pick the best
category from our predefined taxonomy.

This is called "zero-shot classification" — no training examples needed.
The LLM understands the categories from their names alone.

After categorization, the product is written back to Silver with:
  - category_name: the assigned category
  - _categorized_by: 'llm'
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from etl.utils.keyvault import get_ai_services_config
from etl.utils.logging import get_logger
from etl.utils.spark import get_spark

logger = get_logger(__name__)

# Our product taxonomy (must match categories in the OLTP DB)
CATEGORY_TAXONOMY = """
Top-level categories and their sub-categories:
1. Warehouse Equipment
   - Shelving Systems
   - Pallets & Containers
   - Lifting Equipment
   - Storage Bins
2. Transport & Logistics
   - Hand Trucks & Dollies
   - Conveyor Systems
   - Packaging Supplies
3. Facility & Cleaning
   - Cleaning Equipment
   - Waste Management
4. Safety & Signage
   - PPE
   - Floor Markings
"""

SYSTEM_PROMPT = f"""You are a B2B warehouse product cataloguing assistant.
Given a product name and description, classify it into exactly one sub-category
from the following taxonomy:

{CATEGORY_TAXONOMY}

Respond with ONLY the sub-category name, nothing else.
If uncertain, choose the closest match. Never respond with a top-level category.
"""


def _categorize_single(client, name: str, description: str) -> str:
    """Call GPT-4o to categorize one product. Returns sub-category name."""
    user_content = f"Product name: {name}\nDescription: {description or 'N/A'}"
    response = client.chat.completions.create(
        model="gpt-4o",  # available in Azure AI multi-service accounts
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=20,
        temperature=0,  # deterministic output for classification
    )
    return response.choices[0].message.content.strip()


def categorize_uncategorized_products(spark: SparkSession, storage_account: str) -> int:
    """Categorize products with no category_id using the LLM.

    Returns the number of products categorized.
    """
    from openai import AzureOpenAI

    cfg = get_ai_services_config()
    client = AzureOpenAI(
        azure_endpoint=cfg["endpoint"],
        api_key=cfg["api_key"],
        api_version="2024-02-01",
    )

    silver_path = f"abfss://silver@{storage_account}.dfs.core.windows.net/products"
    products = spark.read.format("delta").load(silver_path)

    # Only process products without a category
    uncategorized = products.filter(F.col("category_name").isNull()).select(
        "product_id", "name", "description"
    )

    count = uncategorized.count()
    if count == 0:
        logger.info("No uncategorized products found")
        return 0

    logger.info(f"Categorizing {count} products via LLM")
    pandas_df = uncategorized.toPandas()

    categories = []
    for _, row in pandas_df.iterrows():
        try:
            cat = _categorize_single(client, row["name"], row["description"])
            categories.append(cat)
            logger.info(f"'{row['name']}' → '{cat}'")
        except Exception as e:
            logger.warning(f"Categorization failed for product {row['product_id']}: {e}")
            categories.append(None)

    pandas_df["category_name"] = categories
    pandas_df["_categorized_by"] = "llm"

    result_df = spark.createDataFrame(
        pandas_df[["product_id", "category_name", "_categorized_by"]]
    )

    # Update Silver products with LLM-assigned categories
    from delta.tables import DeltaTable

    target = DeltaTable.forPath(spark, silver_path)
    target.alias("t").merge(
        result_df.alias("s"), "t.product_id = s.product_id"
    ).whenMatchedUpdate(
        condition="s.category_name IS NOT NULL",
        set={
            "category_name": "s.category_name",
            "_categorized_by": "s._categorized_by",
        },
    ).execute()

    logger.info(f"LLM categorization complete: {count} products processed")
    return count


def run(storage_account: str | None = None) -> None:
    from etl.utils.keyvault import get_secret
    spark = get_spark("genai-categorization")
    if storage_account is None:
        storage_account = get_secret("storage-account-name")
    categorize_uncategorized_products(spark, storage_account)
