#!/usr/bin/env python3
"""One anonymous, free, cloud-only LTX motion request on synthetic original art."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4
import zlib


SPACE = "Lightricks/ltx-video-distilled"
BASE = "https://lightricks-ltx-video-distilled.hf.space"
SPACE_SHA = "8a42e93469c66b62d794b83a4233f5fc8439e2b5"
MODEL = "Lightricks/LTX-Video"
MODEL_SHA = "8984fa25007f376c1a299016d0957a37a2f797bb"
OUT = Path("output")
SEED = 7707001
PARAMETERS = (
    "prompt", "negative_prompt", "input_image_filepath", "input_video_filepath",
    "height_ui", "width_ui", "mode", "duration_ui", "ui_frames_to_use",
    "seed_ui", "randomize_seed", "ui_guidance_scale", "improve_texture_flag",
)


def get(url: str, *, body: bytes | None = None, content_type: str = "",
        max_bytes: int = 1_000_000, timeout: int = 30):
    headers = {"User-Agent": "devkatha-public-one-shot-motion-proof/1"}
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(url, data=body, headers=headers)
    with urlopen(request, timeout=timeout) as reply:
        if urlparse(reply.geturl()).netloc != urlparse(url).netloc:
            raise ValueError("Provider redirected to another host")
        raw = reply.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Provider response exceeded the size limit")
    return raw


def get_json(url: str, **kwargs):
    return json.loads(get(url, **kwargs))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(name: str, data: object) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def preflight() -> dict:
    space = get_json(f"https://huggingface.co/api/spaces/{SPACE}")
    runtime = space.get("runtime") or {}
    hardware = runtime.get("hardware") or {}
    if not (space.get("sha") == SPACE_SHA and runtime.get("sha") == SPACE_SHA
            and runtime.get("stage") == "RUNNING"
            and hardware.get("current") == "zero-a10g"):
        raise ValueError("Official Space revision or free GPU runtime changed")
    info = get_json(f"{BASE}/gradio_api/info")
    endpoint = (info.get("named_endpoints") or {}).get("/image_to_video") or {}
    names = tuple(item.get("parameter_name") for item in endpoint.get("parameters", []))
    if names != PARAMETERS:
        raise ValueError("Official image-to-video API changed")
    model = get_json(f"https://huggingface.co/api/models/{MODEL}")
    if model.get("sha") != MODEL_SHA or (model.get("cardData") or {}).get("license") != "other":
        raise ValueError("Official model revision or license changed")
    license_text = get(
        f"https://huggingface.co/{MODEL}/resolve/{MODEL_SHA}/"
        "LTX-Video-Open-Weights-License-0.X.txt"
    ).decode().lower()
    if ("annual revenues of at least $10,000,000" not in license_text
            or "without expressly and intelligibly disclaiming" not in license_text):
        raise ValueError("Reviewed LTX model license changed")
    return {"space": SPACE, "space_sha": SPACE_SHA, "hardware": "zero-a10g",
            "model": MODEL, "model_sha": MODEL_SHA,
            "endpoint": "/image_to_video", "request_mode": "anonymous_free",
            "model_license": "LTX Open Weights 0.X; publication conditions remain",
            "credentials_used": False, "paid_api_used": False}


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(
        ">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def synthetic_source() -> bytes:
    """Original, text-free abstract lamp and water scene; generated on runner."""
    width, height = 512, 896
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            dx, dy = x - 256, y - 428
            radius = math.hypot(dx, dy)
            glow = max(0.0, 1.0 - radius / 240.0)
            if y < 628:
                base = (9 + y // 90, 22 + y // 42, 45 + y // 24)
            else:
                wave = math.sin(x * 0.065 + y * 0.11)
                base = (8, 44 + int(10 * wave), 72 + int(17 * wave))
            red = base[0] + int(36 * glow)
            green = base[1] + int(25 * glow)
            blue = base[2] + int(4 * glow)
            if 85 < radius < 130 and y < 570:
                swirl = math.sin(math.atan2(dy, dx) * 8 + radius / 8)
                red, green, blue = 210 + int(28 * swirl), 139 + int(25 * swirl), 39
            elif radius < 85 and y < 570:
                red, green, blue = 115, 74, 34
            row.extend((min(255, max(0, red)), min(255, max(0, green)),
                        min(255, max(0, blue))))
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), level=6)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header)
            + png_chunk(b"IDAT", raw) + png_chunk(b"IEND", b""))


def upload(image: bytes) -> str:
    boundary = "proof-" + uuid4().hex
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; "
            "filename=\"source.png\"\r\nContent-Type: image/png\r\n\r\n").encode()
    body = head + image + f"\r\n--{boundary}--\r\n".encode()
    result = json.loads(get(f"{BASE}/gradio_api/upload", body=body,
                            content_type=f"multipart/form-data; boundary={boundary}",
                            max_bytes=10_000, timeout=60))
    if not (isinstance(result, list) and len(result) == 1
            and isinstance(result[0], str) and result[0].startswith("/tmp/")
            and ".." not in result[0]):
        raise ValueError("Space returned no image upload path")
    return result[0]


def submit(image_path: str) -> str:
    prompt = ("One continuous locked-camera cinematic shot. The single ornate "
              "golden disc rises clearly above the dark river and spins "
              "clockwise while broad bright ripples push outward across the "
              "water. The disc remains one coherent object. Visible strong "
              "subject movement and water motion; no cut, no people, no text.")
    negative = ("still frame, barely moving subject, duplicate disc, extra "
                "objects, distorted ring, text, subtitles, watermark, flicker")
    payload = {"data": [prompt, negative,
                        {"path": image_path, "orig_name": "source.png",
                         "meta": {"_type": "gradio.FileData"}},
                        None, 896, 512, "image-to-video", 5.0, 9, SEED,
                        False, 3.0, True]}
    result = get_json(f"{BASE}/gradio_api/call/image_to_video",
                      body=json.dumps(payload).encode(), content_type="application/json",
                      max_bytes=10_000, timeout=60)
    event_id = result.get("event_id")
    if not (isinstance(event_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,160}", event_id)):
        raise ValueError("Space returned no bounded job ID")
    return event_id


def receive(event_id: str):
    url = f"{BASE}/gradio_api/call/image_to_video/{quote(event_id)}"
    request = Request(url, headers={"Accept": "text/event-stream",
                                    "User-Agent": "devkatha-public-one-shot-motion-proof/1"})
    with urlopen(request, timeout=600) as reply:
        if urlparse(reply.geturl()).netloc != urlparse(BASE).netloc:
            raise ValueError("Space job stream redirected")
        event = ""
        data = ""
        total = 0
        while line := reply.readline():
            total += len(line)
            if total > 300_000:
                raise ValueError("Space job stream exceeded size cap")
            text = line.decode("utf-8", "replace").rstrip("\r\n")
            if text.startswith("event: "):
                event = text[7:]
            elif text.startswith("data: "):
                data += text[6:]
            elif not text:
                if event == "complete":
                    return json.loads(data)
                if event == "error":
                    raise ValueError("Space job returned error")
                event, data = "", ""
    raise ValueError("Space job ended without a result")


def download(result) -> bytes:
    if not (isinstance(result, list) and len(result) == 2 and result[1] == SEED):
        raise ValueError("Space result or fixed seed changed")
    value = result[0]
    if isinstance(value, dict) and isinstance(value.get("video"), dict):
        value = value["video"]
    url = value.get("url") if isinstance(value, dict) else None
    parsed = urlparse(url) if isinstance(url, str) else None
    if not (parsed and parsed.scheme == "https" and parsed.netloc == urlparse(BASE).netloc
            and parsed.path.startswith("/gradio_api/file=") and not parsed.fragment):
        raise ValueError("Space returned no same-host video URL")
    video = get(url, max_bytes=15_000_000, timeout=120)
    if len(video) < 20_000:
        raise ValueError("Space returned empty video")
    return video


def inspect(path: Path) -> dict:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
         "format=duration:stream=codec_type,width,height,r_frame_rate,nb_read_frames",
         "-of", "json", str(path)], check=True, capture_output=True, text=True)
    media = json.loads(probe.stdout)
    stream = [s for s in media.get("streams", []) if s.get("codec_type") == "video"]
    if len(stream) != 1:
        raise ValueError("Space video stream count changed")
    video = stream[0]
    duration = float(media["format"]["duration"])
    if not (video.get("width") == 512 and video.get("height") == 896
            and 4.4 <= duration <= 5.4):
        raise ValueError("Space video dimensions or duration changed")
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                   check=True, capture_output=True, timeout=90)
    for label, at in (("early", .1), ("middle", duration / 2), ("late", duration - .1)):
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(path),
                        "-frames:v", "1", "-y", str(OUT / f"{label}.jpg")],
                       check=True, capture_output=True, timeout=30)
    return {"width": video["width"], "height": video["height"],
            "fps": video.get("r_frame_rate"), "frames": video.get("nb_read_frames"),
            "duration_seconds": duration, "full_decode": True,
            "bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "run"):
        raise SystemExit("usage: pilot.py preflight|run")
    stage = "preflight"
    try:
        proof = preflight()
        save("provider.json", proof)
        if sys.argv[1] == "preflight":
            output_file = os.environ.get("GITHUB_OUTPUT")
            if output_file:
                with open(output_file, "a") as stream:
                    stream.write("ready=true\n")
            print("Official licensed ZeroGPU Space is running; no GPU call made")
            return 0
        source = synthetic_source()
        (OUT / "source.png").write_bytes(source)
        stage = "upload_image"
        image_path = upload(source)
        stage = "submit_job"
        start = time.monotonic()
        event_id = submit(image_path)
        stage = "receive_job"
        result = receive(event_id)
        elapsed = round(time.monotonic() - start, 2)
        stage = "download_video"
        video = download(result)
        target = OUT / "candidate.mp4"
        target.write_bytes(video)
        stage = "inspect_video"
        metrics = inspect(target)
        save("receipt.json", {"status": "needs_visual_review", "approved": False,
                              "finished_reel": False, "source_sha256": sha(source),
                              "provider": proof, "seed": SEED,
                              "requested_seconds": 5.0,
                              "request_to_completion_seconds": elapsed,
                              "media": metrics, "paid_api_used": False,
                              "cloud_runner": os.environ.get("RUNNER_OS")})
        print("Candidate video returned and decoded:", json.dumps(metrics, sort_keys=True))
        return 0
    except Exception as error:
        if sys.argv[1] == "preflight":
            output_file = os.environ.get("GITHUB_OUTPUT")
            if output_file:
                with open(output_file, "a") as stream:
                    stream.write("ready=false\n")
        save("receipt.json", {"status": "no_candidate", "approved": False,
                              "finished_reel": False, "failure_stage": stage,
                              "error_type": type(error).__name__,
                              "http_status": error.code if isinstance(error, HTTPError) else None,
                              "paid_api_used": False})
        print("One-shot proof held at", stage, type(error).__name__)
        return 0 if sys.argv[1] == "preflight" else 1


if __name__ == "__main__":
    raise SystemExit(main())
