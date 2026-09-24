import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictStr


BASE_URL = os.getenv("TRICOUNT_BASE_URL", "https://api.tricount.bunq.com").rstrip("/")
DEVICE_FILE = Path(os.getenv("TRICOUNT_DEVICE_FILE", "/data/device.json"))
USER_AGENT = os.getenv(
    "TRICOUNT_USER_AGENT",
    "com.bunq.tricount.android:RELEASE:7.0.7:3174:ANDROID:13:C",
)
REQUEST_ID = os.getenv(
    "TRICOUNT_CLIENT_REQUEST_ID",
    "049bfcdf-6ae4-4cee-af7b-45da31ea85d0",
)
CATEGORIES = {
    "registry": [
        "GENERAL",
        "OTHER",
        "TRAVEL",
        "FOOD_AND_DRINK",
        "TRANSPORT",
        "SHOPPING",
        "ENTERTAINMENT",
        "GROCERIES",
    ],
    "entry": [
        "TRAVEL",
        "ENTERTAINMENT",
        "GROCERIES",
        "HEALTHCARE",
        "INSURANCE",
        "RENT_AND_UTILITIES",
        "FOOD_AND_DRINK",
        "SHOPPING",
        "TRANSPORT",
        "OTHER",
        "UNCATEGORIZED",
    ],
    "custom_entry_category_field": "category_custom",
}


class EntryAmount(BaseModel):
    model_config = ConfigDict(extra="allow")

    value: StrictStr
    currency: StrictStr = Field(min_length=3, max_length=3)


class EntryAllocation(BaseModel):
    model_config = ConfigDict(extra="allow")

    membership_uuid: str
    amount: EntryAmount
    type: Literal["AMOUNT", "RATIO"]
    share_ratio: int | None = None
    amount_local: EntryAmount | None = None


class EntryPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    uuid: StrictStr | None = None
    description: str
    amount: EntryAmount
    membership_uuid_owner: str
    allocations: list[EntryAllocation]
    type_transaction: Literal["NORMAL", "INCOME", "BALANCE"]
    status: str
    date: str


class EntryCreate(EntryPayload):
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type_transaction: Literal["NORMAL", "INCOME", "BALANCE"] = "NORMAL"
    status: str = "ACTIVE"


class ShareTokenRequest(BaseModel):
    share_token: StrictStr | None = None
    share_tokens: list[StrictStr] | None = None


def _read_or_create_device() -> tuple[str, str, str]:
    """Return the persistent app ID, private key PEM, and public key PEM."""
    DEVICE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if DEVICE_FILE.exists():
        device = json.loads(DEVICE_FILE.read_text(encoding="utf-8"))
        app_id = device["app_id"]
        private_key_pem = device["private_key_pem"].encode("utf-8")
        private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        app_id = str(uuid.uuid4())
        device = {
            "app_id": app_id,
            "private_key_pem": private_key_pem.decode("utf-8"),
        }
        temporary_file = DEVICE_FILE.with_suffix(".tmp")
        temporary_file.write_text(json.dumps(device), encoding="utf-8")
        temporary_file.chmod(0o600)
        temporary_file.replace(DEVICE_FILE)

    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return app_id, private_key_pem.decode("utf-8"), public_key_pem.decode("utf-8")


def _unwrap(payload: dict[str, Any], object_name: str) -> list[dict[str, Any]]:
    objects = []
    for item in payload.get("Response", []):
        if isinstance(item, dict) and isinstance(item.get(object_name), dict):
            objects.append(item[object_name])
    return objects


def _unwrap_prefix(payload: dict[str, Any], object_prefix: str) -> list[dict[str, Any]]:
    objects = []
    for item in payload.get("Response", []):
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key.startswith(object_prefix) and isinstance(value, dict):
                objects.append(value)
    return objects


