const UPSTREAM = 'https://api.networked.art';
const PER_PAGE = 100;
const MAX_PAGES = 50;
const MAX_WORKS = 5000;
const RATE_LIMIT_RETRY_AFTER = 60;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return cors(new Response(null, { status: 204 }));
    if (request.method !== 'GET') return json({ error: 'Method not allowed' }, 405);

    try {
      if (url.pathname === '/api/health') return json({ ok: true, version: '1.0.1' });

      let match = url.pathname.match(/^\/api\/networked\/profile\/([^/]+)\/works$/);
      if (match) {
        const account = validateAccount(decodeURIComponent(match[1]));
        return cachedRoute(
          request,
          ctx,
          120,
          env.PROFILE_RATE_LIMITER,
          rateLimitKey(request, 'profile'),
          () => buildProfileWorks(account)
        );
      }

      match = url.pathname.match(/^\/api\/networked\/work\/(0x[a-fA-F0-9]{40})\/([0-9]+)$/);
      if (match) {
        const account = validateAccount(url.searchParams.get('account') || '');
        const collection = match[1].toLowerCase();
        const tokenId = match[2];
        return cachedRoute(
          request,
          ctx,
          60,
          env.WORK_RATE_LIMITER,
          rateLimitKey(request, 'work'),
          () => getWorkDetail(account, collection, tokenId)
        );
      }

      return json({ error: 'Not found' }, 404);
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : String(error) }, 502);
    }
  }
};

async function cachedRoute(request, ctx, maxAge, limiter, limitKey, producer) {
  const cache = caches.default;
  const key = new Request(request.url, { method: 'GET' });
  const cached = await cache.match(key);
  if (cached) return cors(cached);

  const limited = await rateLimitMiss(limiter, limitKey);
  if (limited) return limited;

  const payload = await producer();
  const response = json(payload, 200, maxAge);
  ctx.waitUntil(cache.put(key, response.clone()));
  return response;
}

function rateLimitKey(request, route) {
  const client = request.headers.get('CF-Connecting-IP') || 'unknown-client';
  return `${route}:${client}`;
}

async function rateLimitMiss(limiter, key) {
  // Wrangler provides the binding in production. Keeping the guard makes local
  // module tests and staged rollouts fail open rather than breaking the app.
  if (!limiter || typeof limiter.limit !== 'function') return null;
  const { success } = await limiter.limit({ key });
  if (success) return null;
  return json(
    { error: 'Too many uncached requests. Please try again shortly.' },
    429,
    0,
    { 'Retry-After': String(RATE_LIMIT_RETRY_AFTER) }
  );
}

function cors(response) {
  const headers = new Headers(response.headers);
  headers.set('Access-Control-Allow-Origin', '*');
  headers.set('Access-Control-Allow-Methods', 'GET, OPTIONS');
  headers.set('Access-Control-Allow-Headers', 'Content-Type');
  headers.set('X-Content-Type-Options', 'nosniff');
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

function json(payload, status = 200, maxAge = 0, extraHeaders = {}) {
  const headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': maxAge ? `public, max-age=${maxAge}` : 'no-store',
    ...extraHeaders
  };
  return cors(new Response(JSON.stringify(payload), { status, headers }));
}

function validateAccount(value) {
  const account = String(value || '').trim();
  if (!/^[A-Za-z0-9_.:-]{1,128}$/.test(account)) throw new Error('Invalid account, ENS, handle, or address');
  return account;
}

async function upstreamJson(path, optional = false) {
  try {
    const response = await fetch(`${UPSTREAM}${path}`, {
      headers: { Accept: 'application/json', 'User-Agent': 'NetworkedWorld/1.0.1' },
      cf: { cacheTtl: 120, cacheEverything: true }
    });
    const text = await response.text();
    let payload;
    try { payload = JSON.parse(text); }
    catch { throw new Error(`Upstream returned invalid JSON (${response.status})`); }
    if (!response.ok) throw new Error(payload?.message || payload?.error || `Upstream HTTP ${response.status}`);
    return payload;
  } catch (error) {
    if (optional) return null;
    throw error;
  }
}

function items(payload) {
  if (Array.isArray(payload)) return payload.filter(x => x && typeof x === 'object');
  for (const key of ['data', 'items', 'collections', 'tokens']) {
    if (Array.isArray(payload?.[key])) return payload[key];
  }
  return [];
}

function meta(payload) {
  for (const key of ['metadata', 'meta', 'pageInfo']) {
    if (payload?.[key] && typeof payload[key] === 'object') return payload[key];
  }
  return {};
}

function intOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

async function allCollections(account) {
  const output = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const payload = await upstreamJson(`/users/${encodeURIComponent(account)}/collections?page=${page}&per_page=${PER_PAGE}`);
    const batch = items(payload);
    output.push(...batch);
    const metadata = meta(payload);
    const current = intOrNull(metadata.currentPage ?? metadata.current_page);
    const last = intOrNull(metadata.lastPage ?? metadata.last_page);
    if ((current !== null && last !== null && current >= last) || batch.length < PER_PAGE || !batch.length) break;
  }
  return output;
}

