terraform {
  required_version = ">= 1.7, < 2.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.40"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# Azure provider — uses OIDC (GitHub Actions) or az login (local)
# Required environment variables:
#   ARM_CLIENT_ID, ARM_CLIENT_SECRET, ARM_TENANT_ID, ARM_SUBSCRIPTION_ID
provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

# Databricks provider
# Two-phase deployment:
#   Phase 1 (first apply): leave databricks_host = "" → only azurerm resources are created.
#   Phase 2: fill in databricks_host + databricks_pat_token in dev.tfvars,
#             then run terraform apply again → Databricks cluster/warehouse/scope are created.
provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_pat_token
}
