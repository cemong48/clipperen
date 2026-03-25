// Cloudflare Worker: YouTube Transcript Proxy
// Deploy 1 worker per channel/account
// Scrapes YouTube watch page WITH COOKIES for caption URLs
//
// Environment Variables (set in CF Worker Settings):
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

async function getTranscript(videoId, cookieStr, corsHeaders) {
  const errors = [];

  // Method 1: Scrape YouTube watch page WITH cookies
  // Cookies authenticate the request so YouTube doesn't return 429/bot detection
  try {
    const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;
    const headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Sec-Fetch-Mode": "navigate",
      "Sec-Fetch-Site": "none",
      "Sec-Fetch-Dest": "document",
      "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
      "Sec-Ch-Ua-Mobile": "?0",
      "Sec-Ch-Ua-Platform": '"Windows"',
    };

    // Add cookies if provided
    if (cookieStr) {
      headers["Cookie"] = cookieStr;
    }

    const watchResp = await fetch(watchUrl, { headers, redirect: "follow" });

    if (!watchResp.ok) {
      errors.push(`watch_page: HTTP ${watchResp.status}`);
    } else {
      const html = await watchResp.text();

      // Extract ytInitialPlayerResponse from page HTML
      let playerJson = null;

      // Pattern 1: var ytInitialPlayerResponse = {...};
      const m1 = html.match(/var\s+ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;\s*var/s);
      if (m1) {
        playerJson = m1[1];
      }

      // Pattern 2: ytInitialPlayerResponse = {...}; (without var)
      if (!playerJson) {
        const m2 = html.match(/ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;/s);
        if (m2) {
          playerJson = m2[1];
        }
      }

      if (!playerJson) {
        // Check if we got a consent/bot page instead
        if (html.includes("confirm you") || html.includes("captcha") || html.includes("consent")) {
          errors.push("watch_page: got consent/captcha page (cookies may be invalid)");
        } else {
          errors.push("watch_page: ytInitialPlayerResponse not found in HTML");
        }
      } else {
        const result = await extractCaptionsFromPlayerResponse(playerJson, videoId, corsHeaders);
        if (result) return result;
        errors.push("watch_page: no usable captions in player response");
      }
    }
  } catch (e) {
    errors.push(`watch_page: ${e.message}`);
  }

  // Method 2: Try YouTube oEmbed + timedtext (no auth needed, limited)
  try {
    // First check if video exists via oEmbed
    const oembedResp = await fetch(
      `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`,
      { headers: { "User-Agent": "Mozilla/5.0" } }
    );
    if (oembedResp.ok) {
      // Video exists, try direct caption URL patterns
      // Some videos have publicly accessible caption tracks
      const captionUrls = [
        `https://www.youtube.com/api/timedtext?v=${videoId}&lang=en&fmt=json3`,
        `https://www.youtube.com/api/timedtext?v=${videoId}&lang=en&kind=asr&fmt=json3`,
      ];

      for (const capUrl of captionUrls) {
        try {
          const capHeaders = { "User-Agent": "Mozilla/5.0" };
          if (cookieStr) capHeaders["Cookie"] = cookieStr;
          
          const capResp = await fetch(capUrl, { headers: capHeaders });
          if (capResp.ok) {
            const text = await capResp.text();
            if (text && text.length > 50) {
              try {
                const capData = JSON.parse(text);
                const transcript = parseJson3Captions(capData);
                if (transcript && transcript.length >= 50) {
                  return Response.json(
                    { success: true, text: transcript, source: "cf_worker_timedtext", chars: transcript.length },
                    { headers: corsHeaders }
                  );
                }
              } catch (e) {
                // Not JSON, skip
              }
            }
          }
        } catch (e) {
          // Ignore individual caption URL failures
        }
      }
      errors.push("timedtext: no captions found via direct URLs");
    }
  } catch (e) {
    errors.push(`timedtext: ${e.message}`);
  }

  return Response.json(
    { success: false, errors },
    { status: 404, headers: corsHeaders }
  );
}


// ─── Helper: Extract captions from ytInitialPlayerResponse ──────────

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

    // Find best English track
    let target =
      tracks.find((t) => t.languageCode === "en" && t.kind !== "asr") ||
      tracks.find((t) => t.languageCode === "en") ||
      tracks[0];

    if (!target?.baseUrl) return null;

    const capUrl = target.baseUrl + (target.baseUrl.includes("?") ? "&fmt=json3" : "?fmt=json3");
    const capResp = await fetch(capUrl, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      },
    });

    if (!capResp.ok) return null;

    const capData = await capResp.json();
    const text = parseJson3Captions(capData);

    if (text && text.length >= 50) {
      return Response.json(
        {
          success: true,
          text,
          source: "cf_worker_watch_page",
          language: target.languageCode,
          chars: text.length,
        },
        { headers: corsHeaders }
      );
    }

    return null;
  } catch (e) {
    return null;
  }
}


// ─── Helper: Parse JSON3 captions format ────────────────────────────

function parseJson3Captions(capData) {
  const segments = [];
  for (const event of capData.events || []) {
    const parts = [];
    for (const seg of event.segs || []) {
      const text = (seg.utf8 || "").trim();
      if (text && text !== "\n") parts.push(text);
    }
    if (parts.length) segments.push(parts.join(" "));
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

    if (resp.status === 401) {
      return Response.json(
        { playable: true, status: "OK_NO_EMBED", reason: "Embedding disabled but video exists" },
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
