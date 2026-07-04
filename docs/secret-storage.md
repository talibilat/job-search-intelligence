# Secret Storage

JobTracker stores OAuth tokens and provider API keys through the backend `SecretStore` protocol.
Callers pass non-secret `SecretRef` identifiers and Pydantic `SecretStr` values, so provider code does not choose how secret material is stored.

## Fernet Fallback

Use the Fernet fallback when the OS keyring is unavailable by setting `JOBTRACKER_SECRET_STORE_BACKEND=fernet`.
The fallback writes one encrypted Fernet token per secret under `JOBTRACKER_DATA_DIR/secrets/<kind>/<provider>/<name>.fernet`.
The path components come from `SecretRef` and are not secret values.
The encrypted payload contains the secret value and must not contain plaintext.

`JOBTRACKER_FERNET_KEY_FILE` points to the local Fernet key file.
If that file is missing, the backend generates a key on the first secret write and saves it with private file permissions.
If the key file already exists, the backend reuses it to decrypt previously stored secrets.
If the key is lost, the encrypted secrets cannot be recovered and must be deleted and re-entered through setup.

## Operator Notes

Keep `JOBTRACKER_FERNET_KEY_FILE` and `JOBTRACKER_DATA_DIR/secrets/` out of git.
The repository ignores `.jobtracker/` and `*.key`, but custom locations should also stay outside tracked paths.
Back up the key and encrypted secret files together if you need to preserve local credentials across machines.
For stronger separation, place `JOBTRACKER_FERNET_KEY_FILE` outside `JOBTRACKER_DATA_DIR` and outside the repository.
Do not put API keys, OAuth tokens, passwords, Google OAuth client secrets, Fernet keys, or encrypted secret files in `.env.example` or committed docs.

The fallback encrypts secrets at rest, but anyone with both the encrypted payload and the Fernet key can decrypt them.
Treat the key file as secret material.
Do not print or log `SecretStr.get_secret_value()` results, encrypted payload bytes, or decrypted values.