class TricountClient:
    def __init__(self) -> None:
        self.app_id, self.private_key_pem, self.public_key_pem = _read_or_create_device()
        self.http = httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(20.0))
        self.session_token: str | None = None
        self.user_id: int | None = None
        self.session_lock = asyncio.Lock()
        self.synced_share_tokens: set[str] = set()

    async def close(self) -> None:
        await self.http.aclose()

    def _common_headers(self) -> dict[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "app-id": self.app_id,
            "X-Bunq-Client-Request-Id": REQUEST_ID,
            "Content-Type": "application/json",
        }

    async def _install_session_locked(self) -> None:
        try:
            response = await self.http.post(
                "/v1/session-registry-installation",
                headers=self._common_headers(),
                json={
                    "app_installation_uuid": self.app_id,
                    "client_public_key": self.public_key_pem,
                    "device_description": "Android",
                },
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="Timed out while creating Tricount session") from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail="Could not reach Tricount API") from exc

        if response.is_error:
            raise HTTPException(
                status_code=502,
                detail=f"Tricount session installation failed with HTTP {response.status_code}",
            )

        try:
            envelope = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Tricount returned an invalid session response") from exc

        token = None
        user_id = None
        for item in envelope.get("Response", []):
            if "Token" in item:
                token = item["Token"].get("token")
            if "UserPerson" in item:
                user_id = item["UserPerson"].get("id")

        if not token or user_id is None:
            raise HTTPException(status_code=502, detail="Tricount session response did not include token and user ID")

        self.session_token = token
        self.user_id = int(user_id)

    async def _ensure_session(self) -> None:
        if self.session_token and self.user_id is not None:
            return
        async with self.session_lock:
            if not self.session_token or self.user_id is None:
                await self._install_session_locked()

    async def _renew_session_after_unauthorized(self, failed_token: str) -> None:
        async with self.session_lock:
            # A concurrent request may already have installed a fresh session.
            if self.session_token == failed_token:
                self.session_token = None
                self.user_id = None
                await self._install_session_locked()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self._ensure_session()

        for attempt in range(2):
            token = self.session_token
            if token is None:
                await self._ensure_session()
                token = self.session_token
            headers = {
                **self._common_headers(),
                "X-Bunq-Client-Authentication": token or "",
            }
            try:
                response = await self.http.request(
                    method,
                    path,
                    params=params,
                    headers=headers,
                    json=json_body,
                )
            except httpx.TimeoutException as exc:
                raise HTTPException(status_code=504, detail="Tricount API request timed out") from exc
            except httpx.RequestError as exc:
                raise HTTPException(status_code=502, detail="Could not reach Tricount API") from exc

            if response.status_code == 401 and attempt == 0:
                await self._renew_session_after_unauthorized(token or "")
                continue
            if response.is_error:
                status_code = response.status_code if 400 <= response.status_code < 500 else 502
                detail = f"Tricount API returned HTTP {response.status_code}"
                if response.status_code == 404 and response.text.strip():
                    upstream_message = " ".join(response.text.split())[:300]
                    detail = f"{detail}: {upstream_message}"
                raise HTTPException(
                    status_code=status_code,
                    detail=detail,
                )
            if response.status_code == 204 or not response.content:
                return {}
            try:
                return response.json()
            except ValueError as exc:
                raise HTTPException(status_code=502, detail="Tricount returned invalid JSON") from exc

        raise HTTPException(status_code=502, detail="Tricount authentication failed after retry")

    async def list_registries(self, share_tokens: list[str] | None = None) -> list[dict[str, Any]]:
        await self._ensure_session()
        path = f"/v1/user/{self.user_id}/registry"
        if not share_tokens:
            payload = await self._request("GET", path)
            return _unwrap(payload, "Registry")

        # The documented list endpoint accepts one share token per request.
        # Query each configured token and merge results by registry ID.
        registries_by_id: dict[int, dict[str, Any]] = {}
        registries_without_id: list[dict[str, Any]] = []
        for share_token in share_tokens:
            payload = await self._request(
                "GET",
                path,
                params={"public_identifier_token": share_token},
            )
            for registry in _unwrap(payload, "Registry"):
                registry_id = registry.get("id")
                if registry_id is None:
                    registries_without_id.append(registry)
                else:
                    registries_by_id[int(registry_id)] = registry

        return [*registries_by_id.values(), *registries_without_id]

    async def get_registry(self, registry_id: int) -> dict[str, Any]:
        await self._ensure_session()
        path = f"/v1/user/{self.user_id}/registry"
        registry = None

        # Prefer the documented list endpoint's registry_id filter. The direct
        # /registry/{id} route has returned 404 on some API versions.
        try:
            payload = await self._request(
                "GET",
                path,
                params={"registry_id": str(registry_id)},
            )
            registry = next(
                (
                    item
                    for item in _unwrap(payload, "Registry")
                    if str(item.get("id")) == str(registry_id)
                ),
                None,
            )
        except HTTPException as exc:
            if exc.status_code != 404:
                raise

        # Some responses ignore registry_id. Search the configured token
        # results (or this device's full list) as a fallback.
        if registry is None:
            registry = next(
                (
                    item
                    for item in await self.list_registries()
                    if str(item.get("id")) == str(registry_id)
                ),
                None,
            )

        if registry is None:
            raise HTTPException(status_code=404, detail=f"Tricount {registry_id} not found")
        return registry

    async def list_entries(self, registry_id: int) -> list[dict[str, Any]]:
        registry = await self.get_registry(registry_id)
        entries = []
        for item in registry.get("all_registry_entry", []):
            if isinstance(item, dict) and isinstance(item.get("RegistryEntry"), dict):
                entries.append(item["RegistryEntry"])
            elif isinstance(item, dict):
                entries.append(item)
        return entries

    async def get_entry(self, registry_id: int, entry_id: int) -> dict[str, Any]:
        for entry in await self.list_entries(registry_id):
            if str(entry.get("id")) == str(entry_id):
                return entry
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found in tricount {registry_id}")

    async def _ensure_registry_synced(self, registry_id: int) -> None:
        registry = await self.get_registry(registry_id)
        share_token = registry.get("public_identifier_token")
        if share_token:
            await self._sync_shared_registry(str(share_token))

    async def create_entry(self, registry_id: int, entry: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_session()
        await self._ensure_registry_synced(registry_id)
        if not entry.get("uuid"):
            entry["uuid"] = str(uuid.uuid4())

        payload = await self._request(
            "POST",
            f"/v1/user/{self.user_id}/registry/{registry_id}/registry-entry",
            json_body=entry,
        )
        created_ids = _unwrap(payload, "Id")
        return created_ids[0] if created_ids else payload

    async def update_entry(
        self,
        registry_id: int,
        entry_id: int,
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        await self._ensure_session()
        await self._ensure_registry_synced(registry_id)
        payload = await self._request(
            "PUT",
            f"/v1/user/{self.user_id}/registry/{registry_id}/registry-entry/{entry_id}",
            json_body=entry,
        )
        updated_ids = _unwrap(payload, "Id")
        return updated_ids[0] if updated_ids else payload

    async def delete_entry(self, registry_id: int, entry_id: int) -> dict[str, Any]:
        await self._ensure_session()
        await self._ensure_registry_synced(registry_id)
        payload = await self._request(
            "DELETE",
            f"/v1/user/{self.user_id}/registry/{registry_id}/registry-entry/{entry_id}",
        )
        deleted_ids = _unwrap(payload, "Id")
        return deleted_ids[0] if deleted_ids else {"id": entry_id, "deleted": True}

    async def list_members(self, registry_id: int) -> list[dict[str, Any]]:
        await self._ensure_session()
        await self._ensure_registry_synced(registry_id)
        payload = await self._request(
            "GET",
            f"/v1/user/{self.user_id}/registry/{registry_id}/registry-membership",
        )
        return _unwrap_prefix(payload, "RegistryMembership")

    async def get_profile(self) -> dict[str, Any]:
        await self._ensure_session()
        payload = await self._request("GET", f"/v1/user/{self.user_id}")
        profiles = _unwrap(payload, "UserPerson")
        if not profiles:
            raise HTTPException(status_code=502, detail="Tricount profile response did not include UserPerson")
        return profiles[0]

    async def get_exchange_rates(self, currency: str) -> list[dict[str, Any]]:
        await self._ensure_session()
        payload = await self._request(
            "GET",
            f"/v1/user/{self.user_id}/exchange-rate",
            params={"currency": currency.upper()},
        )
        return _unwrap(payload, "ExchangeRate")

    async def _sync_shared_registry(self, share_token: str) -> None:
        if share_token in self.synced_share_tokens:
            return
        await self._request(
            "POST",
            f"/v1/user/{self.user_id}/registry-synchronization",
            json_body={
                "all_registry_active": [{"public_identifier_token": share_token}],
                "all_registry_archived": [],
                "all_registry_deleted": [],
            },
        )
        self.synced_share_tokens.add(share_token)

    async def sync_shared_registry(self, share_token: str) -> dict[str, Any]:
        await self._ensure_session()
        share_token = share_token.strip()
        if not share_token:
            raise HTTPException(status_code=422, detail="share_token must not be empty")
        await self._sync_shared_registry(share_token)
        registries = await self.list_registries([share_token])
        if not registries:
            raise HTTPException(status_code=404, detail="No tricount found for this share token")
        registry = registries[0]
        return {
            "id": registry.get("id"),
            "name": registry.get("title"),
            "currency": registry.get("currency"),
            "emoji": registry.get("emoji"),
            "status": registry.get("status"),
        }

    async def sync_shared_registries(self, share_tokens: list[str]) -> dict[str, Any]:
        await self._ensure_session()
        items = []
        errors = []
        seen_tokens: set[str] = set()
        seen_registry_ids: set[str] = set()

        for index, raw_token in enumerate(share_tokens):
            token = raw_token.strip()
            if not token:
                errors.append({"index": index, "status_code": 422, "message": "Share token is empty"})
                continue
            if token in seen_tokens:
                continue
            seen_tokens.add(token)

            try:
                registry = await self.sync_shared_registry(token)
            except HTTPException as exc:
                errors.append({
                    "index": index,
                    "status_code": exc.status_code,
                    "message": "Could not sync share token",
                })
                continue

            registry_id = str(registry.get("id"))
            if registry_id not in seen_registry_ids:
                seen_registry_ids.add(registry_id)
                items.append(registry)

        return {"items": items, "errors": errors}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.tricount = TricountClient()
    yield
    await app.state.tricount.close()


app = FastAPI(
    title="Tricount API Adapter",
    description="Local adapter for tricounts, members, entry CRUD, categories, exchange rates, and profile data.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/profile")
async def get_profile() -> dict[str, Any]:
    return await app.state.tricount.get_profile()


@app.get("/exchange-rates")
async def get_exchange_rates(currency: str = Query(min_length=3, max_length=3)) -> list[dict[str, Any]]:
    return await app.state.tricount.get_exchange_rates(currency)


@app.get("/metadata/categories")
async def get_categories() -> dict[str, Any]:
    return CATEGORIES


@app.get("/tricounts")
async def list_tricounts() -> list[dict[str, Any]]:
    """List this device's tricounts, or filter by the configured share token."""
    return await app.state.tricount.list_registries()


@app.post("/tricounts/sync")
async def sync_tricount(request: ShareTokenRequest) -> dict[str, Any]:
    if request.share_token is not None and request.share_tokens is not None:
        raise HTTPException(status_code=422, detail="Send either share_token or share_tokens, not both")
    if request.share_token is not None:
        return await app.state.tricount.sync_shared_registry(request.share_token)
    if request.share_tokens is not None:
        return await app.state.tricount.sync_shared_registries(request.share_tokens)
    raise HTTPException(status_code=422, detail="Provide share_token or share_tokens")


@app.get("/tricounts/summary")
async def list_tricount_summaries() -> list[dict[str, Any]]:
    registries = await app.state.tricount.list_registries()
    return [
        {
            "id": registry.get("id"),
            "name": registry.get("title"),
            "currency": registry.get("currency"),
            "emoji": registry.get("emoji"),
            "status": registry.get("status"),
        }
        for registry in registries
        if registry.get("id") is not None
    ]


@app.get("/tricounts/{registry_id}")
async def get_tricount(registry_id: int) -> dict[str, Any]:
    return await app.state.tricount.get_registry(registry_id)


@app.get("/tricounts/{registry_id}/entries")
async def list_entries(registry_id: int) -> list[dict[str, Any]]:
    return await app.state.tricount.list_entries(registry_id)


@app.get("/tricounts/{registry_id}/members")
async def list_members(registry_id: int) -> list[dict[str, Any]]:
    return await app.state.tricount.list_members(registry_id)


@app.get("/tricounts/{registry_id}/entries/{entry_id}")
async def get_entry(registry_id: int, entry_id: int) -> dict[str, Any]:
    return await app.state.tricount.get_entry(registry_id, entry_id)


@app.post("/tricounts/{registry_id}/entries")
async def create_entry(registry_id: int, entry: EntryCreate) -> dict[str, Any]:
    return await app.state.tricount.create_entry(
        registry_id,
        entry.model_dump(exclude_none=True),
    )


@app.put("/tricounts/{registry_id}/entries/{entry_id}")
async def update_entry(registry_id: int, entry_id: int, entry: EntryPayload) -> dict[str, Any]:
    return await app.state.tricount.update_entry(
        registry_id,
        entry_id,
        entry.model_dump(exclude_none=True),
    )


@app.delete("/tricounts/{registry_id}/entries/{entry_id}")
async def delete_entry(registry_id: int, entry_id: int) -> dict[str, Any]:
    return await app.state.tricount.delete_entry(registry_id, entry_id)
