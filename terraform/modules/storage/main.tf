resource "azurerm_storage_account" "adls" {
  name                     = "${replace(var.prefix, "-", "")}adls"
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  # Enables Azure Data Lake Storage Gen2 (hierarchical namespace)
  is_hns_enabled = true

  min_tls_version = "TLS1_2"

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }

  tags = var.tags
}

# Delta Lake container hierarchy: bronze / silver / gold / quarantine
resource "azurerm_storage_container" "bronze" {
  name                  = "bronze"
  storage_account_name  = azurerm_storage_account.adls.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "silver" {
  name                  = "silver"
  storage_account_name  = azurerm_storage_account.adls.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "gold" {
  name                  = "gold"
  storage_account_name  = azurerm_storage_account.adls.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "quarantine" {
  name                  = "quarantine"
  storage_account_name  = azurerm_storage_account.adls.name
  container_access_type = "private"
}

# Lifecycle policy: move data older than 90 days to cool tier
resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.adls.id

  rule {
    name    = "move-old-data-to-cool"
    enabled = true
    filters {
      prefix_match = ["bronze/", "silver/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than = 90
      }
    }
  }
}
