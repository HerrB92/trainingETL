# GenAI Features

## Concepts: What Are Embeddings?

An embedding is a list of numbers (a "vector") that represents the meaning of a piece of text. The embedding model (in our case `text-embedding-ada-002`) maps text to a point in a 1536-dimensional space, such that **semantically similar text ends up near each other**.

Example:
```
"hand truck"      → [0.021, -0.403, 0.891, ...]  1536 numbers
"sack barrow"     → [0.019, -0.401, 0.887, ...]  very close!
"forklift pallet" → [0.041, -0.123, 0.701, ...]  somewhat close
"invoice payment" → [0.821, 0.032, -0.145, ...]  far away
```

Distance between vectors = semantic distance. Two texts about similar topics will have vectors close to each other even if they share no keywords.

## Feature 1: Semantic Product Search

**File:** [etl/genai/embeddings.py](../etl/genai/embeddings.py)

### What It Does

Traditional keyword search fails when the query and product description use different words for the same concept ("material handling equipment" vs. "stuff to move heavy boxes"). Semantic search finds products by meaning.

### How It Works

```
1. For each product in Silver:
   ┌─────────────────────────────────────────────────────────┐
   │  "Heavy Duty Boltless Shelving Unit 200x100x50cm.       │
   │   Load capacity 300 kg per shelf. Powder-coated steel." │
   └─────────────────────────────────────────────────────────┘
                           │
                    Azure OpenAI API
                    (text-embedding-ada-002)
                           │
                           ▼
   [0.021, -0.403, 0.891, 0.012, -0.234, ...]  ← 1536 floats

2. Store the vector in dim_product.embedding_vector (Delta Lake array column)

3. At query time:
   User: "something to carry heavy boxes around the warehouse"
                           │
                    Azure OpenAI API (same model)
                           │
                           ▼
   query_vector = [0.018, -0.392, 0.878, ...]

4. Compute cosine similarity against all product vectors in PySpark:
   similarity = dot(query_vector, product_vector)
   (valid because ada-002 vectors are L2-normalised → dot product = cosine)

5. Return top-5 most similar products
```

### Example Usage

```python
from etl.genai.embeddings import search_products
from etl.utils.spark import get_spark

spark = get_spark()
results = search_products(spark, "my-storage-account",
                          query="equipment for moving pallets",
                          top_k=5)
results.show(truncate=False)
```

Output:
```
+----------+-------+--------------------------------+---------------------+----------+----------------+
|product_id|sku    |name                            |category             |list_price|similarity_score|
+----------+-------+--------------------------------+---------------------+----------+----------------+
|9         |LFT-001|Manual Pallet Jack 2500 kg      |Lifting Equipment    |299.00    |0.921           |
|10        |LFT-002|Hydraulic Scissor Lift Table    |Lifting Equipment    |1299.00   |0.898           |
|41        |LFT-004|Mechanical Loading Ramp 1000 kg |Lifting Equipment    |599.00    |0.876           |
|4         |PLT-001|Euro Pallet 800x1200mm          |Pallets & Containers |12.50     |0.854           |
|16        |TRL-001|Hand Truck 250 kg Steel         |Hand Trucks & Dollies|79.00     |0.841           |
+----------+-------+--------------------------------+---------------------+----------+----------------+
```

### Cost

Embedding 50 products: ~50 × 200 tokens = 10,000 tokens = €0.001 (virtually free).
Query: 1 × ~15 tokens = negligible.

## Feature 2: Automated Product Categorization

**File:** [etl/genai/categorization.py](../etl/genai/categorization.py)

### What It Does

When new products arrive without a category (or with an incorrect one), the LLM automatically assigns the best category from our taxonomy. This is "zero-shot classification" — the model understands categories from their names without any training examples.

### How It Works

```
Product: "Disposable Nitrile Gloves M (Box 100) - Powder-free, EN455"
category_name: NULL

        │
        ▼
System prompt: "You are a B2B cataloguing assistant. Pick one sub-category
                from this taxonomy: [Shelving Systems, Pallets & Containers,
                Lifting Equipment, Storage Bins, Hand Trucks & Dollies,
                Conveyor Systems, Packaging Supplies, Cleaning Equipment,
                Waste Management, PPE, Floor Markings]
                Respond with ONLY the sub-category name."

User message: "Product: Disposable Nitrile Gloves M (Box 100). Powder-free, EN455"

        │
        ▼
GPT-4o response: "PPE"

        │
        ▼
Silver products updated: category_name = "PPE", _categorized_by = "llm"
```

