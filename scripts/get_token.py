# scripts/get_token.py
# Simple script — Generate refresh token for ONE channel at a time
#
# CARA PAKAI:
#   1. Taruh file client_secret JSON di folder "secrets/" 
#      Contoh: secrets/client_secret_1.json
#
#   2. Jalankan:
#      python scripts/get_token.py 1
#      (ganti 1 dengan nomor channel: 1, 2, 3, 4, atau 5)
#
#   3. Browser akan terbuka → Login pakai akun Google channel itu
#   4. Copy refresh token yang muncul → paste ke GitHub Secrets

import sys
import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly"
]

CHANNEL_NAMES = {
    "1": "psyched (Psychology & Self-Improvement)",
    "2": "minted (Finance & Business)",
    "3": "vitals (Health & Science)",
    "4": "wired (Tech & AI)",
    "5": "sage (Philosophy & Wisdom)"
}

def main():
    if len(sys.argv) < 2:
        print("\n❌ Kasih nomor channel!")
        print("   Contoh: python scripts/get_token.py 1")
        print()
        for k, v in CHANNEL_NAMES.items():
            print(f"   {k} = {v}")
        sys.exit(1)
    
    num = sys.argv[1]
    if num not in CHANNEL_NAMES:
        print(f"❌ Nomor channel harus 1-5, bukan '{num}'")
        sys.exit(1)
    
    print(f"\n{'='*50}")
    print(f"  Channel #{num}: {CHANNEL_NAMES[num]}")
    print(f"{'='*50}")
    
    # Cari file client_secret
    search_paths = [
        f"secrets/client_secret_{num}.json",
        f"client_secret_{num}.json",
        f"secrets/client_secret.json",
    ]
    
    secret_file = None
    for path in search_paths:
        if os.path.exists(path):
            secret_file = path
            break
    
    if not secret_file:
        print(f"\n❌ File client_secret tidak ditemukan!")
        print(f"   Taruh file JSON di salah satu lokasi ini:")
        for p in search_paths:
            print(f"     → {p}")
        print(f"\n   Atau ketik path langsung:")
        secret_file = input("   Path: ").strip().strip('"')
    
    if not os.path.exists(secret_file):
        print(f"❌ File tidak ada: {secret_file}")
        sys.exit(1)
    
    # Validasi JSON
    try:
        with open(secret_file, 'r') as f:
            data = json.load(f)
        
        key_type = "installed" if "installed" in data else ("web" if "web" in data else None)
        if not key_type:
            print("❌ Format JSON tidak valid! Harus ada key 'installed' atau 'web'.")
            sys.exit(1)
        
        client_id = data[key_type].get("client_id", "")
        print(f"   ✅ Client ID: {client_id[:30]}...")
    except json.JSONDecodeError:
        print("❌ File bukan JSON yang valid!")
        sys.exit(1)
    
    print(f"\n⚠️  PENTING:")
    print(f"   Browser akan terbuka sebentar lagi.")
    print(f"   LOGIN pakai akun Google untuk channel: {CHANNEL_NAMES[num]}")
    print(f"   Pastikan akun yang BENAR ya!\n")
    
    input("   Tekan ENTER untuk buka browser...")
    
    # Run OAuth flow
    try:
        flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
        credentials = flow.run_local_server(
            port=8080,
            prompt="consent",
            access_type="offline"
        )
    except Exception as e:
        print(f"\n❌ OAuth gagal: {e}")
        print("\n   Kemungkinan masalah:")
        print("   1. Redirect URI belum di-set di Google Cloud Console")
        print("      → Tambahkan http://localhost:8080/ di Authorized redirect URIs")
        print("   2. YouTube Data API belum di-enable")
        print("      → Buka Google Cloud Console → APIs → Enable YouTube Data API v3")
        sys.exit(1)
    
    if not credentials.refresh_token:
        print("\n❌ Refresh token KOSONG!")
        print("   Ini biasanya karena akun sudah pernah di-authorize sebelumnya.")
        print("   Solusi:")
        print("   1. Buka https://myaccount.google.com/permissions")
        print("   2. Hapus/revoke akses app ini")
        print("   3. Jalankan script ini lagi")
        sys.exit(1)
    
    token = credentials.refresh_token
    
    print(f"\n{'='*50}")
    print(f"  ✅ BERHASIL! Refresh Token untuk Channel #{num}")
    print(f"{'='*50}")
    print(f"\n  Token:")
    print(f"  {token}")
    print(f"\n{'='*50}")
    print(f"  LANGKAH SELANJUTNYA:")
    print(f"  1. Copy token di atas")
    print(f"  2. Buka: https://github.com/cemong48/clipperen/settings/secrets/actions")
    print(f"  3. Klik 'New repository secret'")
    print(f"  4. Name:   YOUTUBE_REFRESH_TOKEN_{num}")
    print(f"  5. Secret: (paste token)")
    print(f"  6. Klik 'Add secret'")
    print(f"{'='*50}")
    
    # Save to local file juga (untuk backup)
    os.makedirs("secrets", exist_ok=True)
    backup_path = f"secrets/refresh_token_{num}.txt"
    with open(backup_path, "w") as f:
        f.write(token)
    print(f"\n  💾 Backup saved: {backup_path}")
    print(f"     (Jangan commit file ini ke GitHub!)")


if __name__ == "__main__":
    main()
