"""
video_generator.py — 10 saniyelik ürün videosu üretici
Bağımlılıklar: opencv-python, numpy
"""

import os
import cv2
import numpy as np
from pathlib import Path

_DEFAULT_CODECS = ["avc1", "mp4v"]

_PAN_DIRECTIONS = [
    ( 0.00,  0.00),
    ( 0.06,  0.04),
    (-0.06,  0.04),
    ( 0.06, -0.04),
    (-0.06, -0.04),
    ( 0.00,  0.05),
    ( 0.00, -0.05),
]

_TRANSITION_CYCLE = ["fade", "wipe_left", "zoom_in", "wipe_right", "slide_up"]


def _preferred_codecs():
    """
    MP4 uzantisini korur, fakat Windows'ta OpenH264 gürültüsünü azaltmak için
    daha uyumlu codec'i önce dener.
    """
    env_value = os.environ.get("VIDEO_CODECS", "").strip()
    if env_value:
        codecs = [c.strip() for c in env_value.split(",") if c.strip()]
        if codecs:
            return codecs

    if os.name == "nt":
        return ["mp4v", "avc1"]
    return list(_DEFAULT_CODECS)


def _open_writer(output_path, resolution, fps):
    w, h = resolution
    codecs = _preferred_codecs()
    for codec in codecs:
        fourcc = cv2.VideoWriter_fourcc(*codec)
        vw = cv2.VideoWriter(output_path, fourcc, fps, (w, h))
        if vw.isOpened():
            print(f"  [Video] Codec secildi: {codec} -> {Path(output_path).name}")
            return vw
        vw.release()
    raise RuntimeError(f"VideoWriter acilamadi. Codec'ler: {codecs}")


