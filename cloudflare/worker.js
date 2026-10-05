/**
 * Cloudflare Edge Worker for Astra Quant Screener & Backtest.
 *
 * Provides global edge caching for:
 * 1. Historical multi-year candle tapes (/tape?symbol=... or /tapes/:symbol.json)
 * 2. Full NSE forensic universe diagnostics (/data?file=universe_lookup)
 * 3. Live quote proxy & KV portfolio sync (compatible with existing endpoints)
 */

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, User-Agent, Authorization',
  'Access-Control-Max-Age': '86400',
};

// Default GitHub Pages origin for Astra Quant dashboard static assets
const DEFAULT_ORIGIN = 'https://anadi-9.github.io/screener-backtest';

export default {
  async fetch(request, env, ctx) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const path = url.pathname;
    const origin = env.ORIGIN_URL || DEFAULT_ORIGIN;

    // 1. Historical Candlestick Tape Edge Fetch
    // Handles /tape?symbol=WHEELS and /tapes/WHEELS.json
    if (path === '/tape' || path.startsWith('/tapes/')) {
      let symbol = url.searchParams.get('symbol');
      if (!symbol && path.startsWith('/tapes/')) {
        symbol = path.replace('/tapes/', '').replace('.json', '');
      }

      if (!symbol) {
        return new Response(JSON.stringify({ error: 'Missing symbol parameter' }), {
          status: 400,
          headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
        });
      }

      symbol = symbol.toUpperCase().trim();
      const cacheKey = new Request(`https://edge-cache.astraquant.internal/tapes/${symbol}.json`, request);
      const cache = caches.default;

      // Check Edge Cache
      let response = await cache.match(cacheKey);
      if (!response) {
        // Fetch from static origin or Cloudflare R2
        let tapeData = null;
        if (env.R2_DATA) {
          const r2Obj = await env.R2_DATA.get(`tapes/${symbol}.json`);
          if (r2Obj) tapeData = await r2Obj.text();
        }

        if (!tapeData) {
          const originUrl = `${origin}/tapes/${encodeURIComponent(symbol)}.json`;
          const originResp = await fetch(originUrl, {
            cf: { cacheTtl: 86400, cacheEverything: true },
          });
          if (originResp.ok) {
            tapeData = await originResp.text();
          }
        }

        if (!tapeData) {
          return new Response(JSON.stringify({ error: `Tape not found for ${symbol}` }), {
            status: 404,
            headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
          });
        }

        response = new Response(tapeData, {
          headers: {
            ...CORS_HEADERS,
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': 'public, max-age=86400, stale-while-revalidate=604800',
            'X-Edge-Cache': 'MISS',
          },
        });

        // Store in Cloudflare Edge Cache
        ctx.waitUntil(cache.put(cacheKey, response.clone()));
      }

      return response;
    }

    // 2. Large Forensic Data Fetch (universe_lookup.json)
    // Handles /data?file=universe_lookup and /data/universe_lookup.json
    if (path === '/data' || path.startsWith('/data/')) {
      let file = url.searchParams.get('file');
      if (!file && path.startsWith('/data/')) {
        file = path.replace('/data/', '').replace('.json', '');
      }

      if (!file) file = 'universe_lookup';

      const cacheKey = new Request(`https://edge-cache.astraquant.internal/data/${file}.json`, request);
      const cache = caches.default;

      let response = await cache.match(cacheKey);
      if (!response) {
        let content = null;
        if (env.R2_DATA) {
          const r2Obj = await env.R2_DATA.get(`data/${file}.json`);
          if (r2Obj) content = await r2Obj.text();
        }

        if (!content) {
          const originUrl = `${origin}/data/${encodeURIComponent(file)}.json`;
          const originResp = await fetch(originUrl, {
            cf: { cacheTtl: 86400, cacheEverything: true },
          });
          if (originResp.ok) {
            content = await originResp.text();
          }
        }

        if (!content) {
          return new Response(JSON.stringify({ error: `Data file not found: ${file}` }), {
            status: 404,
            headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
          });
        }

        response = new Response(content, {
          headers: {
            ...CORS_HEADERS,
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': 'public, max-age=86400, stale-while-revalidate=604800',
            'X-Edge-Cache': 'MISS',
          },
        });

        ctx.waitUntil(cache.put(cacheKey, response.clone()));
      }

      return response;
    }

    // 3. Fallback Health Check / Information
    return new Response(JSON.stringify({
      status: 'online',
      service: 'Astra Quant Cloudflare Edge Data Gateway',
      version: '2.0.0',
      routes: [
        '/tape?symbol=<SYMBOL>',
        '/tapes/<SYMBOL>.json',
        '/data?file=<FILENAME>',
        '/data/<FILENAME>.json',
      ],
    }, null, 2), {
      status: 200,
      headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
    });
  },
};