### Prompt Design Notes

- `temperature=0` makes output deterministic (same input → same output every time)
- `max_tokens=20` prevents rambling responses — the category name is short
- The taxonomy in the system prompt constrains possible outputs (no hallucinated categories)
- The `_categorized_by = 'llm'` flag lets analysts filter and review LLM-assigned categories

## Feature 3: RAG Product Q&A (Stub — Not Yet Implemented)

**Planned file:** `etl/genai/rag.py`

### What Is RAG?

**R**etrieval **A**ugmented **G**eneration. Instead of asking the LLM to answer from its training data (which may be outdated or hallucinated), we first search our product catalog for relevant information, then pass that to the LLM as context.

```
User: "What is the maximum load capacity of your pallet jacks?"
        │
        ▼
1. Search dim_product for similar products (using embeddings)
   → retrieves: "Manual Pallet Jack 2500 kg", "Electric Stacker 1000 kg"

2. Build a prompt:
   "Based on this product information:
    - Manual Pallet Jack 2500 kg: 'Ergonomic handle, 2500 kg capacity'
    - Electric Stacker 1000 kg: '1000 kg, lift height 3000 mm'
    Answer: What is the maximum load capacity of your pallet jacks?"

3. LLM answers: "Our strongest pallet jack can handle up to 2500 kg.
                We also offer an electric stacker with 1000 kg capacity."
```

RAG prevents hallucination because the LLM is grounded in your actual data.

**To implement:** Add LangChain (`pip install langchain-openai`), create a `RetrievalQA` chain using the embedding search from Feature 1 as the retriever, and a GPT-4o `ChatOpenAI` as the generator.

## Feature 4: Natural Language to SQL (Stub)

**Concept:** Business users ask questions in plain German/English; the system generates and executes the SQL query against the Gold layer.

```
User: "Zeig mir die Top 10 Produkte nach Umsatz im letzten Quartal"

        │ LLM with Gold schema as context
        ▼

SELECT p.name, SUM(f.revenue) AS total_revenue
FROM fact_sales f
JOIN dim_product p ON f.product_key = p.product_key
JOIN dim_date d ON f.date_key = d.date_key
WHERE d.year = 2024 AND d.quarter = 2
GROUP BY p.product_key, p.name
ORDER BY total_revenue DESC
LIMIT 10

        │ executed against SQL Warehouse
        ▼

[results displayed as table]
```

**Key challenge:** The LLM must know the schema. Pass the DDL from `sql/analytics/01_star_schema.sql` as context in the system prompt. Use few-shot examples (2-3 example question+SQL pairs) to improve accuracy.

## Feature 5: Order Anomaly Detection (Stub)

**Concept:** Use PySpark ML to flag unusual order patterns — unusually large orders, orders from new customers for expensive items, or sudden drops in order volume.

```python
# Isolation Forest via PySpark ML
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.classification import RandomForestClassifier

# Features: order_value, customer_age_days, product_category_avg_price,
#           customer_order_count, time_since_last_order
```

**Use case:** Fraud detection, data quality monitoring, customer churn signals.

## Feature 6: Customer Churn Prediction (Stub)

**Concept:** Gradient boosted tree model trained on Gold layer data. Features derived from `fact_sales`:
- Days since last order
- Order frequency trend (decreasing = churn signal)
- Average order value trend
- Product category diversity

**Output:** `churn_probability` score per customer, refreshed weekly, stored as a new Gold table `dim_customer_churn`.

## How to Extend the GenAI Module

1. Create a new file in `etl/genai/` (e.g. `etl/genai/rag.py`)
2. Add an entry function named `run(storage_account: str | None = None) -> None`
3. Add a corresponding job task in `databricks/resources/etl_jobs.yml`
4. Add unit tests in `tests/test_genai_rag.py` (mock the OpenAI client)
5. The CI pipeline will automatically pick up and run the tests