def _load_and_fit(path, resolution):
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Gorsel okunamadi: {path}")
    tw, th = resolution
    ih, iw = img.shape[:2]
    scale = min(tw / iw, th / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.zeros((th, tw, 3), dtype=np.uint8)
    y0, x0 = (th - nh) // 2, (tw - nw) // 2
    canvas[y0:y0+nh, x0:x0+nw] = resized
    return canvas


def _build_intro_frames(intro_image_path, resolution, fps, intro_seconds):
    if not intro_image_path:
        return []
    intro_path = Path(str(intro_image_path))
    if not intro_path.exists():
        return []

    intro_img = _load_and_fit(intro_path, resolution)
    intro_frames = max(1, int(round(fps * intro_seconds)))
    return [
        _ken_burns_frame(intro_img, fi, intro_frames, resolution, 1.02, (0.0, 0.0))
        for fi in range(intro_frames)
    ]


def _select_evenly(paths, n):
    if len(paths) <= n:
        return list(paths)
    indices = [round(i * (len(paths) - 1) / (n - 1)) for i in range(n)]
    return [paths[i] for i in indices]


def _ken_burns_frame(img, frame_idx, total_frames, resolution, zoom_factor, pan):
    tw, th = resolution
    t = frame_idx / max(total_frames - 1, 1)
    zoom = 1.0 + (zoom_factor - 1.0) * t
    cw, ch = max(1, int(tw / zoom)), max(1, int(th / zoom))
    max_px = int((tw - cw) * abs(pan[0]))
    max_py = int((th - ch) * abs(pan[1]))
    px = int(max_px * t * (1 if pan[0] >= 0 else -1))
    py = int(max_py * t * (1 if pan[1] >= 0 else -1))
    cx, cy = tw // 2 + px, th // 2 + py
    x1 = max(0, cx - cw // 2)
    y1 = max(0, cy - ch // 2)
    x2, y2 = min(tw, x1 + cw), min(th, y1 + ch)
    if x2 <= x1 or y2 <= y1:
        return cv2.resize(img, (tw, th), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(img[y1:y2, x1:x2], (tw, th), interpolation=cv2.INTER_LINEAR)


def _apply_transition(frame_a, frame_b, alpha, transition, resolution):
    tw, th = resolution
    if transition == "fade":
        return cv2.addWeighted(frame_a, 1.0 - alpha, frame_b, alpha, 0)
    elif transition == "wipe_left":
        split = int(tw * alpha)
        out = frame_a.copy()
        if split > 0:
            out[:, :split] = frame_b[:, :split]
        return out
    elif transition == "wipe_right":
        split = int(tw * (1.0 - alpha))
        out = frame_a.copy()
        if split < tw:
            out[:, split:] = frame_b[:, split:]
        return out
    elif transition == "zoom_in":
        scale = 1.0 + alpha * 0.25
        new_w, new_h = int(tw * scale), int(th * scale)
        scaled = cv2.resize(frame_a, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        x1, y1 = (new_w - tw) // 2, (new_h - th) // 2
        cropped = scaled[y1:y1+th, x1:x1+tw]
        return cv2.addWeighted(cropped, 1.0 - alpha, frame_b, alpha, 0)
    elif transition == "slide_up":
        offset = int(th * alpha)
        out = np.empty_like(frame_a)
        keep = th - offset
        if keep > 0:
            out[:keep] = frame_a[offset:]
        if offset > 0:
            out[keep:] = frame_b[:offset]
        return out
    return cv2.addWeighted(frame_a, 1.0 - alpha, frame_b, alpha, 0)


def generate_product_video(
    mockup_path,
    product_image_paths,
    output_path,
    *,
    include_mockup=True,
    max_product_images=7,
    resolution=(1080, 1080),
    fps=30,
    total_seconds=10,
    fade_frames=20,
    zoom_factor=1.07,
    intro_image_path=None,
    intro_seconds=1.0,
    stop_event=None,
):
    mockup_path = str(mockup_path)
    valid_products = [str(p) for p in product_image_paths if Path(str(p)).exists()]
    selected = _select_evenly(valid_products, max_product_images)

    if include_mockup:
        if not Path(mockup_path).exists():
            raise ValueError(f"Mockup bulunamadi: {mockup_path}")
        scenes = [mockup_path] + selected
    else:
        if not selected:
            raise ValueError("Hicbir gorsel bulunamadi.")
        scenes = selected

    intro_frames = _build_intro_frames(intro_image_path, resolution, fps, intro_seconds)
    n = len(scenes)
    total_frames = fps * total_seconds
    scene_total_frames = max(n, total_frames - len(intro_frames))
    base_frames = scene_total_frames // n
    scene_frame_counts = [base_frames] * n
    scene_frame_counts[-1] += scene_total_frames % n
    actual_fade = max(3, min(fade_frames, base_frames // 3))
    loaded = [_load_and_fit(p, resolution) for p in scenes]
    writer = _open_writer(output_path, resolution, fps)
    frames_written = 0

    try:
        for frame in intro_frames:
            if stop_event and stop_event.is_set():
                writer.release()
                raise InterruptedError("Durduruldu.")
            writer.write(frame)
            frames_written += 1

        for scene_idx, (img, n_frames) in enumerate(zip(loaded, scene_frame_counts)):
            pan = _PAN_DIRECTIONS[scene_idx % len(_PAN_DIRECTIONS)]
            is_last = scene_idx == n - 1
            if not is_last:
                next_img = loaded[scene_idx + 1]
                next_pan = _PAN_DIRECTIONS[(scene_idx + 1) % len(_PAN_DIRECTIONS)]
                transition = _TRANSITION_CYCLE[scene_idx % len(_TRANSITION_CYCLE)]
                fade_start = n_frames - actual_fade
            else:
                next_img = next_pan = transition = None
                fade_start = n_frames
            for fi in range(n_frames):
                if stop_event and stop_event.is_set():
                    writer.release()
                    raise InterruptedError("Durduruldu.")
                frame = _ken_burns_frame(img, fi, n_frames, resolution, zoom_factor, pan)
                if not is_last and fi >= fade_start:
                    alpha = (fi - fade_start + 1) / (actual_fade + 1)
                    next_frame = _ken_burns_frame(
                        next_img, 0, scene_frame_counts[scene_idx + 1],
                        resolution, zoom_factor, next_pan
                    )
                    frame = _apply_transition(frame, next_frame, alpha, transition, resolution)
                writer.write(frame)
                frames_written += 1
    finally:
        writer.release()

    if frames_written != total_frames:
        raise RuntimeError(f"Frame hatasi: {frames_written} != {total_frames}")
