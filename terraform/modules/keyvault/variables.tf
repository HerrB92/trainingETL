variable "prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "tenant_id" { type = string }
variable "admin_object_id" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
variable "secrets" {
  description = "Map of secret name → value to store in Key Vault"
  type        = map(string)
  sensitive   = true
  default     = {}
}
