// Cloudflare Worker: YouTube Transcript Proxy
// Deploy 1 worker per channel/account
// Scrapes YouTube watch page for caption URLs and downloads them
// (innertube /player API is dead as of 2025-2026)
//
// Environment Variables (set in CF Worker Settings):
//   AUTH_KEY = your CF_WORKER_AUTH_KEY_x value

export default {
  async fetch(request, env) {
    // CORS headers
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Auth-Key",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // Auth check
    const authKey = request.headers.get("X-Auth-Key");
    if (!authKey || authKey !== env.AUTH_KEY) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    if (request.method !== "POST") {
      return new Response(JSON.stringify({ error: "Method not allowed" }), {
        status: 405,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    try {
      const body = await request.json();
      const { action, video_id } = body;

      if (action === "transcript") {
        return await getTranscript(video_id, corsHeaders);
      } else if (action === "playability") {
        return await checkPlayability(video_id, corsHeaders);
      } else {
        return new Response(
          JSON.stringify({ error: "Invalid action. Use: transcript, playability" }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }
    } catch (e) {
      return new Response(
        JSON.stringify({ error: e.message }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }
  },
};

// ─── Transcript Extraction via Watch Page Scraping ──────────────────

async function getTranscript(videoId, corsHeaders) {
  const errors = [];

  // Method 1: Scrape the YouTube watch page for caption track URLs
  // This is how youtube-transcript-api v1.x works — parse the HTML for ytInitialPlayerResponse
  try {
    const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;
    const watchResp = await fetch(watchUrl, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
    });

    if (!watchResp.ok) {
      errors.push(`watch_page: HTTP ${watchResp.status}`);
    } else {
      const html = await watchResp.text();

      // Extract ytInitialPlayerResponse from the page HTML
      const playerRespMatch = html.match(/var ytInitialPlayerResponse\s*=\s*(\{.+?\});/s);
      if (!playerRespMatch) {
        // Try alternative pattern
        const altMatch = html.match(/ytInitialPlayerResponse\s*=\s*(\{.+?\});/s);
        if (!altMatch) {
          errors.push("watch_page: ytInitialPlayerResponse not found in HTML");
        } else {
          const result = await extractCaptionsFromPlayerResponse(altMatch[1], videoId, corsHeaders);
          if (result) return result;
          errors.push("watch_page(alt): no captions extracted");
        }
      } else {
        const result = await extractCaptionsFromPlayerResponse(playerRespMatch[1], videoId, corsHeaders);
        if (result) return result;
        errors.push("watch_page: no captions extracted");
      }
    }
  } catch (e) {
    errors.push(`watch_page: ${e.message}`);
  }

  // Method 2: Try innertube /player API as fallback (may work from CF IPs)
  const clients = [
    {
      name: "WEB",
      payload: {
        context: {
          client: { clientName: "WEB", clientVersion: "2.20250325.00.00", hl: "en", gl: "US" },
        },
        videoId,
        contentCheckOk: true,
        racyCheckOk: true,
      },
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Origin": "https://www.youtube.com",
        "Referer": "https://www.youtube.com/",
      },
    },
  ];

  for (const client of clients) {
    try {
      const resp = await fetch(
        "https://www.youtube.com/youtubei/v1/player?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false",
        {
          method: "POST",
          headers: client.headers,
          body: JSON.stringify(client.payload),
        }
      );

      if (!resp.ok) {
        errors.push(`${client.name}: HTTP ${resp.status}`);
        continue;
      }

      const data = await resp.json();
      const status = data.playabilityStatus?.status;
      if (status !== "OK") {
        errors.push(`${client.name}: ${status} — ${data.playabilityStatus?.reason || "unknown"}`);
        continue;
      }

      const tracks = data.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
      if (tracks.length === 0) {
        errors.push(`${client.name}: no caption tracks`);
        continue;
      }

      const result = await downloadCaptionTrack(tracks, client.headers, client.name, corsHeaders);
      if (result) return result;
      errors.push(`${client.name}: caption download failed`);
    } catch (e) {
      errors.push(`${client.name}: ${e.message}`);
    }
  }

  return new Response(
    JSON.stringify({ success: false, errors }),
    { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
  );
}


// ─── Helper: Extract captions from ytInitialPlayerResponse JSON ────

async function extractCaptionsFromPlayerResponse(jsonStr, videoId, corsHeaders) {
  try {
    const data = JSON.parse(jsonStr);

    const status = data.playabilityStatus?.status;
    if (status !== "OK") {
      return null;
    }

    const tracks = data.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
    if (tracks.length === 0) {
      return null;
    }

    const headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    };

    return await downloadCaptionTrack(tracks, headers, "watch_page", corsHeaders);
  } catch (e) {
    return null;
  }
}


// ─── Helper: Download and parse caption track ──────────────────────

async function downloadCaptionTrack(tracks, headers, sourceName, corsHeaders) {
  // Find English track (prefer manual, then auto, then any)
  let target =
    tracks.find((t) => t.languageCode === "en" && t.kind !== "asr") ||
    tracks.find((t) => t.languageCode === "en") ||
    tracks[0];

  if (!target?.baseUrl) return null;

  const capUrl = target.baseUrl + (target.baseUrl.includes("?") ? "&fmt=json3" : "?fmt=json3");
  const capResp = await fetch(capUrl, { headers });

  if (!capResp.ok) return null;

  const capData = await capResp.json();
  const segments = [];
  for (const event of capData.events || []) {
    const parts = [];
    for (const seg of event.segs || []) {
      const text = (seg.utf8 || "").trim();
      if (text && text !== "\n") parts.push(text);
    }
    if (parts.length) segments.push(parts.join(" "));
  }

  const text = segments.join(" ");
  if (text.length >= 50) {
    return new Response(
      JSON.stringify({
        success: true,
        text,
        source: `cf_worker_${sourceName}`,
        language: target.languageCode,
        chars: text.length,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }

  return null;
}


// ─── Playability Check ───────────────────────────────────────────────

async function checkPlayability(videoId, corsHeaders) {
  // Method 1: Check via watch page (more reliable than innertube)
  try {
    const oembedUrl = `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`;
    const resp = await fetch(oembedUrl, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      },
    });

    if (resp.ok) {
      return new Response(
        JSON.stringify({ playable: true, status: "OK", reason: "" }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // 401 = embedding disabled but video exists, 404 = video doesn't exist
    if (resp.status === 401) {
      return new Response(
        JSON.stringify({ playable: true, status: "OK_NO_EMBED", reason: "Embedding disabled but video exists" }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(
      JSON.stringify({ playable: false, status: "NOT_FOUND", reason: `oembed HTTP ${resp.status}` }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (e) {
    return new Response(
      JSON.stringify({ playable: false, error: e.message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
}
