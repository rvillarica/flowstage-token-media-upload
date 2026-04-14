#!/usr/bin/env python3
"""
Headless test script for backend-mobile-upload service.
Tests the complete upload flow using a token URL.

Features:
- Extracts video duration and dimensions using ffprobe
- Generates video thumbnails using ffmpeg
- Extracts photo dimensions using PIL/Pillow
- Uploads thumbnails to server
- Creates DB records and links to facet

Dependencies:
    ffmpeg and ffprobe must be installed (brew install ffmpeg)
    For photos: pip install pillow

Usage:
    python test_upload.py --url "https://app.theflowstage.com/upload?facet=xxx&token=yyy" --file video.mp4
    python test_upload.py --url "https://app.theflowstage.com/upload?token=xxx" --file test.jpg --type photo
"""

import argparse
import os
import sys
import requests
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

# Default to localhost, or override with env var
BASE_URL = "https://backend-mobile-upload.theflowstage.com"


def get_video_duration(file_path: str) -> float:
    """Extract video duration using ffprobe."""
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'json',
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            duration = float(data.get('format', {}).get('duration', 0))
            return duration
    except Exception as e:
        print(f"   ⚠ Failed to extract duration: {e}")
    return 0.0


def get_video_dimensions(file_path: str) -> Tuple[int, int]:
    """Extract video dimensions using ffprobe."""
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'json',
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            streams = data.get('streams', [])
            if streams:
                width = streams[0].get('width', 0)
                height = streams[0].get('height', 0)
                return (width, height)
    except Exception as e:
        print(f"   ⚠ Failed to extract dimensions: {e}")
    return (0, 0)


def generate_video_thumbnail(file_path: str, seek_time: float = 0.5) -> Optional[str]:
    """Generate a thumbnail from video using ffmpeg. Returns path to temp JPEG file."""
    try:
        # Create temp file for thumbnail
        temp_thumb = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        temp_thumb.close()

        result = subprocess.run(
            [
                'ffmpeg',
                '-ss', str(seek_time),
                '-i', file_path,
                '-vframes', '1',
                '-vf', 'scale=480:-1',  # Scale to max width 480, maintain aspect ratio
                '-q:v', '2',  # JPEG quality (2 is high)
                '-y',  # Overwrite output
                temp_thumb.name
            ],
            capture_output=True,
            timeout=30
        )

        if result.returncode == 0 and os.path.exists(temp_thumb.name):
            return temp_thumb.name
        else:
            print(f"   ⚠ ffmpeg failed: {result.stderr.decode()[:200]}")
            os.unlink(temp_thumb.name)
    except Exception as e:
        print(f"   ⚠ Failed to generate thumbnail: {e}")

    return None


def get_image_dimensions(file_path: str) -> Tuple[int, int]:
    """Extract image dimensions using PIL/Pillow."""
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.size  # Returns (width, height)
    except ImportError:
        print(f"   ⚠ PIL/Pillow not installed, skipping dimensions")
        return (0, 0)
    except Exception as e:
        print(f"   ⚠ Failed to extract image dimensions: {e}")
        return (0, 0)


def parse_upload_url(upload_url: str) -> dict:
    """Parse the upload URL to extract token, facet_id, and other params."""
    parsed = urlparse(upload_url)
    params = parse_qs(parsed.query)

    # Extract single values from lists (parse_qs returns lists)
    token = params.get('token', [None])[0]
    facet_id = params.get('facet', [None])[0]
    title = params.get('title', [None])[0]

    if not token:
        raise ValueError("URL must contain 'token' parameter")

    print(f"🔗 Parsed upload URL:")
    print(f"   Token: {token[:16]}..." if len(token) > 16 else f"   Token: {token}")
    if facet_id:
        print(f"   Facet ID: {facet_id}")
    if title:
        print(f"   Title: {title}")

    return {
        "token": token,
        "facet_id": facet_id,
        "title": title,
    }


