# Remote State Configuration
# ============================================================
# Terraform stores its state (which Azure resources it knows about)
# in a file. Using Azure Storage as the backend means:
#   - Multiple people can work on the same infra safely
#   - State is not lost if your laptop breaks
#   - GitHub Actions can access state during CI/CD
#
# ONE-TIME BOOTSTRAP (before first terraform init):
#
#   # 1. Create a dedicated storage account for Terraform state
#   az group create --name rg-trainetl-terraform-state --location westeurope
#
#   az storage account create \
#     --name stterraformstate$RANDOM \
#     --resource-group rg-trainetl-terraform-state \
#     --location westeurope \
#     --sku Standard_LRS \
#     --min-tls-version TLS1_2
#
#   az storage container create \
#     --name tfstate \
#     --account-name <storage-account-name-from-above>
#
#   # 2. Note the storage account name and update the values below
#   # 3. Run: terraform init
# ============================================================

terraform {
  backend "azurerm" {
    resource_group_name  = "rg-trainetl-terraform-state"
    storage_account_name = "stterraformstate3874"
    container_name       = "tfstate"
    key                  = "b2betl.terraform.tfstate"
  }
}

# For local development / first-time setup without remote state,
# comment out the backend block above and run:
#   terraform init
# This stores state locally in terraform.tfstate (DO NOT COMMIT this file)
