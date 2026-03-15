import requests, json, sys
sys.path.insert(0, '.')

# Test with a known popular Huberman Lab video that definitely has captions
test_videos = [
    ('RDQ4vHAPN1s', 'Andrej Karpathy video'),
    ('s9SnEE7JXU4', 'Andrej Karpathy video 2'),
    ('qF_tfIieeE0', 'Andrej Karpathy video 3'),
]

url = 'https://www.youtube.com/youtubei/v1/player'
headers = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

for vid, name in test_videos:
    print(f'\n=== Testing {name} ({vid}) ===')
    payload = {
        'context': {
            'client': {
                'clientName': 'WEB',
                'clientVersion': '2.20240101.00.00',
                'hl': 'en', 'gl': 'US'
            }
        },
        'videoId': vid
    }
    
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    data = resp.json()
    
    playability = data.get('playabilityStatus', {})
    print(f'Playability: {playability.get("status", "unknown")}')
    
    if playability.get('status') != 'OK':
        print(f'Reason: {playability.get("reason", "none")}')
        continue
    
    captions = data.get('captions', {}).get('playerCaptionsTracklistRenderer', {})
    tracks = captions.get('captionTracks', [])
    print(f'Caption tracks: {len(tracks)}')
    
    for t in tracks:
        lang = t.get('languageCode', '?')
        kind = t.get('kind', 'manual')
        print(f'  - {lang}: {kind}')
    
    if tracks:
        base_url = tracks[0].get('baseUrl', '')
        cap_resp = requests.get(f'{base_url}&fmt=json3', headers=headers, timeout=15)
        if cap_resp.status_code == 200:
            cap_data = cap_resp.json()
            events = cap_data.get('events', [])
            text = []
            for e in events[:3]:
                for seg in e.get('segs', []):
                    t = seg.get('utf8', '').strip()
                    if t and t != '\n':
                        text.append(t)
            print(f'Caption events: {len(events)}')
            print(f'Preview: {" ".join(text)[:200]}')


# Also test youtube-transcript-api
print('\n\n=== Testing youtube-transcript-api ===')
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    print(f'Library version: {getattr(YouTubeTranscriptApi, "__version__", "unknown")}')
    
    for vid, name in test_videos:
        print(f'\nTesting {name} ({vid})...')
        try:
            entries = YouTubeTranscriptApi.get_transcript(vid, languages=['en'])
            text = " ".join([e.get("text", "") if isinstance(e, dict) else str(e) for e in entries])
            print(f'SUCCESS! Length: {len(text)} chars')
            print(f'Preview: {text[:200]}')
        except Exception as e:
            print(f'FAILED: {type(e).__name__}: {e}')
except ImportError as e:
    print(f'youtube-transcript-api not installed: {e}')
