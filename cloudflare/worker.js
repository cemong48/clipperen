// Cloudflare Worker: YouTube Transcript Proxy
// Strategy: Call innertube ANDROID API DIRECTLY with hardcoded key
// (no watch page needed — avoids 429 on watch page from datacenter IPs)
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


// ─── Transcript Extraction ──────────────────────────────────────────
// Priority order:
//   1. Innertube ANDROID API (direct, no watch page needed)
//   2. Watch page scraping (fallback, may 429 from datacenter IPs)

// Well-known public innertube API key — used by all YouTube clients
const INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8";

async function getTranscript(videoId, cookieStr, corsHeaders) {
  const errors = [];

  // ─── METHOD 1: Innertube ANDROID API (direct call, no watch page) ───
  // This is the most reliable method from datacenter IPs because it
  // doesn't hit the watch page (which returns 429 from CF Worker IPs).
  try {
    const innertubeUrl = `https://www.youtube.com/youtubei/v1/player?key=${INNERTUBE_API_KEY}`;
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
        "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 13)",
      },
      body: JSON.stringify(innertubePayload),
    });

    if (innerResp.ok) {
      const innerData = await innerResp.json();
      const result = await extractCaptionsFromPlayerData(innerData, videoId, corsHeaders, "innertube_android");
      if (result) return result;

      const status = innerData.playabilityStatus?.status || "?";
      const reason = innerData.playabilityStatus?.reason || "";
      errors.push(`innertube_android: ${status} ${reason}`.trim());
    } else {
      errors.push(`innertube_android: HTTP ${innerResp.status}`);
    }
  } catch (e) {
    errors.push(`innertube_android: ${e.message}`);
  }

  // ─── METHOD 2: Innertube WEB client ─────────────────────────────────
  try {
    const innertubeUrl = `https://www.youtube.com/youtubei/v1/player?key=${INNERTUBE_API_KEY}`;
    const webPayload = {
      context: {
        client: {
          clientName: "WEB",
          clientVersion: "2.20240313.05.00",
        },
      },
      videoId: videoId,
    };

    const webResp = await fetch(innertubeUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      },
      body: JSON.stringify(webPayload),
    });

    if (webResp.ok) {
      const webData = await webResp.json();
      const result = await extractCaptionsFromPlayerData(webData, videoId, corsHeaders, "innertube_web");
      if (result) return result;

      const status = webData.playabilityStatus?.status || "?";
      const reason = webData.playabilityStatus?.reason || "";
      errors.push(`innertube_web: ${status} ${reason}`.trim());
    } else {
      errors.push(`innertube_web: HTTP ${webResp.status}`);
    }
  } catch (e) {
    errors.push(`innertube_web: ${e.message}`);
  }

  // ─── METHOD 3: Watch page scraping (fallback) ───────────────────────
  try {
    const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;
    const fetchHeaders = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    };

    if (cookieStr) {
      fetchHeaders["Cookie"] = cookieStr;
    }

    const watchResp = await fetch(watchUrl, { headers: fetchHeaders, redirect: "follow" });

    if (watchResp.ok) {
      const html = await watchResp.text();

      // Try to extract ytInitialPlayerResponse
      const playerMatch = html.match(/var\s+ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;\s*var/s)
        || html.match(/ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;/s);

      if (playerMatch) {
        const result = await extractCaptionsFromPlayerData(JSON.parse(playerMatch[1]), videoId, corsHeaders, "watch_page");
        if (result) return result;
        errors.push("watch_page: no captions in ytInitialPlayerResponse");
      } else {
        errors.push("watch_page: ytInitialPlayerResponse not found");
      }
    } else {
      errors.push(`watch_page: HTTP ${watchResp.status}`);
    }
  } catch (e) {
    errors.push(`watch_page: ${e.message}`);
  }

  return Response.json(
    { success: false, errors },
    { status: 404, headers: corsHeaders }
  );
}


// ─── Extract captions from player data and download transcript ──────

async function extractCaptionsFromPlayerData(playerData, videoId, corsHeaders, source) {
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

  // Try to download the caption track directly
  try {
    const capResp = await fetch(target.baseUrl, {
      headers: { "User-Agent": "com.google.android.youtube/20.10.38" },
    });

    if (capResp.ok) {
      const capXml = await capResp.text();
      const text = parseXmlCaptions(capXml);

      if (text && text.length >= 50) {
        return Response.json(
          {
            success: true,
            text,
            source: `cf_worker_${source}`,
            language: target.languageCode,
            chars: text.length,
          },
          { headers: corsHeaders }
        );
      }
    }
  } catch (e) {
    // Caption download failed (likely 429 from CF Worker IP) — fall through
  }

  // Caption download failed — return the URLs so Python caller can download them
  const captionUrls = tracks.map((t) => ({
    languageCode: t.languageCode,
    kind: t.kind || "manual",
    baseUrl: t.baseUrl,
    name: t.name?.runs?.[0]?.text || t.name?.simpleText || t.languageCode,
  }));

  return Response.json(
    {
      success: true,
      text: null,
      caption_urls: captionUrls,
      source: `cf_worker_${source}_urls`,
      language: target.languageCode,
      message: "Caption URLs returned — download from caller side",
    },
    { headers: corsHeaders }
  );
}


// ─── Parse XML captions ─────────────────────────────────────────────

function parseXmlCaptions(xml) {
  const segments = [];
  // Match both <text> tags (format 1) and <p> tags (format 3/timedtext)
  const regex = /<(?:text|p)[^>]*>([\s\S]*?)<\/(?:text|p)>/g;
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
