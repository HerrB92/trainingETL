# Data Modeling: 3NF and Star Schema

## Why Data Modeling Matters

Without a deliberate structure, a database quickly becomes a mess of redundant, inconsistent data. Data modeling is the discipline of designing table structures that serve a specific purpose well.

The key insight: **OLTP databases (transactional systems) and OLAP databases (analytics) need fundamentally different structures.**

## Part 1: Third Normal Form (3NF) — The Source Schema

### What Problem Does 3NF Solve?

Imagine storing customer orders in one flat table:

| order_id | customer_name | customer_email | city | product_name | price | qty |
|----------|--------------|----------------|------|--------------|-------|-----|
| 1 | Thomas Müller | t.m@corp.de | Hamburg | Shelf | 189.90 | 2 |
| 2 | Thomas Müller | t.m@corp.de | Hamburg | Pallet | 12.50 | 100 |
| 3 | Sandra Bauer | s.b@co.de | Berlin | Pallet | 12.50 | 50 |

Problems:
- Thomas Müller's email appears twice → update anomaly: change it in one place, miss it in another
- "Hamburg" appears twice → if Thomas moves, we have to find every row
- "Pallet" price appears twice → price change requires updating multiple rows
- Delete order 1 → we lose the fact that Thomas Müller exists

### The Three Normal Forms

**1NF (First Normal Form):** Every column has atomic (indivisible) values; no repeating groups.
- Bad: `products = "Shelf,Pallet"` in one column
- Good: separate rows or a separate order_items table

**2NF (Second Normal Form):** Every non-key column depends on the *whole* primary key (matters for composite keys).
- Bad: a table with PK `(order_id, product_id)` where `product_name` depends only on `product_id`
- Good: move `product_name` to a separate products table

**3NF (Third Normal Form):** No transitive dependencies — non-key columns don't depend on other non-key columns.
- Bad: `city` and `zip` in the customers table, where `city` depends on `zip` (not on customer_id)
- Good: move `city` and `zip` to an `addresses` table; customers reference it by `address_id`

### Our OLTP Schema

```
addresses (address_id PK, street, city, zip, country_code)
    ▲                    ▲
    │                    │
customers                suppliers
(customer_id PK,         (supplier_id PK,
 address_id FK,           address_id FK,
 name, email, company)    name, contact_email)
    │
    │ 1:N
    ▼
orders (order_id PK,        ◄── categories (category_id PK,
        customer_id FK,              name, parent_category_id FK self-ref)
        order_date, status,              ▲
        shipping_address_id FK)          │
    │                              products (product_id PK,
    │ 1:N                                   category_id FK,
    ▼                                       supplier_id FK,
order_items (order_item_id PK,              sku, name, price, stock)
             order_id FK,                       ▲
             product_id FK,────────────────────┘
             quantity, unit_price, discount_pct)
```

**Why the `addresses` table?** Instead of storing `city` and `country_code` in both `customers` and `suppliers`, we share one `addresses` table. If a city's name changes (rare, but happens), we update one row.

**Why `order_items` separate from `orders`?** One order has many products. The alternative — storing product lists in one column — would violate 1NF.

**Why `categories` has a self-reference?** It models a hierarchy: "Shelving Systems" → parent: "Warehouse Equipment". The `parent_category_id` points to another row in the same table.

## Part 2: Star Schema (Kimball) — The Analytics Schema

### Why Not Use 3NF for Analytics?

3NF is excellent for writing data. For reading it, it's painful:

```sql
-- How much revenue did Hamburg customers generate in 2024?
SELECT SUM(oi.quantity * oi.unit_price * (1 - oi.discount_pct/100))
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN customers c ON o.customer_id = c.customer_id
JOIN addresses a ON c.address_id = a.address_id
WHERE a.city = 'Hamburg'
  AND YEAR(o.order_date) = 2024
```

Six tables, five joins, just for a simple aggregation. BI tools struggle with this. 3NF also makes it impossible to preserve history (if a customer changes company, what was their company when they placed an order last year?).

