# Deployment Guide: Cloudflare Worker Transcript Proxy

## Ringkasan

Deploy 5 Cloudflare Workers (1 per akun/channel) sebagai proxy permanen untuk YouTube transcript extraction. **Tidak pernah expire**, gratis 100K request/hari per worker.

## Langkah Deploy (Ulangi untuk Masing-masing 5 Akun)

### 1. Buat Akun Cloudflare (Gratis)

Buka https://dash.cloudflare.com/sign-up — daftar dengan email masing-masing akun.

### 2. Buat Worker

1. Login ke **Cloudflare Dashboard**
2. Klik **Workers & Pages** di sidebar kiri
3. Klik **Create** → **Create Worker**
4. Beri nama worker: `yt-transcript-proxy`
5. Klik **Deploy** (biarkan code default dulu)

### 3. Edit Code Worker

1. Setelah deploy, klik **Edit Code**
2. **Hapus semua** code default
3. **Copy-paste** seluruh isi file `cloudflare/worker.js` dari repo
4. Klik **Deploy** (atau Save & Deploy)

### 4. Set Environment Variable (AUTH_KEY)

1. Kembali ke halaman worker
2. Klik **Settings** → **Variables and Secrets**
3. Klik **Add** → pilih **Secret**
4. Name: `AUTH_KEY`
5. Value: (gunakan key dari tabel di bawah)
6. Klik **Save**

### 5. Catat URL Worker

URL worker ada di halaman overview, formatnya:
```
https://yt-transcript-proxy.<subdomain-kamu>.workers.dev
```

---

## Tabel Konfigurasi per Channel

| # | Channel | Akun CF | AUTH_KEY | GitHub Secret URL |
|---|---------|---------|---------|-------------------|
| 1 | psyched | Akun 1 | `cpk_Xt9mQ4vL7nRjW2bFhKs8dYpA3` | `CF_WORKER_URL_1` |
| 2 | minted  | Akun 2 | `cpk_Bw6rH1eZcN5gTyUx0jMfKq4P9` | `CF_WORKER_URL_2` |
| 3 | vitals  | Akun 3 | `cpk_Jn3sV8dLkR7wYm2XpF6hCt0G5` | `CF_WORKER_URL_3` |
| 4 | wired   | Akun 4 | `cpk_Dz5fA9qWu1xNb4vKy7JmEh3S8` | `CF_WORKER_URL_4` |
| 5 | sage    | Akun 5 | `cpk_Mg2tL0pHr6cXw9kBn4YfQj8V1` | `CF_WORKER_URL_5` |

## GitHub Secrets yang Harus Ditambahkan (10 total)

Setelah deploy 5 worker, tambahkan di GitHub repo Settings → Secrets:

| Secret Name | Value |
|---|---|
| `CF_WORKER_URL_1` | `https://yt-transcript-proxy.akun1.workers.dev` |
| `CF_WORKER_URL_2` | `https://yt-transcript-proxy.akun2.workers.dev` |
| `CF_WORKER_URL_3` | `https://yt-transcript-proxy.akun3.workers.dev` |
| `CF_WORKER_URL_4` | `https://yt-transcript-proxy.akun4.workers.dev` |
| `CF_WORKER_URL_5` | `https://yt-transcript-proxy.akun5.workers.dev` |
| `CF_WORKER_AUTH_KEY_1` | `cpk_Xt9mQ4vL7nRjW2bFhKs8dYpA3` |
| `CF_WORKER_AUTH_KEY_2` | `cpk_Bw6rH1eZcN5gTyUx0jMfKq4P9` |
| `CF_WORKER_AUTH_KEY_3` | `cpk_Jn3sV8dLkR7wYm2XpF6hCt0G5` |
| `CF_WORKER_AUTH_KEY_4` | `cpk_Dz5fA9qWu1xNb4vKy7JmEh3S8` |
| `CF_WORKER_AUTH_KEY_5` | `cpk_Mg2tL0pHr6cXw9kBn4YfQj8V1` |

## Test Worker (Opsional)

Setelah deploy, test dengan curl:

```bash
curl -X POST https://yt-transcript-proxy.akun1.workers.dev \
  -H "Content-Type: application/json" \
  -H "X-Auth-Key: cpk_Xt9mQ4vL7nRjW2bFhKs8dYpA3" \
  -d '{"action": "transcript", "video_id": "dQw4w9WgXcQ"}'
```

Kalau berhasil, response akan berisi `"success": true` dan `"text": "..."`.
