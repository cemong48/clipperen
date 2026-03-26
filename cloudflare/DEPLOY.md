# Deployment Guide: Cloudflare Worker Transcript Proxy

## Ringkasan

Deploy 5 Cloudflare Workers (1 per akun/channel) sebagai proxy untuk YouTube transcript extraction. **Gratis 100K request/hari per worker.** Sekarang auto-deploy via pipeline — tidak perlu manual edit code lagi.

## Auto-Deploy (Setiap Pipeline Run)

Pipeline `daily_pipeline.yml` otomatis deploy `cloudflare/worker.js` ke semua 5 CF Workers menggunakan Cloudflare API. Tidak perlu manual edit code di dashboard lagi.

### Secrets yang Dibutuhkan (Per Akun, 1x Setup)

| Secret | Cara Dapat | Fungsi |
|---|---|---|
| `CF_ACCOUNT_ID_1` s/d `_5` | CF Dashboard → sidebar kanan → **Account ID** | Identifikasi akun |
| `CF_API_TOKEN_1` s/d `_5` | My Profile → API Tokens → Create → **Edit Workers** template | Push code ke worker |
| `CF_WORKER_URL_1` s/d `_5` | `https://yt-transcript-proxy.<subdomain>.workers.dev` | Endpoint yang dipanggil pipeline |
| `CF_WORKER_AUTH_KEY_1` s/d `_5` | Lihat tabel di bawah | Autentikasi request |

## Tabel Konfigurasi per Channel

| # | Channel | AUTH_KEY | GitHub Secrets |
|---|---------|---------|---|
| 1 | psyched | `cpk_Xt9mQ4vL7nRjW2bFhKs8dYpA3` | `CF_WORKER_URL_1`, `CF_WORKER_AUTH_KEY_1`, `CF_ACCOUNT_ID_1`, `CF_API_TOKEN_1` |
| 2 | minted  | `cpk_Bw6rH1eZcN5gTyUx0jMfKq4P9` | `CF_WORKER_URL_2`, `CF_WORKER_AUTH_KEY_2`, `CF_ACCOUNT_ID_2`, `CF_API_TOKEN_2` |
| 3 | vitals  | `cpk_Jn3sV8dLkR7wYm2XpF6hCt0G5` | `CF_WORKER_URL_3`, `CF_WORKER_AUTH_KEY_3`, `CF_ACCOUNT_ID_3`, `CF_API_TOKEN_3` |
| 4 | wired   | `cpk_Dz5fA9qWu1xNb4vKy7JmEh3S8` | `CF_WORKER_URL_4`, `CF_WORKER_AUTH_KEY_4`, `CF_ACCOUNT_ID_4`, `CF_API_TOKEN_4` |
| 5 | sage    | `cpk_Mg2tL0pHr6cXw9kBn4YfQj8V1` | `CF_WORKER_URL_5`, `CF_WORKER_AUTH_KEY_5`, `CF_ACCOUNT_ID_5`, `CF_API_TOKEN_5` |

Total: **20 secrets** untuk CF Workers (4 per channel × 5 channels)

## Manual Deploy (Pertama Kali atau Darurat)

```bash
python scripts/deploy_cf_workers.py
```

Script interaktif yang meminta Account ID, Worker name, dan API Token per channel.

## Cara Kerja CF Worker (worker.js)

Mereplikasi **algoritma persis** `youtube-transcript-api` v1.2.4:

1. Fetch YouTube watch page HTML
2. Handle consent page (SOCS cookie)
3. Extract `INNERTUBE_API_KEY` dari HTML
4. POST ke `/youtubei/v1/player` dengan ANDROID client (v20.10.38)
5. Download captions dari response

Pipeline mem-forward cookies dari `temp/cookies_{idx}.txt` ke CF Worker untuk bypass bot detection.

## Test Worker

```bash
curl -X POST https://yt-transcript-proxy.<subdomain>.workers.dev \
  -H "Content-Type: application/json" \
  -H "X-Auth-Key: <AUTH_KEY>" \
  -d '{"action": "transcript", "video_id": "dQw4w9WgXcQ", "cookies": ""}'
```
