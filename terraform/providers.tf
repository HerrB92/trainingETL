terraform {
  required_version = ">= 1.7"

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
      # Prevent accidental deletion of Key Vault (soft-delete recovery window)
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

# Databricks provider — configured after workspace is created
# host + token are provided via the databricks module output
provider "databricks" {
  host  = module.databricks.workspace_url
  token = var.databricks_pat_token
}
