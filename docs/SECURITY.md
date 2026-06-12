# Secrets & security posture

## Current state (dev)
Secrets load from environment variables via pydantic-settings. Locally that
means `.env` (gitignored); in Kubernetes, a standard `Secret` (`avatarforge-secrets`)
injected with `envFrom`. No secret ever lives in code, images, or manifests —
`02-secret.example.yaml` is a template, the real file is gitignored.

## Production path (AKS + Azure Key Vault)
The env-var indirection makes the Key Vault upgrade config-only — no code changes:

1. Store `AZURE-OPENAI-API-KEY`, `AZURE-SPEECH-KEY`, `OPENAI-API-KEY` in Key Vault.
2. Enable the **Azure Key Vault Provider for Secrets Store CSI Driver** on AKS.
3. Bind pods via **workload identity** (no credentials in cluster at all).
4. Define a `SecretProviderClass` syncing vault objects to the same
   `avatarforge-secrets` Kubernetes Secret name the deployments already reference.

Because the application only ever reads environment variables, swapping the
secret *source* (literal Secret -> CSI-synced Secret) requires zero changes to
deployments or code.

## Other controls in place
- Per-IP rate limiting (slowapi); `5/minute` on video generation (denial-of-wallet guard)
- Non-root container user (`forge`) in API/worker images
- Path-traversal guard on media file serving
- SSML escaping (XML injection) on TTS input
- Image upload validation (type, dimensions, size) before any processing
- Read-only SQL posture: app DB user owns only its own schema

## Known gaps (documented scope boundary)
Authentication/authorization, TLS termination, network policies, and audit-log
shipping are deliberately out of scope for this portfolio build — see the
"Production readiness" section in the README.
