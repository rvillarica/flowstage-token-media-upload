# Flowstage Token-Based Auth Upload 

A demo script for uploading photos and videos to Flowstage aesthetics using token-based upload links

## Quickstart

### 1. Install Dependencies

```bash
# Install ffmpeg (required for video metadata)
brew install ffmpeg  # macOS
# or
sudo apt install ffmpeg  # Ubuntu/Debian

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Get an Upload Link from Flowstage

Before you can upload, you need to generate an upload link in Flowstage:

1. **Log in to Flowstage** at [app.theflowstage.com](https://app.theflowstage.com)
2. **Navigate to your aesthetic** where you want to upload media
3. **Click "Upload photos and videos from phone"** (to get your public access URL)
4. **Generate a new upload link**:
   - Set expiration time (e.g., 2 hours, 24 hours)
   - Set max number of uploads (e.g., 50, 100)
   - Copy the generated URL

The upload link will look like:
```
https://app.theflowstage.com/upload?facet=xxx-xxx-xxx&token=yyy-yyy-yyy&title=My+Aesthetic
```

### 3. Upload Media

```bash
python test_upload.py \
  --url "https://app.theflowstage.com/upload?facet=xxx&token=yyy" \
  --file video.mp4
```

That's it! Your media will be uploaded and automatically appear in your aesthetic.

---

## Usage

### Basic Upload

```bash
# Upload a video
python test_upload.py \
  --url "YOUR_UPLOAD_LINK" \
  --file video.mp4

# Upload a photo
python test_upload.py \
  --url "YOUR_UPLOAD_LINK" \
  --file photo.jpg

# Upload multiple files (run script multiple times)
python test_upload.py --url "YOUR_UPLOAD_LINK" --file video1.mp4
python test_upload.py --url "YOUR_UPLOAD_LINK" --file video2.mp4
python test_upload.py --url "YOUR_UPLOAD_LINK" --file photo1.jpg
```

---

## What the Script Does

When you run the test script, it:

1. ✅ **Validates your upload link** - Checks if it's still valid and has remaining uses
2. ✅ **Uploads the file** - Streams file to cloud storage
3. ✅ **Extracts metadata**:
   - Videos: Duration, dimensions, thumbnail (using ffmpeg)
   - Photos: Dimensions
4. ✅ **Creates media record** - Adds to your aesthetic automatically
5. ✅ **Triggers processing** - Video transcoding and AI analysis happen in the background

### Sample Output

```
🔗 Parsed upload URL:
   Token: 8ea88714d2c74f02...
   Facet ID: 2117dcfc-271d-4967-b8a2-ced56aab982d
   Title: My Aesthetic

🔍 Resolving token...
✅ Token valid
   Scope: facet_id=2117dcfc-271d-4967-b8a2-ced56aab982d
   Remaining uses: 50
   Status: active

📤 Uploading video: vacation.mp4
   Size: 45,234,567 bytes (43.14 MB)
   [1/3] Uploading to storage...
   ✓ Uploaded to storage: 2026/04/14/facet_xxx/vacation.mp4
   [2/3] Extracting video metadata and generating thumbnail...
   ✓ Duration: 12.34s
   ✓ Dimensions: 1920x1080
   ✓ Thumbnail generated, uploading...
   ✓ Thumbnail uploaded: 2026/04/14/thumbs/xxx.jpg
   [3/3] Finalizing (creating DB records)...
✅ Complete! Media record created and linked to facet

🔍 Verifying upload...
✅ Token consumed! Remaining uses: 49

============================================================
🎉 TEST PASSED - Upload successful!
============================================================

Your video is now in your aesthetic and will be visible in Flowstage shortly.
```

---

## Understanding Upload Links

### Link Components

Your upload link contains three key pieces:

```
https://app.theflowstage.com/upload?facet=xxx&token=yyy&title=My+Aesthetic
```

- **`facet=xxx`**: The aesthetic (collection) ID where media will go
- **`token=yyy`**: Your temporary upload credential
- **`title=My+Aesthetic`**: Display name for the aesthetic (optional)

### Link Properties

Each upload link has:
- ⏰ **Expiration time** - Links expire after set duration (e.g., 2 hours, 24 hours)
- 🔢 **Upload limit** - Max number of files you can upload (e.g., 50, 100)
- 🔗 **Single aesthetic** - All uploads go to one specific aesthetic

### Checking Link Status

Before uploading, you can check your link's status:

```bash
# The script automatically checks this, but you can verify manually
curl "https://backend-mobile-upload.theflowstage.com/api/temp-upload-tokens/YOUR_TOKEN/resolve"
```

---

## Troubleshooting

### "Upload link has expired"

**Problem:** Your link is past its expiration time or has reached its upload limit.

**Solution:** Generate a new upload link in Flowstage (see [Step 2](#2-get-an-upload-link-from-flow-stage) above).

---

### Upload succeeds but media doesn't appear in Flowstage

**Possible causes:**
- Media is still processing (transcoding/analysis) - wait 1-2 minutes
- The /finalize endpoint was not called, which actually creates the DB records

---

### File is too large

**Problem:** File exceeds storage limits (typically 64MB per file).

**Solution:**
- Compress the video before uploading
- Use a video compression tool like HandBrake or ffmpeg

---

## API Integration Guide

### Step 1: Get Upload Link from User

Ask the user to generate an upload link in Flowstage and paste it into your app.

### Step 2: Extract Token from URL

```python
from urllib.parse import urlparse, parse_qs

url = "https://app.theflowstage.com/upload?facet=xxx&token=yyy"
params = parse_qs(urlparse(url).query)
token = params['token'][0]
```

### Step 3: Upload File

```python
import requests

# Upload file
with open('video.mp4', 'rb') as f:
    response = requests.post(
        'https://backend-mobile-upload.theflowstage.com/api/media/upload',
        files={'file': f},
        data={
            'token': token,
            'media_type': 'video'
        }
    )
    upload_result = response.json()
```

### Step 4: Finalize Upload

```python
# Finalize (create DB record)
requests.post(
    'https://backend-mobile-upload.theflowstage.com/api/media/finalize',
    json={
        'token': token,
        'storage_path': upload_result['storage_path'],
        'original_filename': 'video.mp4',
        'content_type': upload_result['content_type'],
        'media_type': 'video',
        'size': 12345,  # file size in bytes
        # Optional: add duration, dimensions, thumbnail
    }
)
```

### API Endpoints

**Base URL:** `https://backend-mobile-upload.theflowstage.com`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/temp-upload-tokens/{token}/resolve` | GET | Check if token is valid |
| `/api/media/upload` | POST | Upload file (form data) |
| `/api/media/upload-thumbnail` | POST | Upload thumbnail (form data) |
| `/api/media/finalize` | POST | Create media record (JSON) |

For detailed API specs, see the test script source code.

---

## Requirements

- **Python 3.7+**
- **ffmpeg/ffprobe** (for video metadata extraction)
- **Pillow** (for photo dimension extraction)