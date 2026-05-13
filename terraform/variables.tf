variable "project_name" {
  description = "Short name used as prefix for all resources (lowercase, no spaces)"
  type        = string
  default     = "b2betl"
}

variable "environment" {
  description = "Deployment environment: dev, staging, or prod"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod"
  }
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "West Europe"
}

variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
  sensitive   = true
}

variable "tenant_id" {
  description = "Azure Active Directory tenant ID"
  type        = string
  sensitive   = true
}

# Key Vault access — your service principal or user principal object ID
variable "key_vault_admin_object_id" {
  description = "Object ID of the AAD user/SP that gets Key Vault admin access"
  type        = string
  sensitive   = true
}

# SQL Database credentials
variable "sql_admin_username" {
  description = "Administrator username for Azure SQL Server"
  type        = string
  default     = "sqladmin"
}

variable "sql_admin_password" {
  description = "Administrator password for Azure SQL Server (min 12 chars)"
  type        = string
  sensitive   = true
}

# Databricks — Personal Access Token created after first manual login
# Set this after running terraform apply the first time
variable "databricks_pat_token" {
  description = "Databricks Personal Access Token (create in workspace UI after first apply)"
  type        = string
  sensitive   = true
  default     = ""
}

# Existing AI services (not created by Terraform)
variable "ai_services_resource_group" {
  description = "Resource group containing the existing Azure AI services account"
  type        = string
  default     = "train_rsrc_foundry_swe"
}

variable "ai_services_account_name" {
  description = "Name of the existing Azure AI multi-service account"
  type        = string
  default     = "train-bb-ai-services"
}

# Budget alert threshold in EUR
variable "monthly_budget_eur" {
  description = "Monthly budget alert threshold in EUR"
  type        = number
  default     = 30
}

variable "budget_alert_email" {
  description = "Email address for budget alerts"
  type        = string
  default     = "b.behrens@btech.de"
}
