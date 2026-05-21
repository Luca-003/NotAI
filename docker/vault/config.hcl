# NotAI - Vault production config (usato solo da compose.prod.yml).
# In dev usiamo `vault server -dev` con root token noto.

ui = true
disable_mlock = false

storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1   # In produzione vera: TLS dietro a Caddy (mTLS interna) o cert qui.
}

api_addr     = "http://vault:8200"
cluster_addr = "http://vault:8201"

# In produzione abilitare unseal automatico con KMS (AWS, GCP, Azure) o usare
# auto-unseal via transit con un Vault peer.
# Esempio (commentato):
# seal "awskms" {
#   region     = "eu-south-1"
#   kms_key_id = "alias/notai-vault-unseal"
# }

# Politica di telemetria
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = true
}