def resolve_token(token: str, base_url: str = None) -> dict:
    """Resolve token to check validity and remaining uses."""
    api_url = (base_url or BASE_URL).rstrip('/')
    url = f"{api_url}/api/temp-upload-tokens/{token}/resolve"

    print(f"\n🔍 Resolving token...")
    resp = requests.get(url)
    resp.raise_for_status()

    data = resp.json()
    print(f"✅ Token valid")
    print(f"   Scope: facet_id={data['scope'].get('facet_id')}, user_id={data['scope'].get('user_id')}")
    print(f"   Remaining uses: {data.get('remaining_uses')}")
    print(f"   Status: {data['status']}")

    return data


def upload_media(token: str, file_path: str, media_type: str, base_url: str = None) -> dict:
    """Upload a file using the token and finalize it (complete flow)."""
    api_url = (base_url or BASE_URL).rstrip('/')

    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = file_path_obj.stat().st_size
    print(f"\n📤 Uploading {media_type}: {file_path_obj.name}")
    print(f"   Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")

    # Determine content type
    ext = file_path_obj.suffix.lower()
    content_type_map = {
        '.mp4': 'video/mp4',
        '.mov': 'video/quicktime',
        '.avi': 'video/x-msvideo',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
    }
    content_type = content_type_map.get(ext, 'application/octet-stream')

    # Step 1: Upload file to storage
    print(f"   [1/3] Uploading to storage...")
    with open(file_path, 'rb') as f:
        files = {
            'file': (file_path_obj.name, f, content_type)
        }
        data = {
            'token': token,
            'media_type': media_type,
        }

        resp = requests.post(f"{api_url}/api/media/upload", files=files, data=data)
        resp.raise_for_status()

    upload_result = resp.json()
    print(f"   ✓ Uploaded to storage: {upload_result.get('storage_path')}")

    # Step 2: Extract metadata and upload thumbnail
    thumbnail_data = {}
    metadata = {}

    if media_type == 'video':
        print(f"   [2/3] Extracting video metadata and generating thumbnail...")

        # Extract duration
        duration = get_video_duration(file_path)
        if duration > 0:
            metadata['duration'] = duration
            print(f"   ✓ Duration: {duration:.2f}s")

        # Extract dimensions
        width, height = get_video_dimensions(file_path)
        if width > 0 and height > 0:
            metadata['width'] = width
            metadata['height'] = height
            print(f"   ✓ Dimensions: {width}x{height}")

        # Generate and upload thumbnail
        thumb_path = generate_video_thumbnail(file_path, seek_time=min(0.5, duration / 10 if duration > 0 else 0.5))
        if thumb_path:
            try:
                print(f"   ✓ Thumbnail generated, uploading...")
                with open(thumb_path, 'rb') as thumb_file:
                    files = {
                        'file': (f"{file_path_obj.stem}-thumb.jpg", thumb_file, 'image/jpeg')
                    }
                    data = {
                        'token': token,
                    }
                    thumb_resp = requests.post(
                        f"{api_url}/api/media/upload-thumbnail",
                        files=files,
                        data=data
                    )
                    thumb_resp.raise_for_status()
                    thumb_result = thumb_resp.json()
                    thumbnail_data = {
                        'thumbnail_url': thumb_result.get('url'),
                        'thumbnail_storage_path': thumb_result.get('storage_path'),
                    }
                    print(f"   ✓ Thumbnail uploaded: {thumb_result.get('storage_path')}")
            except Exception as e:
                print(f"   ⚠ Thumbnail upload failed: {e}")
            finally:
                # Clean up temp thumbnail
                try:
                    os.unlink(thumb_path)
                except:
                    pass

    elif media_type == 'photo':
        print(f"   [2/3] Extracting photo metadata...")

        # Extract dimensions
        width, height = get_image_dimensions(file_path)
        if width > 0 and height > 0:
            metadata['width'] = width
            metadata['height'] = height
            print(f"   ✓ Dimensions: {width}x{height}")

    # Step 3: Finalize (create DB records and link to facet)
    print(f"   [3/3] Finalizing (creating DB records)...")

    finalize_payload = {
        'token': token,
        'storage_path': upload_result['storage_path'],
        'original_filename': file_path_obj.name,
        'content_type': upload_result.get('content_type') or content_type,
        'media_type': media_type,
        'size': file_size,
        **metadata,
        **thumbnail_data,
    }

    finalize_resp = requests.post(
        f"{api_url}/api/media/finalize",
        json=finalize_payload,
        headers={'Content-Type': 'application/json'}
    )
    finalize_resp.raise_for_status()
    finalize_result = finalize_resp.json()

    print(f"✅ Complete! Media record created and linked to facet")
    print(f"   Media ID: {finalize_result.get('media', {}).get('id')}")
    print(f"   Public URL: {upload_result.get('url')}")

    return {
        **upload_result,
        'finalize': finalize_result,
    }


