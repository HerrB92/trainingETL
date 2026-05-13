resource "azurerm_databricks_workspace" "main" {
  name                = "dbw-${var.prefix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "standard"  # standard tier is sufficient for learning

  tags = var.tags
}

# ── Cluster Policy ───────────────────────────────────────────
# A cluster policy restricts what users can configure,
# ensuring auto-terminate is always set and only cost-effective
# node types are selectable.
resource "databricks_cluster_policy" "cost_optimized" {
  name = "Cost-Optimized Dev Policy"

  definition = jsonencode({
    "autotermination_minutes" = {
      "type"  = "fixed"
      "value" = 15
    }
    "node_type_id" = {
      "type"         = "allowlist"
      "values"       = ["Standard_DS3_v2", "Standard_DS4_v2"]
      "defaultValue" = "Standard_DS3_v2"
    }
    "num_workers" = {
      "type"         = "range"
      "minValue"     = 0
      "maxValue"     = 2
      "defaultValue" = 0  # single-node (driver only = cheapest)
    }
    "spark_version" = {
      "type"         = "unlimited"
      "defaultValue" = "14.3.x-scala2.12"
    }
  })
}

# ── All-Purpose Cluster (for interactive development) ────────
resource "databricks_cluster" "dev" {
  cluster_name            = "${var.prefix}-dev"
  spark_version           = "14.3.x-scala2.12"  # Databricks Runtime 14.3 LTS
  node_type_id            = "Standard_DS3_v2"
  autotermination_minutes = 15

  # single-node mode: driver acts as worker (no worker nodes → cheapest)
  num_workers = 0

  spark_conf = {
    "spark.master"                    = "local[*]"
    "spark.databricks.cluster.profile" = "singleNode"

    # Mount ADLS Gen2 using storage account key
    "fs.azure.account.key.${var.storage_account_name}.dfs.core.windows.net" = var.storage_account_key
  }

  custom_tags = {
    "ResourceClass" = "SingleNode"
  }

  policy_id = databricks_cluster_policy.cost_optimized.id
}

# ── SQL Warehouse (for BI queries against Gold tables) ───────
# SQL Warehouse is a separate compute type optimized for SQL.
# It auto-stops after idle timeout and is priced separately.
resource "databricks_sql_endpoint" "main" {
  name             = "${var.prefix}-warehouse"
  cluster_size     = "2X-Small"  # smallest available (2 DBU/h)
  max_num_clusters = 1
  auto_stop_mins   = 10

  enable_serverless_compute = false  # classic warehouse = more predictable cost

  tags {
    custom_tags {
      key   = "Environment"
      value = var.prefix
    }
  }
}

# ── Secret Scope (backed by Azure Key Vault) ─────────────────
# A Databricks Secret Scope linked to Key Vault lets notebooks
# read secrets via: dbutils.secrets.get("kv-scope", "secret-name")
# without the actual secret value appearing in code or logs.
resource "databricks_secret_scope" "keyvault" {
  name = "kv-scope"

  keyvault_metadata {
    resource_id = var.key_vault_id
    dns_name    = var.key_vault_uri
  }
}
