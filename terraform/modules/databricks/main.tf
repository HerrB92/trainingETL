# ── Databricks Workspace (Azure resource, always created) ─────
# SKU must be "premium" — "standard" was deprecated by Azure in 2024.
resource "azurerm_databricks_workspace" "main" {
  name                = "dbw-${var.prefix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "premium"

  tags = var.tags
}

# ── Phase-2 resources (only when workspace URL + PAT are provided) ──
#
# Terraform can't connect to the Databricks API until the workspace exists
# and a Personal Access Token has been created inside it.
# Setting phase2 = false (Phase 1) skips these resources via count = 0.
# Setting phase2 = true (Phase 2) creates them.
#
# Phase 1: databricks_host = ""  → var.phase2 = false → count = 0 (skipped)
# Phase 2: databricks_host = "https://..." → var.phase2 = true → count = 1

locals {
  p2 = var.phase2 ? 1 : 0
}

# ── SQL Warehouse ────────────────────────────────────────────
resource "databricks_sql_endpoint" "main" {
  count            = local.p2
  name             = "${var.prefix}-warehouse"
  cluster_size     = "2X-Small"
  max_num_clusters = 1
  auto_stop_mins   = 10

  enable_serverless_compute = true

  tags {
    custom_tags {
      key   = "Environment"
      value = var.prefix
    }
  }
}

# ── Secret Scope ─────────────────────────────────────────────
resource "databricks_secret_scope" "main" {
  count = local.p2
  name  = "kv-scope"
}
