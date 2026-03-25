// Cloudflare Worker: YouTube Transcript Proxy
// Deploy 1 worker per channel/account
// Proxies innertube API requests through Cloudflare IPs to bypass bot detection
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

// ─── Transcript Extraction ───────────────────────────────────────────

async function getTranscript(videoId, corsHeaders) {
  // Try multiple innertube clients — IOS is most reliable for bypassing login requirements
  const clients = [
    {
      name: "IOS",
      payload: {
        context: {
          client: {
            clientName: "IOS",
            clientVersion: "19.29.1",
            deviceMake: "Apple",
            deviceModel: "iPhone16,2",
            hl: "en",
            gl: "US",
          },
        },
        videoId,
      },
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X;)",
        "X-Youtube-Client-Name": "5",
        "X-Youtube-Client-Version": "19.29.1",
      },
    },
    {
      name: "ANDROID",
      payload: {
        context: {
          client: {
            clientName: "ANDROID",
            clientVersion: "19.29.37",
            androidSdkVersion: 34,
            hl: "en",
            gl: "US",
          },
        },
        videoId,
      },
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "com.google.android.youtube/19.29.37 (Linux; U; Android 14) gzip",
        "X-Youtube-Client-Name": "3",
        "X-Youtube-Client-Version": "19.29.37",
      },
    },
    {
      name: "TV_EMBEDDED",
      payload: {
        context: {
          client: {
            clientName: "TVHTML5_SIMPLY_EMBEDDED_PLAYER",
            clientVersion: "2.0",
            hl: "en",
            gl: "US",
          },
          thirdParty: {
            embedUrl: "https://www.google.com",
          },
        },
        videoId,
      },
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      },
    },
    {
      name: "WEB",
      payload: {
        context: {
          client: { clientName: "WEB", clientVersion: "2.20250325.00.00", hl: "en", gl: "US" },
        },
        videoId,
      },
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      },
    },
  ];

  const errors = [];

  for (const client of clients) {
    try {
      const resp = await fetch("https://www.youtube.com/youtubei/v1/player", {
        method: "POST",
        headers: client.headers,
        body: JSON.stringify(client.payload),
      });

      if (!resp.ok) {
        errors.push(`${client.name}: HTTP ${resp.status}`);
        continue;
      }

      const data = await resp.json();

      // Check playability
      const status = data.playabilityStatus?.status;
      if (status !== "OK") {
        const reason = data.playabilityStatus?.reason || "unknown";
        errors.push(`${client.name}: ${status} — ${reason}`);
        continue;
      }

      // Get caption tracks
      const tracks = data.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
      if (tracks.length === 0) {
        errors.push(`${client.name}: no caption tracks`);
        continue;
      }

      // Find English track (prefer manual, then auto, then any)
      let target =
        tracks.find((t) => t.languageCode === "en" && t.kind !== "asr") ||
        tracks.find((t) => t.languageCode === "en") ||
        tracks[0];

      if (!target?.baseUrl) {
        errors.push(`${client.name}: no baseUrl`);
        continue;
      }

      // Download captions as JSON3
      const capUrl = target.baseUrl + (target.baseUrl.includes("?") ? "&fmt=json3" : "?fmt=json3");
      const capResp = await fetch(capUrl, { headers: client.headers });

      if (!capResp.ok) {
        errors.push(`${client.name}: caption download ${capResp.status}`);
        continue;
      }

      const capData = await capResp.json();

      // Parse segments to plain text
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
            source: `cf_worker_${client.name.toLowerCase()}`,
            language: target.languageCode,
            chars: text.length,
          }),
          { headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }

      errors.push(`${client.name}: text too short (${text.length} chars)`);
    } catch (e) {
      errors.push(`${client.name}: ${e.message}`);
    }
  }

  return new Response(
    JSON.stringify({ success: false, errors }),
    { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
  );
}

// ─── Playability Check ───────────────────────────────────────────────

async function checkPlayability(videoId, corsHeaders) {
  try {
    const resp = await fetch("https://www.youtube.com/youtubei/v1/player", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      },
      body: JSON.stringify({
        context: {
          client: { clientName: "WEB", clientVersion: "2.20240101.00.00", hl: "en", gl: "US" },
        },
        videoId,
      }),
    });

    const data = await resp.json();
    const status = data.playabilityStatus?.status || "UNKNOWN";
    const reason = data.playabilityStatus?.reason || "";

    return new Response(
      JSON.stringify({ playable: status === "OK", status, reason }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (e) {
    return new Response(
      JSON.stringify({ playable: false, error: e.message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
}
