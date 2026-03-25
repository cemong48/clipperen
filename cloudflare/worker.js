// Cloudflare Worker: YouTube Transcript Proxy
// Replicates EXACT method used by youtube-transcript-api v1.2.4:
// 1. Fetch watch page → extract INNERTUBE_API_KEY
// 2. Call innertube /player with ANDROID client + extracted key
// 3. Download captions from the response URLs
//
// Environment Variables:
//   AUTH_KEY = your CF_WORKER_AUTH_KEY_x value

export default {
  async fetch(request, env) {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Auth-Key",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    const authKey = request.headers.get("X-Auth-Key");
    if (!authKey || authKey !== env.AUTH_KEY) {
      return Response.json({ error: "Unauthorized" }, { status: 401, headers: corsHeaders });
    }

    if (request.method !== "POST") {
      return Response.json({ error: "Method not allowed" }, { status: 405, headers: corsHeaders });
    }

    try {
      const body = await request.json();
      const { action, video_id, cookies } = body;

      if (action === "transcript") {
        return await getTranscript(video_id, cookies || "", corsHeaders);
      } else if (action === "playability") {
        return await checkPlayability(video_id, corsHeaders);
      } else {
        return Response.json(
          { error: "Invalid action. Use: transcript, playability" },
          { status: 400, headers: corsHeaders }
        );
      }
    } catch (e) {
      return Response.json({ error: e.message }, { status: 500, headers: corsHeaders });
    }
  },
};


// ─── Transcript Extraction (replicates youtube-transcript-api) ──────

async function getTranscript(videoId, cookieStr, corsHeaders) {
  const errors = [];

  try {
    // ── Step 1: Fetch watch page HTML ───────────────────────────
    const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;
    const fetchHeaders = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    };

    if (cookieStr) {
      fetchHeaders["Cookie"] = cookieStr;
    }

    let html = "";
    let watchResp = await fetch(watchUrl, { headers: fetchHeaders, redirect: "follow" });

    if (!watchResp.ok) {
      errors.push(`watch_page: HTTP ${watchResp.status}`);
    } else {
      html = await watchResp.text();

      // ── Step 2: Handle consent page ────────────────────────────
      if (html.includes('action="https://consent.youtube.com/s"')) {
        // Create consent cookie (SOCS=CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjMwODI5LjA3X3AxGgJlbiACGgYIgJnoBw)
        const consentCookie = "SOCS=CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjMwODI5LjA3X3AxGgJlbiACGgYIgJnoBw";
        const newCookies = cookieStr ? `${cookieStr}; ${consentCookie}` : consentCookie;
        fetchHeaders["Cookie"] = newCookies;

        watchResp = await fetch(watchUrl, { headers: fetchHeaders, redirect: "follow" });
        if (watchResp.ok) {
          html = await watchResp.text();
        } else {
          errors.push(`consent_retry: HTTP ${watchResp.status}`);
        }
      }

      if (html) {
        // ── Step 3: Extract INNERTUBE_API_KEY from HTML ────────────
        const apiKeyMatch = html.match(/"INNERTUBE_API_KEY":\s*"([a-zA-Z0-9_-]+)"/);

        if (!apiKeyMatch) {
          errors.push("watch_page: INNERTUBE_API_KEY not found in HTML");

          // Fallback: try to extract captions directly from ytInitialPlayerResponse
          const playerMatch = html.match(/var\s+ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;\s*var/s)
            || html.match(/ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;/s);
          if (playerMatch) {
            const result = await extractCaptionsFromPlayerData(JSON.parse(playerMatch[1]), videoId, corsHeaders);
            if (result) return result;
            errors.push("fallback: no captions in ytInitialPlayerResponse");
          }
        } else {
          const apiKey = apiKeyMatch[1];

          // ── Step 4: Call innertube /player with ANDROID client ─────
          // This is EXACTLY what youtube-transcript-api does
          const innertubeUrl = `https://www.youtube.com/youtubei/v1/player?key=${apiKey}`;
          const innertubePayload = {
            context: {
              client: {
                clientName: "ANDROID",
                clientVersion: "20.10.38",
              },
            },
            videoId: videoId,
          };

          const innerResp = await fetch(innertubeUrl, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            body: JSON.stringify(innertubePayload),
          });

          if (!innerResp.ok) {
            errors.push(`innertube_android: HTTP ${innerResp.status}`);
          } else {
            const innerData = await innerResp.json();
            const result = await extractCaptionsFromPlayerData(innerData, videoId, corsHeaders);
            if (result) return result;

            const status = innerData.playabilityStatus?.status || "?";
            const reason = innerData.playabilityStatus?.reason || "";
            errors.push(`innertube_android: ${status} — ${reason}`.trim());
          }
        }
      }
    }
  } catch (e) {
    errors.push(`exception: ${e.message}`);
  }

  return Response.json(
    { success: false, errors },
    { status: 404, headers: corsHeaders }
  );
}


// ─── Extract captions from player data and download transcript ──────

async function extractCaptionsFromPlayerData(playerData, videoId, corsHeaders) {
  const status = playerData.playabilityStatus?.status;
  if (status !== "OK") return null;

  const tracks = playerData.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
  if (tracks.length === 0) return null;

  // Find best English caption track
  let target =
    tracks.find((t) => t.languageCode === "en" && t.kind !== "asr") ||
    tracks.find((t) => t.languageCode === "en") ||
    tracks[0];

  if (!target?.baseUrl) return null;

  // Download the caption track
  const capUrl = target.baseUrl;
  const capResp = await fetch(capUrl, {
    headers: { "User-Agent": "Mozilla/5.0" },
  });

  if (!capResp.ok) return null;

  const capXml = await capResp.text();

  // Parse XML caption format
  const text = parseXmlCaptions(capXml);
  if (text && text.length >= 50) {
    return Response.json(
      {
        success: true,
        text,
        source: "cf_worker_innertube_android",
        language: target.languageCode,
        chars: text.length,
      },
      { headers: corsHeaders }
    );
  }

  return null;
}


// ─── Parse XML captions format ──────────────────────────────────────

function parseXmlCaptions(xml) {
  // Simple XML parser for YouTube captions
  // Format: <transcript><text start="0" dur="1.5">Hello world</text>...</transcript>
  const segments = [];
  const regex = /<text[^>]*>([\s\S]*?)<\/text>/g;
  let match;
  while ((match = regex.exec(xml)) !== null) {
    let text = match[1]
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/\n/g, " ")
      .trim();
    if (text) segments.push(text);
  }
  return segments.join(" ");
}


// ─── Playability Check ──────────────────────────────────────────────

async function checkPlayability(videoId, corsHeaders) {
  try {
    const oembedUrl = `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`;
    const resp = await fetch(oembedUrl, {
      headers: { "User-Agent": "Mozilla/5.0" },
    });

    if (resp.ok) {
      return Response.json(
        { playable: true, status: "OK", reason: "" },
        { headers: corsHeaders }
      );
    }

    return Response.json(
      { playable: false, status: "NOT_FOUND", reason: `oembed HTTP ${resp.status}` },
      { headers: corsHeaders }
    );
  } catch (e) {
    return Response.json(
      { playable: false, error: e.message },
      { status: 500, headers: corsHeaders }
    );
  }
}