function isNativeCollection(collection) {
  return !['external', 'patron_edition'].includes(String(collection?.kind || '').toLowerCase());
}

function isEdition(token) {
  return String(token?.standard || '').toLowerCase().includes('1155') || Number(token?.supply ?? token?.total_supply ?? 1) > 1;
}

async function allTokens(collection, account) {
  const slug = String(collection.slug || collection.address || '');
  if (!slug) return [];
  const output = [];
  const seen = new Set();
  let cursor = null;

  for (let page = 1; page <= MAX_PAGES && output.length < MAX_WORKS; page++) {
    const query = new URLSearchParams({ account, per_page: String(PER_PAGE) });
    if (cursor) query.set('cursor', cursor); else query.set('page', String(page));
    const payload = await upstreamJson(`/collections/${encodeURIComponent(slug)}/tokens?${query}`);
    const batch = items(payload);
    for (const token of batch) {
      const contract = String(token.collection || collection.address || '').toLowerCase();
      const tokenId = String(token.token_id ?? token.tokenId ?? token.id ?? '');
      const key = `${contract}:${tokenId}`;
      if (contract && tokenId && !seen.has(key)) {
        seen.add(key);
        output.push(token);
      }
    }
    const metadata = meta(payload);
    const next = metadata.nextCursor ?? metadata.next_cursor;
    if (typeof next === 'string' && next) { cursor = next; continue; }
    const current = intOrNull(metadata.currentPage ?? metadata.current_page);
    const last = intOrNull(metadata.lastPage ?? metadata.last_page);
    const externalInventory = ['inventorySource', 'inventoryStatus', 'nextCursor'].some(key => Object.hasOwn(metadata, key));
    if ((current !== null && last !== null && current >= last) || externalInventory || batch.length < PER_PAGE || !batch.length) break;
  }
  return output;
}

function normalizeCollection(collection) {
  const address = String(collection.address || '').toLowerCase();
  const slug = String(collection.slug || address);
  const protocol = collection.protocol || null;
  return {
    address,
    slug,
    name: collection.name || slug || address,
    description: collection.description || null,
    creatorAddress: String(collection.creator || '').toLowerCase() || null,
    kind: collection.kind || null,
    protocol,
    proof: {
      source: 'networked-profile-collections',
      classification: String(protocol || '').toLowerCase() === 'networked' ? 'native' : 'custom-or-legacy'
    }
  };
}

function normalizeWork(token, collection, account) {
  const contract = String(token.collection || collection.address || '').toLowerCase();
  const tokenId = String(token.token_id ?? token.tokenId ?? token.id ?? '');
  if (!/^0x[a-f0-9]{40}$/.test(contract) || !/^[0-9]{1,78}$/.test(tokenId)) return null;
  if (String(collection.kind || '').toLowerCase() !== 'external' && isEdition(token)) return null;
  return {
    id: `${contract}:${tokenId}`,
    contract,
    tokenId,
    collectionAddress: contract,
    collectionSlug: collection.slug || contract,
    collectionName: collection.name || collection.slug || contract,
    creatorAddress: String(token.creator || collection.creator || '').toLowerCase() || null,
    routeAccount: account,
    standard: token.standard || collection.standard || null,
    mintedAt: token.minted_at || null,
    mintTxHash: token.mint_tx_hash || null,
    isNsfw: token.is_nsfw === true,
    isShadowBanned: token.is_shadow_banned === true,
    proof: {
      source: 'networked-artist-works-api',
      collectionKind: collection.kind || null,
      collectionProtocol: collection.protocol || null,
      upstreamPath: `/collections/${collection.slug || contract}/tokens?account=${account}`
    }
  };
}

async function profileIdentity(account, fallbackAddress) {
  const payload = await upstreamJson(`/users/${encodeURIComponent(account)}/profile`, true);
  const root = payload && typeof payload === 'object' ? payload : {};
  const user = root.user && typeof root.user === 'object' ? root.user : root;
  let address = fallbackAddress;
  for (const candidate of [user.address, user.wallet_address, user.primary_address]) {
    const value = String(candidate || '').toLowerCase();
    if (/^0x[a-f0-9]{40}$/.test(value)) { address = value; break; }
  }
  const counts = root.counts && typeof root.counts === 'object' ? root.counts : {};
  return {
    account: user.username || account,
    address,
    displayName: user.display_name || user.label || user.username || user.ens_name || account,
    avatarUrl: user.avatar_url || null,
    bio: user.bio || null,
    origin: user.origin || null,
    year: user.year || null,
    counts: {
      works: counts.works ?? null,
      collections: counts.collections ?? null,
      collectors: counts.collectors ?? null,
      patrons: counts.patrons ?? null
    }
  };
}

