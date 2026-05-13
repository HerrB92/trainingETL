resource "random_string" "kv_suffix" {
  length  = 4
  special = false
  upper   = false
}

resource "azurerm_key_vault" "main" {
  # Key Vault names must be globally unique and 3-24 chars
  name                = "kv-${var.prefix}-${random_string.kv_suffix.result}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tenant_id           = var.tenant_id
  sku_name            = "standard"

  # Soft-delete protects against accidental deletion (7-day recovery window)
  soft_delete_retention_days = 7
  purge_protection_enabled   = false  # keep false for dev to allow re-creation

  tags = var.tags
}

# Grant the deploying principal (you / the service principal) full admin access
resource "azurerm_key_vault_access_policy" "admin" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = var.tenant_id
  object_id    = var.admin_object_id

  secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover"]
  key_permissions    = ["Get", "List", "Create", "Delete", "Purge"]
}

# Store each secret passed in via var.secrets map
resource "azurerm_key_vault_secret" "secrets" {
  for_each = var.secrets

  name         = each.key
  value        = each.value
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_key_vault_access_policy.admin]
}
