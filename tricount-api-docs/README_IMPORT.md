# Import guide

Files:

- `TRICOUNT_PRIVATE_API.md` — human-readable reference.
- `tricount-private-api.openapi.yaml` — OpenAPI 3.1 specification for Swagger UI, Redoc, Postman, Insomnia, Bruno tooling, and client generators.
- `.env.example` — suggested environment variables.

## Postman

Use **Import** and select `tricount-private-api.openapi.yaml`.

Set variables/headers after obtaining a Tricount session:

```text
app-id                         = persistent installation UUID
X-Bunq-Client-Authentication  = Token.token returned by session installation
userId                         = UserPerson.id returned by session installation
```

The initial `POST /v1/session-registry-installation` operation is intentionally unauthenticated.

## Swagger / Redoc

Serve `tricount-private-api.openapi.yaml` directly with your preferred OpenAPI UI.

## Code generation

The specification is suitable as a starting contract for tools such as OpenAPI Generator. Because the upstream API is private and some response objects contain undocumented fields, generated clients should allow additional JSON properties.

## Recommended project boundary

Wrap this private API behind your own service interface instead of letting frontend code call Tricount directly.