async function buildProfileWorks(account) {
  const all = await allCollections(account);
  const native = all.filter(isNativeCollection);
  const excluded = all.filter(collection => !isNativeCollection(collection));
  const collections = [];
  const works = [];

  for (const collection of native) {
    const tokens = await allTokens(collection, account);
    const normalizedWorks = tokens.map(token => normalizeWork(token, collection, account)).filter(Boolean);
    if (!normalizedWorks.length) continue;
    const normalizedCollection = normalizeCollection(collection);
    normalizedCollection.workCount = normalizedWorks.length;
    collections.push(normalizedCollection);
    works.push(...normalizedWorks);
  }

  const fallbackAddress = works.find(work => work.creatorAddress)?.creatorAddress || collections.find(collection => collection.creatorAddress)?.creatorAddress || null;
  const identity = await profileIdentity(account, fallbackAddress);
  return {
    account,
    identity,
    collections,
    works,
    excluded: {
      externalOrPatronCollections: excluded.length,
      collectionKinds: [...new Set(excluded.map(collection => String(collection.kind || 'unknown')))].sort()
    },
    proof: {
      mode: 'strict-profile-source',
      upstream: UPSTREAM,
      collectionsEndpoint: `/users/${account}/collections`,
      profileEndpoint: `/users/${account}/profile`,
      definition: 'Artist collections returned by Networked.art, excluding external inventory and patron editions.'
    }
  };
}

function person(value) {
  if (!value || typeof value !== 'object') return null;
  const address = String(value.address || '').toLowerCase();
  if (!/^0x[a-f0-9]{40}$/.test(address)) return null;
  return {
    address,
    label: value.label || value.display_name || value.handle || address,
    handle: value.handle || value.username || null,
    avatarUrl: value.avatar_url || null
  };
}

function auctionWinner(token) {
  const auction = token?.auction && typeof token.auction === 'object' ? token.auction : {};
  const status = String(auction.status || '').toLowerCase();
  const bidder = String(auction.bidder || '').toLowerCase();
  if (status === 'settled' && /^0x[a-f0-9]{40}$/.test(bidder)) {
    const bids = Array.isArray(token.bids) ? token.bids : [];
    const matching = bids.filter(bid => bid && typeof bid === 'object' && String(bid.bidder || '').toLowerCase() === bidder);
    const last = matching.at(-1);
    const raw = {
      address: bidder,
      label: last?.bidder_label || last?.bidder_handle || bidder,
      handle: last?.bidder_handle || null,
      avatar_url: last?.bidder_avatar_url || null
    };
    if (!last && String(token.collector?.address || '').toLowerCase() === bidder) Object.assign(raw, token.collector);
    return [person(raw), 'settled-auction-bidder'];
  }
  const fallback = person(token?.collector);
  return fallback ? [fallback, 'collector-fallback'] : [null, null];
}

function dedupePeople(values) {
  const output = [];
  const seen = new Set();
  for (const value of Array.isArray(values) ? values : []) {
    const normalized = person(value);
    if (!normalized || seen.has(normalized.address)) continue;
    seen.add(normalized.address);
    output.push(normalized);
  }
  return output;
}

function bestThumbnail(metadata) {
  if (!metadata || typeof metadata !== 'object') return null;
  for (const source of [metadata.image, metadata.thumbnail, metadata.thumbnails]) {
    if (source && typeof source === 'object') {
      for (const key of ['lg', 'md', 'sm', 'xs', 'url']) if (source[key]) return source[key];
    }
  }
  for (const key of ['image_url', 'image', 'animation_url']) {
    if (typeof metadata[key] === 'string' && metadata[key]) return metadata[key];
  }
  return null;
}

async function getWorkDetail(account, collection, tokenId) {
  const query = new URLSearchParams({ account, include: 'offers' });
  const [detail, metadataPayload] = await Promise.all([
    upstreamJson(`/collections/${encodeURIComponent(collection)}/tokens/${encodeURIComponent(tokenId)}?${query}`),
    upstreamJson(`/metadata/${collection}/${tokenId}`)
  ]);
  const token = detail?.token && typeof detail.token === 'object' ? detail.token : detail;
  const metadata = metadataPayload?.token && typeof metadataPayload.token === 'object' ? metadataPayload.token : metadataPayload;
  const [winner, winnerSource] = auctionWinner(token || {});
  const patrons = dedupePeople(token?.patrons);
  return {
    contract: collection,
    tokenId,
    title: metadata?.name || null,
    description: metadata?.description || null,
    image: metadata?.image || null,
    animationUrl: metadata?.animation_url || null,
    thumbnail: bestThumbnail(metadata),
    metadata,
    metadataStatus: metadataPayload?.status || null,
    auctionStatus: token?.auction?.status || null,
    auctionWinner: winner,
    auctionWinnerSource: winnerSource,
    patrons,
    patronCount: patrons.length,
    history: token?.events || [],
    proof: {
      source: 'networked-token-detail-api',
      detailPath: `/collections/${collection}/tokens/${tokenId}`,
      metadataPath: `/metadata/${collection}/${tokenId}`,
      winnerSource,
      patronSource: 'token.patrons'
    }
  };
}