### The Star Schema

```
            dim_date
              │
              │ date_key FK
              │
dim_customer ─┼─ fact_sales ─┼─ dim_product
              │  (grain: one │
dim_supplier ─┘  order line) └─ (embedding_vector for semantic search)
```

**The fact table** (`fact_sales`) sits at the centre. It has one row per order line item and contains only:
- Foreign keys to all dimension tables (to enable joins)
- Measurable, additive numbers (quantities, prices, revenue)

**Dimension tables** describe the "who, what, when, where":
- `dim_customer` — who bought
- `dim_product` — what was bought  
- `dim_date` — when it was bought
- `dim_supplier` — who supplied the product

Now the Hamburg query becomes:
```sql
SELECT SUM(f.revenue)
FROM fact_sales f
JOIN dim_customer c ON f.customer_key = c.customer_key
JOIN dim_date d ON f.date_key = d.date_key
WHERE c.city = 'Hamburg'
  AND d.year = 2024
  AND c.is_current = TRUE
```

Three tables, two joins. Much simpler.

### Surrogate Keys

In the star schema, dimension tables use **surrogate keys** (arbitrary integers) rather than the source IDs:

| dim_customer | | |
|-------------|---|---|
| **customer_key** (PK, surrogate) | **customer_id** (natural key, from OLTP) | name |
| 1001 | 42 | Thomas Müller |

Why? Because natural keys from source systems can change, be reused after deletion, or conflict across multiple source systems. Surrogate keys are stable and controlled by the warehouse.

### Slowly Changing Dimensions (SCD)

What happens when a customer changes company? We have three choices (Kimball's SCD types):

**SCD Type 1 (Overwrite):** Just update the row. Simple, but history is lost. Used for `dim_product` (price changes are acceptable to overwrite).

**SCD Type 2 (Add New Row):** Insert a new row with the new value; mark the old row as inactive.

```
| customer_key | customer_id | company | valid_from | valid_to | is_current |
|-------------|------------|---------|-----------|---------|-----------|
| 1001 | 42 | Corp A GmbH | 2023-01-01 | 2024-05-31 | FALSE |
| 1042 | 42 | Corp B AG | 2024-06-01 | NULL | TRUE |
```

Now: historical fact_sales rows pointing to key `1001` still show "Corp A GmbH" (the company at order time). New orders get key `1042`. History is preserved. Used for `dim_customer`.

**SCD Type 3 (Add Column):** Add a `previous_company` column. Simple but only keeps one level of history. Not used here.

### The dim_date Table

`dim_date` is pre-generated for the full time range (2020–2030) and never changes. Advantages:
- Enables complex calendar queries without SQL date functions (which vary by database)
- `is_holiday_de`, `is_weekend`, `week_of_year` calculated once, not per query
- Consistent `date_key = YYYYMMDD` integer (e.g. 20240115) for fast joins

```sql
-- Q2 2024 weekend revenue — trivially easy with dim_date
SELECT SUM(f.revenue)
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
WHERE d.year = 2024 AND d.quarter = 2 AND d.is_weekend = TRUE
```

### The Kimball Bus Matrix

The "bus matrix" is a planning tool: rows are business processes, columns are dimensions.

| Business Process | dim_date | dim_customer | dim_product | dim_supplier |
|-----------------|----------|-------------|------------|-------------|
| Sales (order items) | ✓ | ✓ | ✓ | ✓ |
| Returns (future) | ✓ | ✓ | ✓ | — |
| Inventory (future) | ✓ | — | ✓ | ✓ |

When multiple fact tables share a dimension (with the same surrogate keys), BI tools can drill across them — e.g. see sales and returns for the same product side by side.

## Summary: When to Use Which

| Scenario | Use |
|----------|-----|
| Application database (orders, customers, users) | 3NF |
| Analytics, reporting, BI dashboards | Star schema |
| Exploratory data science | Denormalized flat tables |
| Real-time streaming | Delta Lake with bronze-only or light silver |