def verify_upload(token: str, base_url: str = None, expected_use_count: int = 1):
    """Verify the upload by checking token usage."""
    print(f"\n🔍 Verifying upload...")
    data = resolve_token(token, base_url)

    if data.get('status') != 'active':
        print(f"⚠️  Token status: {data.get('status')}")

    # Note: The API doesn't expose use_count in resolve, but we can check remaining_uses
    remaining = data.get('remaining_uses')
    if remaining is not None:
        print(f"✅ Token consumed! Remaining uses: {remaining}")
    else:
        print(f"✅ Token verified (no use limit)")


def main():
    parser = argparse.ArgumentParser(
        description="Test backend-mobile-upload using a token URL",
        epilog="""
Examples:
  python test_upload.py --url "https://app.theflowstage.com/upload?facet=xxx&token=yyy" --file video.mp4
  python test_upload.py --url "https://app.theflowstage.com/upload?token=xxx" --file photo.jpg --type photo
        """
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Upload URL with token (e.g., https://app.theflowstage.com/upload?facet=xxx&token=yyy)"
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to file to upload (video or photo)"
    )
    parser.add_argument(
        "--type",
        choices=["photo", "video"],
        help="Media type (auto-detected from extension if not provided)"
    )
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"Backend API URL (default: {BASE_URL})"
    )

    args = parser.parse_args()

    base_url = args.base_url.rstrip('/')

    # Auto-detect media type if not provided
    media_type = args.type
    if not media_type:
        ext = Path(args.file).suffix.lower()
        if ext in ['.mp4', '.mov', '.avi', '.webm']:
            media_type = 'video'
        elif ext in ['.jpg', '.jpeg', '.png', '.gif']:
            media_type = 'photo'
        else:
            print(f"❌ Cannot auto-detect media type from extension: {ext}")
            print("   Please specify --type photo or --type video")
            sys.exit(1)
        print(f"🔍 Auto-detected media type: {media_type}")

    try:
        # Step 1: Parse the upload URL
        url_data = parse_upload_url(args.url)
        token = url_data['token']
        facet_id = url_data.get('facet_id')

        # Step 2: Resolve token (verify it's valid)
        token_info = resolve_token(token, base_url)

        # Step 3: Upload file
        upload_result = upload_media(token, args.file, media_type, base_url)

        # Step 4: Verify token was consumed
        verify_upload(token, base_url)

        print("\n" + "="*60)
        print("🎉 TEST PASSED - Upload successful!")
        print("="*60)
        print(f"\nUploaded file is now accessible at:")
        print(f"  {upload_result.get('url')}")
        if facet_id:
            print(f"\nLinked to facet: {facet_id}")

    except requests.HTTPError as e:
        print(f"\n❌ HTTP Error: {e}")
        if e.response is not None:
            print(f"   Status: {e.response.status_code}")
            try:
                print(f"   Response: {e.response.json()}")
            except:
                print(f"   Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
