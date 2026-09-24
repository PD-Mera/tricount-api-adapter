# Project instructions

## Scope and API contract

- This repository is a small FastAPI adapter for Tricount's unofficial private API. Keep the implementation narrow and follow the local reference in `tricount-api-docs/`.
- Treat confidence labels in `TRICOUNT_PRIVATE_API.md` as meaningful. Prefer `VERIFIED` endpoints; do not present APK-observed or currently absent routes as reliable.
- Preserve unknown upstream response fields where practical. Tricount responses commonly use a `Response` envelope; unwrap only the object needed by the adapter.
- Keep money values as decimal strings from request through upstream serialization. Expenses and their allocations use negative amounts per the local reference.
- For new write routes, document the request and response in `README.md`. Do not send real mutations to Tricount while developing unless the user explicitly asks for that action.

## Credentials and local state

- Keep session tokens, share tokens, app identity, and private keys on the backend. Never add credentials to source control, examples, logs, or error responses.
- `.env` and `tricount-data/` contain local secrets/state. Do not inspect or expose their contents unless needed for the requested task.
- Reuse the persistent device identity in `/data`; do not reset or delete it as part of routine changes.

## Development

- The Docker Compose service bind-mounts the project into `/app` and runs Uvicorn with reload. Python source edits should not require an image rebuild. Rebuild after changing `requirements.txt` or `Dockerfile`.
- Use the Compose port mapping and README when referring to the local URL; do not assume a fixed host port if Compose changes.
- Keep request validation explicit for write endpoints, including the documented string representation for amounts.

## Checks

- Validate Python syntax with `python3 -m py_compile main.py`.
- Validate Compose configuration with `docker compose config --quiet`.
- Avoid live upstream calls for checks that could join tricounts or create, modify, or delete data. Prefer local validation unless the user asks for a live test.
