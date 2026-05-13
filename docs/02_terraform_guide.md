# Terraform Guide for Beginners

## What Is Terraform?

Terraform is a tool that lets you describe cloud infrastructure in text files (`.tf` files), then create and manage that infrastructure automatically. Instead of clicking through the Azure Portal to create a storage account, you write:

```hcl
resource "azurerm_storage_account" "adls" {
  name                = "mystorageaccount"
  resource_group_name = "my-resource-group"
  location            = "West Europe"
  account_tier        = "Standard"
  ...
}
```

Then run `terraform apply` and Terraform creates it. If you run it again without changes, nothing happens (Terraform knows what already exists). If you change the name and run again, Terraform deletes the old one and creates the new one.

**Key insight:** Terraform tracks the current state of your infrastructure in a "state file". It compares that state to your `.tf` files and calculates what needs to change.

## Project Structure

```
terraform/
├── providers.tf         Azure + Databricks provider versions
├── backend.tf           Where to store the state file (Azure Storage)
├── main.tf              Root: creates resource group, calls all modules
├── variables.tf         Input variables (like function parameters)
├── outputs.tf           Output values shown after apply (like return values)
└── modules/
    ├── storage/         ADLS Gen2 storage account
    ├── keyvault/        Azure Key Vault
    ├── sql/             Azure SQL Database (serverless)
    └── databricks/      Databricks workspace + cluster
```

**Why modules?** A module is like a function: reusable, takes inputs, returns outputs. The `sql/` module knows how to create a SQL database; `main.tf` just calls it with the right parameters.

## Installation

```bash
# macOS
brew tap hashicorp/tap
brew install hashicorp/tap/terraform

# Windows (PowerShell, with winget)
winget install Hashicorp.Terraform

# Verify
terraform version
# Terraform v1.7.5
```

Also install the Azure CLI:
```bash
# macOS
brew install azure-cli

# Windows
winget install Microsoft.AzureCLI
```

## Authentication

Terraform needs to authenticate to Azure. For local development, the simplest method is:

```bash
# Log in with your browser
az login

# Set the active subscription
az account set --subscription "your-subscription-id"

# Verify
az account show
```

For GitHub Actions (CI/CD), the project uses **OIDC** (OpenID Connect) — GitHub proves its identity to Azure without storing a long-lived secret. This is configured via the `ARM_USE_OIDC = "true"` environment variable in the workflow file.

## One-Time Bootstrap (Before First `terraform init`)

Terraform needs a place to store its state file. We use an Azure Storage account for this. This account must be created manually once — before Terraform can manage anything else.

```bash
# 1. Create a resource group for the state storage
az group create --name rg-terraform-state --location westeurope

# 2. Create a storage account (name must be globally unique — add random suffix)
STATE_ACCOUNT="stterraformstate$(date +%s | tail -c 5)"
az storage account create \
  --name "$STATE_ACCOUNT" \
  --resource-group rg-terraform-state \
  --location westeurope \
  --sku Standard_LRS

# 3. Create the container for the state file
az storage container create \
  --name tfstate \
  --account-name "$STATE_ACCOUNT"

# 4. Note the name
echo "State storage account: $STATE_ACCOUNT"
```

Then update `terraform/backend.tf`:
```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "stterraformstate12345"  # ← your name here
    container_name       = "tfstate"
    key                  = "b2betl.terraform.tfstate"
  }
}
```

## Filling in Variables

Copy `terraform/environments/dev.tfvars` and fill in your values:

```bash
# Get your subscription ID
az account show --query id -o tsv

# Get your tenant ID
az account show --query tenantId -o tsv

# Get your own object ID (needed for Key Vault access policy)
az ad signed-in-user show --query id -o tsv
```

**Important:** Never commit a filled-in `.tfvars` file to Git. The `.gitignore` already excludes `*.tfvars` but allows `example.tfvars`. Keep secrets out of version control.

## The Three Core Commands

### `terraform init`
Downloads the required providers (Azure, Databricks) and connects to the remote state backend. Run this once when you clone the repo, and again when you change provider versions.

```bash
cd terraform/
terraform init
```

### `terraform plan`
Calculates what changes would be made. Shows additions (green `+`), changes (yellow `~`), and deletions (red `-`). **Nothing is created or changed** — this is purely a preview.

```bash
terraform plan -var-file="environments/dev.tfvars"
```

Always read the plan carefully before applying! Look for unexpected deletions especially.

### `terraform apply`
Applies the changes shown in the plan. Asks for confirmation unless you pass `-auto-approve`.

```bash
terraform apply -var-file="environments/dev.tfvars"
# Type 'yes' when prompted
```

### Destroying Resources

To delete all resources managed by Terraform (useful to save costs):

```bash
terraform destroy -var-file="environments/dev.tfvars"
```

**Warning:** This deletes everything, including data in ADLS. Do not run in production.

## After `terraform apply` — Manual Steps

After the first `terraform apply` completes:

1. **Log in to Databricks** using the URL shown in the outputs
2. **Create a Personal Access Token**: User Settings (top right) → Access Tokens → Generate new token
3. **Store it in Key Vault**:
   ```bash
   az keyvault secret set \
     --vault-name <kv-name-from-output> \
     --name databricks-token \
     --value <your-token>
   ```
4. **Run the second apply** to configure the Databricks provider with the token:
   ```bash
   terraform apply \
     -var-file="environments/dev.tfvars" \
     -var="databricks_pat_token=<your-token>"
   ```

## Common Errors

**Error: "State file locked"**
Another Terraform process is running (or crashed). Wait, or remove the lock:
```bash
terraform force-unlock <lock-id>
```

**Error: "Provider not initialised"**
Run `terraform init` again.

**Error: "Resource already exists"**
The resource was created outside Terraform. Import it:
```bash
terraform import azurerm_resource_group.main /subscriptions/<id>/resourceGroups/<name>
```

**Error: "Key Vault soft-deleted"**
If you destroyed and re-created, the old Key Vault is in soft-delete state. Purge it:
```bash
az keyvault purge --name <vault-name>
```

## Understanding the State File

The state file (`b2betl.terraform.tfstate` in Azure Storage) is Terraform's memory. It maps `.tf` resource names to actual Azure resource IDs. If you delete a resource in Azure Portal without using Terraform, Terraform will try to recreate it on next apply (because it thinks it still exists).

**Golden rule:** If Terraform manages a resource, only Terraform should delete it.

## Cost Control

The `monthly_budget_eur` variable (default: €30) sets up an Azure Budget Alert. You'll receive an email at 80% actual spend and 100% forecasted spend.

To manually pause all compute:
- Databricks cluster: auto-terminates after 15 min idle — just stop using it
- SQL Database: auto-pauses after 15 min — just close all connections
- SQL Warehouse: auto-stops after 10 min idle

To completely stop all charges (except storage):
```bash
# Delete just the compute resources (keep data safe)
terraform destroy -target=module.databricks -var-file="environments/dev.tfvars"
terraform destroy -target=module.sql -var-file="environments/dev.tfvars"
```
