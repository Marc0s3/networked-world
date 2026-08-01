#!/usr/bin/env python3
"""Networked World v1.0.1 local server and read-only API proxy.

The browser cannot call api.networked.art directly because of its CORS policy.
This tiny server exposes only the fixed public routes required by the explorer,
normalizes artist works, settled-auction winners, patrons, and profile identity,
and serves the static application from the same local origin.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

UPSTREAM = "https://api.networked.art"
USER_AGENT = "NetworkedWorld/1.0.1 (+https://github.com/Marc0s3/networked-world)"
ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
TOKEN_RE = re.compile(r"^[0-9]{1,78}$")
CACHE_TTL = 120
MAX_PAGES = 50
PER_PAGE = 100
MAX_WORKS = 5000


@dataclass
class CacheEntry:
    expires_at: float
    value: Any


CACHE: dict[str, CacheEntry] = {}
CACHE_LOCK = threading.Lock()


def cached_json(url: str, ttl: int = CACHE_TTL) -> Any:
    now = time.time()
    with CACHE_LOCK:
        entry = CACHE.get(url)
        if entry and entry.expires_at > now:
            return entry.value
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            value = json.loads(body.decode(charset, errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Upstream HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Upstream unavailable: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Upstream returned invalid JSON") from exc
    with CACHE_LOCK:
        CACHE[url] = CacheEntry(now + ttl, value)
    return value


def optional_json(url: str, ttl: int = CACHE_TTL) -> Any:
    try:
        return cached_json(url, ttl=ttl)
    except RuntimeError:
        return None


def payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "items", "collections", "tokens"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def payload_meta(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    for key in ("metadata", "meta", "pageInfo"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def validate_account(account: str) -> str:
    account = urllib.parse.unquote(account).strip()
    if not ACCOUNT_RE.fullmatch(account):
        raise ValueError("Invalid account, ENS, handle, or address")
    return account


def validate_collection(collection: str) -> str:
    collection = urllib.parse.unquote(collection).strip().lower()
    if not ADDRESS_RE.fullmatch(collection):
        raise ValueError("Invalid collection address")
    return collection


def validate_token(token_id: str) -> str:
    token_id = urllib.parse.unquote(token_id).strip()
    if not TOKEN_RE.fullmatch(token_id):
        raise ValueError("Invalid token id")
    return token_id


def get_all_collections(account: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        query = urllib.parse.urlencode({"page": page, "per_page": PER_PAGE})
        url = f"{UPSTREAM}/users/{urllib.parse.quote(account, safe='')}/collections?{query}"
        payload = cached_json(url)
        items = payload_items(payload)
        output.extend(items)
        meta = payload_meta(payload)
        current = to_int(meta.get("currentPage") or meta.get("current_page"))
        last = to_int(meta.get("lastPage") or meta.get("last_page"))
        if current is not None and last is not None and current >= last:
            break
        if len(items) < PER_PAGE or not items:
            break
    return output


def token_is_edition(token: dict[str, Any]) -> bool:
    standard = str(token.get("standard") or "").lower()
    supply = to_int(token.get("supply") or token.get("total_supply") or 1) or 1
    return "1155" in standard or supply > 1


def collection_is_native_work_source(collection: dict[str, Any]) -> bool:
    kind = str(collection.get("kind") or "").lower()
    return kind not in {"external", "patron_edition"}


def get_all_tokens(collection: dict[str, Any], account: str) -> list[dict[str, Any]]:
    slug = str(collection.get("slug") or collection.get("address") or "").strip()
    if not slug:
        return []
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor: str | None = None
    for page in range(1, MAX_PAGES + 1):
        params: dict[str, Any] = {"account": account, "per_page": PER_PAGE}
        if cursor:
            params["cursor"] = cursor
        else:
            params["page"] = page
        url = (
            f"{UPSTREAM}/collections/{urllib.parse.quote(slug, safe='')}/tokens?"
            f"{urllib.parse.urlencode(params)}"
        )
        payload = cached_json(url)
        items = payload_items(payload)
        for token in items:
            contract = str(token.get("collection") or collection.get("address") or "").lower()
            token_id = str(token.get("token_id") or token.get("tokenId") or token.get("id") or "")
            key = f"{contract}:{token_id}"
            if contract and token_id and key not in seen:
                seen.add(key)
                output.append(token)
                if len(output) >= MAX_WORKS:
                    return output
        meta = payload_meta(payload)
        next_cursor = meta.get("nextCursor") or meta.get("next_cursor")
        if isinstance(next_cursor, str) and next_cursor:
            cursor = next_cursor
            continue
        current = to_int(meta.get("currentPage") or meta.get("current_page"))
        last = to_int(meta.get("lastPage") or meta.get("last_page"))
        external_inventory = any(k in meta for k in ("inventorySource", "inventoryStatus", "nextCursor"))
        if last is not None and current is not None and current >= last:
            break
        if external_inventory or len(items) < PER_PAGE or not items:
            break
    return output


def normalize_collection(collection: dict[str, Any]) -> dict[str, Any]:
    address = str(collection.get("address") or "").lower()
    slug = str(collection.get("slug") or address)
    kind = str(collection.get("kind") or "") or None
    protocol = str(collection.get("protocol") or "") or None
    creator = str(collection.get("creator") or "").lower() or None
    return {
        "address": address,
        "slug": slug,
        "name": collection.get("name") or slug or address,
        "description": collection.get("description"),
        "creatorAddress": creator,
        "kind": kind,
        "protocol": protocol,
        "proof": {
            "source": "networked-profile-collections",
            "classification": "native" if str(protocol or "").lower() == "networked" else "custom-or-legacy",
        },
    }


def normalize_work(token: dict[str, Any], collection: dict[str, Any], account: str) -> dict[str, Any] | None:
    contract = str(token.get("collection") or collection.get("address") or "").lower()
    token_id = str(token.get("token_id") or token.get("tokenId") or token.get("id") or "")
    if not ADDRESS_RE.fullmatch(contract) or not TOKEN_RE.fullmatch(token_id):
        return None
    if str(collection.get("kind") or "").lower() != "external" and token_is_edition(token):
        return None
    creator = str(token.get("creator") or collection.get("creator") or "").lower() or None
    return {
        "id": f"{contract}:{token_id}",
        "contract": contract,
        "tokenId": token_id,
        "collectionAddress": contract,
        "collectionSlug": collection.get("slug") or contract,
        "collectionName": collection.get("name") or collection.get("slug") or contract,
        "creatorAddress": creator,
        "routeAccount": account,
        "standard": token.get("standard") or collection.get("standard"),
        "mintedAt": token.get("minted_at"),
        "mintTxHash": token.get("mint_tx_hash"),
        "isNsfw": token.get("is_nsfw") is True,
        "isShadowBanned": token.get("is_shadow_banned") is True,
        "proof": {
            "source": "networked-artist-works-api",
            "collectionKind": collection.get("kind"),
            "collectionProtocol": collection.get("protocol"),
            "upstreamPath": f"/collections/{collection.get('slug') or contract}/tokens?account={account}",
        },
    }


def profile_identity(account: str, fallback_address: str | None) -> dict[str, Any]:
    url = f"{UPSTREAM}/users/{urllib.parse.quote(account, safe='')}/profile"
    payload = optional_json(url, ttl=120)
    root = payload if isinstance(payload, dict) else {}
    user = root.get("user") if isinstance(root.get("user"), dict) else root
    if not isinstance(user, dict):
        user = {}
    address = fallback_address
    for candidate in (
        user.get("address"),
        user.get("wallet_address"),
        user.get("primary_address"),
    ):
        value = str(candidate or "").lower()
        if ADDRESS_RE.fullmatch(value):
            address = value
            break
    display_name = (
        user.get("display_name")
        or user.get("label")
        or user.get("username")
        or user.get("ens_name")
        or account
    )
    counts = root.get("counts") if isinstance(root.get("counts"), dict) else {}
    return {
        "account": user.get("username") or account,
        "address": address,
        "displayName": display_name,
        "avatarUrl": user.get("avatar_url"),
        "bio": user.get("bio"),
        "origin": user.get("origin"),
        "year": user.get("year"),
        "counts": {
            "works": counts.get("works"),
            "collections": counts.get("collections"),
            "collectors": counts.get("collectors"),
            "patrons": counts.get("patrons"),
        },
    }


def build_profile_works(account: str) -> dict[str, Any]:
    collections_raw = get_all_collections(account)
    native_raw = [c for c in collections_raw if collection_is_native_work_source(c)]
    excluded = [c for c in collections_raw if not collection_is_native_work_source(c)]
    collections: list[dict[str, Any]] = []
    works: list[dict[str, Any]] = []
    for collection in native_raw:
        normalized_collection = normalize_collection(collection)
        tokens = get_all_tokens(collection, account)
        normalized_works = [normalize_work(t, collection, account) for t in tokens]
        normalized_works = [w for w in normalized_works if w is not None]
        if not normalized_works:
            continue
        normalized_collection["workCount"] = len(normalized_works)
        collections.append(normalized_collection)
        works.extend(normalized_works)
    identity_address = next(
        (w.get("creatorAddress") for w in works if w.get("creatorAddress")),
        next((c.get("creatorAddress") for c in collections if c.get("creatorAddress")), None),
    )
    identity = profile_identity(account, identity_address)
    return {
        "account": account,
        "identity": identity,
        "collections": collections,
        "works": works,
        "excluded": {
            "externalOrPatronCollections": len(excluded),
            "collectionKinds": sorted({str(c.get("kind") or "unknown") for c in excluded}),
        },
        "proof": {
            "mode": "strict-profile-source",
            "upstream": UPSTREAM,
            "collectionsEndpoint": f"/users/{account}/collections",
            "profileEndpoint": f"/users/{account}/profile",
            "definition": "Artist collections returned by Networked.art, excluding external inventory and patron editions.",
        },
    }


def normalize_person(person: Any) -> dict[str, Any] | None:
    if not isinstance(person, dict):
        return None
    address = str(person.get("address") or "").lower()
    if not ADDRESS_RE.fullmatch(address):
        return None
    return {
        "address": address,
        "label": person.get("label") or person.get("display_name") or person.get("handle") or address,
        "handle": person.get("handle") or person.get("username"),
        "avatarUrl": person.get("avatar_url"),
    }


def auction_winner(raw_token: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    auction = raw_token.get("auction") if isinstance(raw_token.get("auction"), dict) else {}
    status = str(auction.get("status") or "").lower()
    bidder = str(auction.get("bidder") or "").lower()
    if status == "settled" and ADDRESS_RE.fullmatch(bidder):
        winner: dict[str, Any] = {"address": bidder}
        bids = raw_token.get("bids") if isinstance(raw_token.get("bids"), list) else []
        matches = [b for b in bids if isinstance(b, dict) and str(b.get("bidder") or "").lower() == bidder]
        if matches:
            bid = matches[-1]
            winner.update({
                "label": bid.get("bidder_label") or bid.get("bidder_handle") or bidder,
                "handle": bid.get("bidder_handle"),
                "avatar_url": bid.get("bidder_avatar_url"),
            })
        else:
            collector = raw_token.get("collector") if isinstance(raw_token.get("collector"), dict) else {}
            if str(collector.get("address") or "").lower() == bidder:
                winner.update(collector)
        return normalize_person(winner), "settled-auction-bidder"
    collector = normalize_person(raw_token.get("collector"))
    if collector:
        return collector, "collector-fallback"
    return None, None


def dedupe_people(values: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    source = values if isinstance(values, list) else []
    for raw in source:
        person = normalize_person(raw)
        if not person or person["address"] in seen:
            continue
        seen.add(person["address"])
        output.append(person)
    return output


def get_work_detail(account: str, collection: str, token_id: str) -> dict[str, Any]:
    params = urllib.parse.urlencode({"account": account, "include": "offers"})
    detail_url = (
        f"{UPSTREAM}/collections/{urllib.parse.quote(collection, safe='')}/tokens/"
        f"{urllib.parse.quote(token_id, safe='')}?{params}"
    )
    metadata_url = f"{UPSTREAM}/metadata/{collection}/{token_id}"
    payload = cached_json(detail_url, ttl=45)
    raw_token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(raw_token, dict):
        raw_token = payload if isinstance(payload, dict) else {}
    metadata_payload = cached_json(metadata_url, ttl=300)
    metadata = (
        metadata_payload.get("token")
        if isinstance(metadata_payload, dict) and isinstance(metadata_payload.get("token"), dict)
        else metadata_payload
    )
    winner, winner_source = auction_winner(raw_token)
    patrons = dedupe_people(raw_token.get("patrons"))
    auction = raw_token.get("auction") if isinstance(raw_token.get("auction"), dict) else {}
    return {
        "contract": collection,
        "tokenId": token_id,
        "title": metadata.get("name") if isinstance(metadata, dict) else None,
        "description": metadata.get("description") if isinstance(metadata, dict) else None,
        "image": metadata.get("image") if isinstance(metadata, dict) else None,
        "animationUrl": metadata.get("animation_url") if isinstance(metadata, dict) else None,
        "thumbnail": best_thumbnail(metadata),
        "metadata": metadata,
        "metadataStatus": metadata_payload.get("status") if isinstance(metadata_payload, dict) else None,
        "auctionStatus": auction.get("status"),
        "auctionWinner": winner,
        "auctionWinnerSource": winner_source,
        "patrons": patrons,
        "patronCount": len(patrons),
        "history": raw_token.get("events") or [],
        "proof": {
            "source": "networked-token-detail-api",
            "detailPath": f"/collections/{collection}/tokens/{token_id}",
            "metadataPath": f"/metadata/{collection}/{token_id}",
            "winnerSource": winner_source,
            "patronSource": "token.patrons",
        },
    }


def best_thumbnail(metadata: Any) -> str | None:
    if not isinstance(metadata, dict):
        return None
    image = metadata.get("image")
    if isinstance(image, dict):
        for key in ("lg", "md", "sm", "xs", "url"):
            if image.get(key):
                return image[key]
    thumbnails = metadata.get("thumbnail") or metadata.get("thumbnails")
    if isinstance(thumbnails, dict):
        for key in ("lg", "md", "sm", "xs"):
            if thumbnails.get(key):
                return thumbnails[key]
    for key in ("image_url", "image", "animation_url"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


class Handler(SimpleHTTPRequestHandler):
    server_version = "NetworkedWorld/1.0.1"

    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/health":
                self.send_json(200, {"ok": True, "version": "1.0.1"})
                return
            match = re.fullmatch(r"/api/networked/profile/([^/]+)/works", path)
            if match:
                account = validate_account(match.group(1))
                self.send_json(200, build_profile_works(account))
                return
            match = re.fullmatch(r"/api/networked/work/(0x[a-fA-F0-9]{40})/([0-9]+)", path)
            if match:
                query = urllib.parse.parse_qs(parsed.query)
                account = validate_account((query.get("account") or [""])[0])
                collection = validate_collection(match.group(1))
                token_id = validate_token(match.group(2))
                self.send_json(200, get_work_detail(account, collection, token_id))
                return
            super().do_GET()
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except RuntimeError as exc:
            self.send_json(502, {"error": str(exc)})
        except Exception as exc:
            self.send_json(500, {"error": f"Internal proxy error: {exc}"})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="Local port. 0 selects a free port automatically.")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    mimetypes.add_type("application/javascript", ".js")
    handler = lambda *a, **kw: Handler(*a, directory=str(root), **kw)  # noqa: E731
    server = ThreadingHTTPServer((args.host, args.port), handler)
    actual_port = int(server.server_address[1])
    url = f"http://{args.host}:{actual_port}/"
    print(f"Networked World v1.0.1 running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
