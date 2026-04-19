#!/usr/bin/env python3
"""
servo_dashboard.py — Web dashboard for ST3215 servo control
Usage: python3 servo_dashboard.py
Then open http://localhost:5000 in your browser
"""

import csv
import json
import base64
import os
import select
import shutil
import subprocess
import sys
import time
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib import parse as urllib_parse
from urllib import error as urllib_error
from urllib import request as urllib_request
from flask import Flask, Response, jsonify, request, render_template, send_file

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

sys.path.insert(0, '.')
from st3215.port_handler import PortHandler
from st3215.protocol_packet_handler import protocol_packet_handler
import st3215.values as V

DEVICE    = '/dev/ttyACM0'
BAUD      = 1_000_000
KNOWN_IDS = list(range(1, 7))  # IDs 1-6
PAIR_MAPPINGS = {
    1: 8,
    2: 7,
    3: 9,
    4: 10,
    5: 11,
    6: 12,
}
PAIR_INVERTED = {
    6: True,  # 12 -> 6 is mirrored relative to the leader arm
}
FOLLOWER_IDS = list(KNOWN_IDS)
LEADER_IDS = sorted(PAIR_MAPPINGS.values())
TRACKED_IDS = sorted(set(FOLLOWER_IDS + LEADER_IDS))
RAW_MAX   = 4095
RAW_MOD   = RAW_MAX + 1
CAMERA_SOURCE = os.getenv('SERVO_DASHBOARD_CAMERA', 'auto')
CAMERA_WIDTH = int(os.getenv('SERVO_DASHBOARD_CAMERA_WIDTH', '640'))
CAMERA_HEIGHT = int(os.getenv('SERVO_DASHBOARD_CAMERA_HEIGHT', '480'))
CAMERA_FPS = int(os.getenv('SERVO_DASHBOARD_CAMERA_FPS', '20'))
CAMERA_STREAM_FPS = int(os.getenv('SERVO_DASHBOARD_STREAM_FPS', '10'))
CAMERA_JPEG_QUALITY = int(os.getenv('SERVO_DASHBOARD_JPEG_QUALITY', '80'))
CAMERA_ROTATION = os.getenv('SERVO_DASHBOARD_CAMERA_ROTATION', 'left').strip().lower()
YOLO26_ROOT = os.getenv(
    'SERVO_DASHBOARD_YOLO26_ROOT',
    '/home/grafito/Grafito-Edge-Services/Vision-System-Experiments/yolo26_hailo',
)
YOLO26_PYTHON_DIR = os.path.join(YOLO26_ROOT, 'python')
YOLO26_HEF_PATH = os.getenv(
    'SERVO_DASHBOARD_HEF',
    os.path.join(YOLO26_ROOT, 'models', 'yolo26n_seg.hef'),
)
DETECTION_CONFIDENCE = float(os.getenv('SERVO_DASHBOARD_DET_CONF', '0.1'))
DETECTION_IOU = float(os.getenv('SERVO_DASHBOARD_DET_IOU', '0.5'))
DETECTION_MASK_THRESHOLD = float(os.getenv('SERVO_DASHBOARD_MASK_THRESHOLD', '0.5'))
DETECTION_FPS = int(os.getenv('SERVO_DASHBOARD_DET_FPS', '8'))
DETECTION_JPEG_QUALITY = int(os.getenv('SERVO_DASHBOARD_DET_JPEG_QUALITY', '85'))
MOTION_RECORD_DIR = os.getenv('SERVO_DASHBOARD_MOTION_DIR', 'motion_recordings')
MOTION_PLAYBACK_SPEED = int(os.getenv('SERVO_DASHBOARD_MOTION_PLAYBACK_SPEED', '1400'))
GOOGLE_API_KEY = os.getenv('SERVO_DASHBOARD_GOOGLE_API_KEY', '')
GOOGLE_MODEL = os.getenv('SERVO_DASHBOARD_GOOGLE_MODEL', 'gemma-4-26b-a4b-it')
GOOGLE_GENERATE_ENDPOINT = os.getenv(
    'SERVO_DASHBOARD_GOOGLE_GENERATE_ENDPOINT',
    'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
)
GOOGLE_TIMEOUT_S = float(os.getenv('SERVO_DASHBOARD_GOOGLE_TIMEOUT_S', '90'))
GOOGLE_INSIGHTS_PROMPT = os.getenv(
    'SERVO_DASHBOARD_GOOGLE_PROMPT',
    'Analyze this robot camera frame and give concise operator insights. '
    'Respond with 4 short bullet points covering: scene summary, important objects, '
    'robot relevance, and any immediate caution. Keep it practical and under 120 words.',
)
GOOGLE_ARM_PLAN_PROMPT = os.getenv(
    'SERVO_DASHBOARD_GOOGLE_ARM_PLAN_PROMPT',
    'You are generating a safe robot arm pose suggestion from a camera frame. '
    'Return JSON only. Use the provided joint limits and current joint angles. '
    'Do not invent joints or omit any of the 6 joints. Keep targets conservative. '
    'If the scene is unclear, keep joints near current values and set action to "hold".',
)
GOOGLE_ARM_PLAN_SPEED = int(os.getenv('SERVO_DASHBOARD_GOOGLE_ARM_PLAN_SPEED', '280'))
PAIR_SYNC_HZ = float(os.getenv('SERVO_DASHBOARD_PAIR_SYNC_HZ', '6.0'))
PAIR_SYNC_SPEED = int(os.getenv('SERVO_DASHBOARD_PAIR_SYNC_SPEED', '360'))
PAIR_SYNC_DEADBAND_RAW = int(os.getenv('SERVO_DASHBOARD_PAIR_SYNC_DEADBAND_RAW', '6'))
PAIR_SYNC_RANGE_MIN_RAW = int(os.getenv('SERVO_DASHBOARD_PAIR_SYNC_RANGE_MIN_RAW', '80'))
PAIR_SYNC_MAX_STEP_RAW = int(os.getenv('SERVO_DASHBOARD_PAIR_SYNC_MAX_STEP_RAW', '180'))
AUTO_LIMIT_STEP = int(os.getenv('SERVO_DASHBOARD_AUTO_LIMIT_STEP', '55'))
AUTO_LIMIT_SPEED = int(os.getenv('SERVO_DASHBOARD_AUTO_LIMIT_SPEED', '260'))
AUTO_LIMIT_SETTLE = float(os.getenv('SERVO_DASHBOARD_AUTO_LIMIT_SETTLE', '0.45'))
AUTO_LIMIT_STALL_DELTA = int(os.getenv('SERVO_DASHBOARD_AUTO_LIMIT_STALL_DELTA', '8'))
AUTO_LIMIT_STALL_COUNT = int(os.getenv('SERVO_DASHBOARD_AUTO_LIMIT_STALL_COUNT', '3'))
AUTO_LIMIT_MAX_STEPS = int(os.getenv('SERVO_DASHBOARD_AUTO_LIMIT_MAX_STEPS', '36'))
AUTO_LIMIT_LOAD_THRESHOLD = int(os.getenv('SERVO_DASHBOARD_AUTO_LIMIT_LOAD_THRESHOLD', '850'))
AUTO_LIMIT_CURRENT_THRESHOLD = int(os.getenv('SERVO_DASHBOARD_AUTO_LIMIT_CURRENT_THRESHOLD', '320'))
AUTO_BASE_ID = int(os.getenv('SERVO_DASHBOARD_AUTO_BASE_ID', '1'))
AUTO_SHOULDER_ID = int(os.getenv('SERVO_DASHBOARD_AUTO_SHOULDER_ID', '2'))
AUTO_ELBOW_ID = int(os.getenv('SERVO_DASHBOARD_AUTO_ELBOW_ID', '3'))
AUTO_WRIST_ID = int(os.getenv('SERVO_DASHBOARD_AUTO_WRIST_ID', '4'))
AUTO_ROLL_ID = int(os.getenv('SERVO_DASHBOARD_AUTO_ROLL_ID', '5'))
AUTO_GRIPPER_ID = int(os.getenv('SERVO_DASHBOARD_AUTO_GRIPPER_ID', '6'))
AUTO_TRACK_SPEED = int(os.getenv('SERVO_DASHBOARD_AUTO_SPEED', '300'))
AUTO_GRAB_SPEED = int(os.getenv('SERVO_DASHBOARD_AUTO_GRAB_SPEED', '220'))
AUTO_LOOP_HZ = float(os.getenv('SERVO_DASHBOARD_AUTO_LOOP_HZ', '2.5'))
AUTO_CENTER_X_TOL = float(os.getenv('SERVO_DASHBOARD_AUTO_CENTER_X_TOL', '0.09'))
AUTO_CENTER_Y_TOL = float(os.getenv('SERVO_DASHBOARD_AUTO_CENTER_Y_TOL', '0.11'))
AUTO_GRAB_AREA = float(os.getenv('SERVO_DASHBOARD_AUTO_GRAB_AREA', '0.085'))
AUTO_BASE_SIGN = int(os.getenv('SERVO_DASHBOARD_AUTO_BASE_SIGN', '-1'))
AUTO_VERTICAL_SIGN = int(os.getenv('SERVO_DASHBOARD_AUTO_VERTICAL_SIGN', '1'))
AUTO_BASE_GAIN = float(os.getenv('SERVO_DASHBOARD_AUTO_BASE_GAIN', '220'))
AUTO_SHOULDER_GAIN = float(os.getenv('SERVO_DASHBOARD_AUTO_SHOULDER_GAIN', '160'))
AUTO_ELBOW_GAIN = float(os.getenv('SERVO_DASHBOARD_AUTO_ELBOW_GAIN', '120'))
AUTO_WRIST_GAIN = float(os.getenv('SERVO_DASHBOARD_AUTO_WRIST_GAIN', '90'))
AUTO_APPROACH_SHOULDER = int(os.getenv('SERVO_DASHBOARD_AUTO_APPROACH_SHOULDER', '35'))
AUTO_APPROACH_ELBOW = int(os.getenv('SERVO_DASHBOARD_AUTO_APPROACH_ELBOW', '28'))
AUTO_APPROACH_WRIST = int(os.getenv('SERVO_DASHBOARD_AUTO_APPROACH_WRIST', '22'))
AUTO_LIFT_SHOULDER = int(os.getenv('SERVO_DASHBOARD_AUTO_LIFT_SHOULDER', '-120'))
AUTO_LIFT_ELBOW = int(os.getenv('SERVO_DASHBOARD_AUTO_LIFT_ELBOW', '-90'))
AUTO_LIFT_WRIST = int(os.getenv('SERVO_DASHBOARD_AUTO_LIFT_WRIST', '-60'))
AUTO_GRIPPER_OPEN = int(os.getenv('SERVO_DASHBOARD_AUTO_GRIPPER_OPEN', '3920'))
AUTO_GRIPPER_CLOSE = int(os.getenv('SERVO_DASHBOARD_AUTO_GRIPPER_CLOSE', '3340'))
AUTO_ALIGN_SETTLE = float(os.getenv('SERVO_DASHBOARD_AUTO_ALIGN_SETTLE', '0.45'))
AUTO_GRIP_SETTLE = float(os.getenv('SERVO_DASHBOARD_AUTO_GRIP_SETTLE', '0.7'))

DEFAULT_LIMITS = {
    1: {'min': 2782, 'max': 4095},
    2: {'min': 0, 'max': 3582},
    3: {'min': 1, 'max': 1706},
    4: {'min': 1, 'max': 2041},
    5: {'min': 2042, 'max': 4095},
}

app = Flask(__name__)
_bus = None


def load_local_dashboard_settings() -> Dict[str, Any]:
    settings_path = os.path.join(os.path.dirname(__file__), '.dashboard_secrets.json')
    if not os.path.exists(settings_path):
        return {}
    try:
        with open(settings_path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


LOCAL_DASHBOARD_SETTINGS = load_local_dashboard_settings()
if not GOOGLE_API_KEY:
    GOOGLE_API_KEY = str(LOCAL_DASHBOARD_SETTINGS.get('google_api_key', '') or '')
local_google_model = str(LOCAL_DASHBOARD_SETTINGS.get('google_model', '') or '')
if local_google_model:
    GOOGLE_MODEL = local_google_model


# ── Camera stream ────────────────────────────────────────────────────────────
def render_status_jpeg(title: str, subtitle: str, message: str, width: int, height: int) -> bytes:
    if cv2 is None or np is None:
        return b''

    frame = np.zeros((max(height, 240), max(width, 320), 3), dtype=np.uint8)
    frame[:] = (17, 24, 39)
    cv2.putText(frame, title, (24, 54), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (125, 211, 252), 2, cv2.LINE_AA)
    cv2.putText(frame, subtitle, (24, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (226, 232, 240), 2, cv2.LINE_AA)

    max_chars = max(24, (frame.shape[1] - 48) // 12)
    words = (message or '').split()
    lines: List[str] = []
    current = ''
    for word in words:
        candidate = word if not current else f'{current} {word}'
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if not lines:
        lines = ['No status available']

    for idx, line in enumerate(lines[:6]):
        y = 142 + idx * 28
        cv2.putText(frame, line, (24, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (148, 163, 184), 2, cv2.LINE_AA)

    ok, encoded = cv2.imencode(
        '.jpg',
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), CAMERA_JPEG_QUALITY],
    )
    return encoded.tobytes() if ok else b''


def apply_camera_rotation(frame: np.ndarray) -> np.ndarray:
    if frame is None:
        return frame
    if CAMERA_ROTATION in ('left', '90left', 'ccw', '270'):
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if CAMERA_ROTATION in ('right', '90right', 'cw', '90'):
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if CAMERA_ROTATION in ('180', 'flip'):
        return cv2.rotate(frame, cv2.ROTATE_180)
    return frame


class CameraStream:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame_lock = threading.Lock()
        self.capture = None
        self.thread = None
        self.running = False
        self.ready = False
        self.error = 'Camera idle'
        self.source_label = None
        self.last_frame = None
        self.last_image = None
        self.last_frame_at = 0.0
        self.last_frame_seq = 0

    def start(self) -> None:
        if cv2 is None or np is None:
            self.error = 'OpenCV is not installed'
            return
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.running = True
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()

    def _source_candidates(self) -> List[Any]:
        candidates: List[Any] = []
        raw_source = (CAMERA_SOURCE or 'auto').strip()
        if raw_source and raw_source.lower() != 'auto':
            candidates.append(int(raw_source) if raw_source.isdigit() else raw_source)
        for idx in range(4):
            device = f'/dev/video{idx}'
            if os.path.exists(device):
                candidates.append(device)
        candidates.extend(range(4))

        unique: List[Any] = []
        seen = set()
        for candidate in candidates:
            key = self._source_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    @staticmethod
    def _source_key(candidate: Any) -> str:
        if isinstance(candidate, int):
            return f'video-index:{candidate}'
        if isinstance(candidate, str) and candidate.startswith('/dev/video'):
            suffix = candidate.removeprefix('/dev/video')
            if suffix.isdigit():
                return f'video-index:{suffix}'
        return str(candidate)

    @staticmethod
    def _configure_capture(cap, pixel_format: Optional[str] = None) -> None:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if pixel_format:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*pixel_format))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 1)

    @staticmethod
    def _warmup_capture(cap) -> Tuple[bool, Optional[np.ndarray]]:
        frame = None
        for attempt in range(12):
            ok, candidate = cap.read()
            if ok and candidate is not None and candidate.size:
                frame = candidate
                return True, frame
            time.sleep(0.08 if attempt < 4 else 0.12)
        return False, frame

    @staticmethod
    def _ffmpeg_input_formats() -> List[Optional[str]]:
        return [None, 'yuyv422', 'mjpeg']

    def _open_ffmpeg_capture(self, source: str):
        if not isinstance(source, str) or not source.startswith('/dev/video'):
            return None, None
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            return None, None

        errors: List[str] = []
        for input_format in self._ffmpeg_input_formats():
            cap = FFmpegMJPEGCapture(
                ffmpeg_path=ffmpeg_path,
                source=source,
                width=CAMERA_WIDTH,
                height=CAMERA_HEIGHT,
                fps=CAMERA_FPS,
                input_format=input_format,
            )
            if not cap.isOpened():
                cap.release()
                continue
            ok, frame = self._warmup_capture(cap)
            if ok and frame is not None:
                fmt = input_format or 'native'
                return cap, f'{source} (ffmpeg {fmt})'
            fmt = input_format or 'native'
            errors.append(f'{source} [ffmpeg {fmt}] opened but no frames after warmup')
            cap.release()

        return None, ', '.join(errors) or None

    def _open_capture(self):
        errors = []
        for source in self._source_candidates():
            for backend in (cv2.CAP_V4L2, cv2.CAP_ANY):
                for pixel_format in (None, 'YUYV', 'MJPG'):
                    cap = cv2.VideoCapture(source, backend)
                    if not cap or not cap.isOpened():
                        if cap:
                            cap.release()
                        continue
                    self._configure_capture(cap, pixel_format=pixel_format)
                    ok, frame = self._warmup_capture(cap)
                    if ok and frame is not None:
                        fmt = pixel_format or 'native'
                        return cap, f'{source} ({fmt})'
                    fmt = pixel_format or 'native'
                    errors.append(f'{source} [{fmt}] opened but no frames after warmup')
                    cap.release()
            ffmpeg_cap, ffmpeg_info = self._open_ffmpeg_capture(source)
            if ffmpeg_cap is not None:
                return ffmpeg_cap, ffmpeg_info
            if ffmpeg_info:
                errors.append(ffmpeg_info)
        return None, ', '.join(errors) or 'No camera found'

    def _release_capture(self) -> None:
        with self.lock:
            cap = self.capture
            self.capture = None
            self.source_label = None
            self.ready = False
        if cap:
            cap.release()

    def _capture_loop(self) -> None:
        while self.running:
            if self.capture is None:
                cap, info = self._open_capture()
                if cap is None:
                    self.error = info
                    time.sleep(2.0)
                    continue
                with self.lock:
                    self.capture = cap
                    self.source_label = info
                    self.error = None

            ok, frame = self.capture.read()
            if not ok or frame is None:
                self.error = f'Camera feed lost from {self.source_label}'
                self._release_capture()
                time.sleep(1.0)
                continue

            frame = apply_camera_rotation(frame)

            ok, encoded = cv2.imencode(
                '.jpg',
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), CAMERA_JPEG_QUALITY],
            )
            if ok:
                with self.frame_lock:
                    self.last_image = frame.copy()
                    self.last_frame = encoded.tobytes()
                    self.last_frame_at = time.time()
                    self.last_frame_seq += 1
                self.ready = True
                self.error = None

            time.sleep(1.0 / max(CAMERA_FPS, 1))

    def get_frame(self) -> bytes:
        self.start()
        with self.frame_lock:
            frame = self.last_frame
            age = time.time() - self.last_frame_at if self.last_frame_at else None
        if frame and (age is None or age < 2.0):
            return frame
        return render_status_jpeg(
            'USB Camera',
            'Waiting for stream...',
            self.error or 'Connecting to camera',
            CAMERA_WIDTH,
            CAMERA_HEIGHT,
        )

    def get_frame_data(self) -> Tuple[Optional[np.ndarray], float, int]:
        self.start()
        with self.frame_lock:
            image = self.last_image.copy() if self.last_image is not None else None
            frame_at = self.last_frame_at
            frame_seq = self.last_frame_seq
        return image, frame_at, frame_seq

    def status(self) -> Dict[str, Any]:
        age = None
        if self.last_frame_at:
            age = round(time.time() - self.last_frame_at, 2)
        return {
            'opencv': cv2 is not None,
            'running': bool(self.thread and self.thread.is_alive()),
            'ready': self.ready,
            'source': self.source_label,
            'error': self.error,
            'frame_age_s': age,
            'configured_source': CAMERA_SOURCE,
        }


_camera = CameraStream()


class FFmpegMJPEGCapture:
    def __init__(
        self,
        ffmpeg_path: str,
        source: str,
        width: int,
        height: int,
        fps: int,
        input_format: Optional[str] = None,
    ):
        self.buffer = bytearray()
        self.process = None
        cmd = [
            ffmpeg_path,
            '-hide_banner',
            '-loglevel',
            'error',
            '-fflags',
            'nobuffer',
            '-flags',
            'low_delay',
            '-f',
            'video4linux2',
        ]
        if input_format:
            cmd.extend(['-input_format', input_format])
        cmd.extend([
            '-video_size',
            f'{width}x{height}',
            '-framerate',
            str(max(fps, 1)),
            '-i',
            source,
            '-an',
            '-c:v',
            'mjpeg',
            '-q:v',
            '5',
            '-f',
            'image2pipe',
            '-',
        ])
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                bufsize=0,
            )
        except Exception:
            self.process = None

    def isOpened(self) -> bool:
        return bool(
            self.process
            and self.process.stdout is not None
            and self.process.poll() is None
        )

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.isOpened():
            return False, None
        frame_bytes = self._read_jpeg_frame(timeout_s=1.4)
        if not frame_bytes:
            return False, None
        encoded = np.frombuffer(frame_bytes, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None or not getattr(frame, 'size', 0):
            return False, None
        return True, frame

    def _read_jpeg_frame(self, timeout_s: float) -> Optional[bytes]:
        if not self.isOpened() or self.process.stdout is None:
            return None

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            start = self.buffer.find(b'\xff\xd8')
            if start != -1:
                end = self.buffer.find(b'\xff\xd9', start + 2)
                if end != -1:
                    frame = bytes(self.buffer[start:end + 2])
                    del self.buffer[:end + 2]
                    return frame

            remaining = max(deadline - time.time(), 0.05)
            ready, _, _ = select.select([self.process.stdout], [], [], remaining)
            if not ready:
                continue
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                return None
            self.buffer.extend(chunk)
        return None

    def release(self) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1.0)
        self.process = None


class VisionInsightsManager:
    def __init__(self, camera: CameraStream):
        self.camera = camera
        self.lock = threading.Lock()
        self.thread = None
        self.busy = False
        self.message = 'Idle'
        self.last_result = None
        self.last_error = None
        self.last_updated_at = None
        self.last_arm_plan = None
        self.last_arm_plan_raw = None
        self.last_arm_plan_error = None
        self.last_arm_plan_updated_at = None

    def status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                'busy': self.busy,
                'message': self.message,
                'result': self.last_result,
                'error': self.last_error,
                'model': GOOGLE_MODEL,
                'updated_at': self.last_updated_at,
                'arm_plan': self.last_arm_plan,
                'arm_plan_raw': self.last_arm_plan_raw,
                'arm_plan_error': self.last_arm_plan_error,
                'arm_plan_updated_at': self.last_arm_plan_updated_at,
            }

    def start(self, detector_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._start_worker('insights', detector_payload)

    def start_arm_plan(self, detector_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._start_worker('arm_plan', detector_payload)

    def _start_worker(self, task: str, detector_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.message = 'Gemma request already running'
            else:
                self.busy = True
                if task == 'arm_plan':
                    self.last_arm_plan_error = None
                    self.message = 'Capturing frame and generating robot arm plan...'
                else:
                    self.last_error = None
                    self.message = 'Capturing frame and generating Gemma insights...'
                self.thread = threading.Thread(
                    target=self._worker,
                    args=(task, detector_payload or {}),
                    daemon=True,
                )
                self.thread.start()
        return self.status()

    def _worker(self, task: str, detector_payload: Dict[str, Any]) -> None:
        try:
            if not GOOGLE_API_KEY:
                raise RuntimeError('Google API key is not configured in SERVO_DASHBOARD_GOOGLE_API_KEY')
            frame_bgr, _, _ = self.camera.get_frame_data()
            if frame_bgr is None:
                raise RuntimeError('No live camera frame available')

            ok, encoded = cv2.imencode('.jpg', frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            if not ok:
                raise RuntimeError('Could not encode current frame')
            image_b64 = base64.b64encode(encoded.tobytes()).decode('ascii')

            if task == 'arm_plan':
                prompt = self._build_arm_plan_prompt(detector_payload)
            else:
                prompt = self._build_insights_prompt(detector_payload)

            response_text = self._generate_from_google(prompt, image_b64)
            if not response_text:
                raise RuntimeError('Gemma API returned an empty response')

            if task == 'arm_plan':
                arm_plan = self._parse_arm_plan(response_text)
                with self.lock:
                    self.last_arm_plan = arm_plan
                    self.last_arm_plan_raw = response_text
                    self.last_arm_plan_error = None
                    self.message = 'Robot arm plan ready'
                    self.last_arm_plan_updated_at = datetime.now().isoformat(timespec='seconds')
                    self.busy = False
            else:
                with self.lock:
                    self.last_result = response_text
                    self.last_error = None
                    self.message = 'Gemma insights ready'
                    self.last_updated_at = datetime.now().isoformat(timespec='seconds')
                    self.busy = False
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='ignore')
            with self.lock:
                if task == 'arm_plan':
                    self.last_arm_plan_error = f'Google API HTTP {exc.code}: {detail or exc.reason}'
                    self.message = 'Robot arm plan generation failed'
                else:
                    self.last_error = f'Google API HTTP {exc.code}: {detail or exc.reason}'
                    self.message = 'Gemma insight generation failed'
                self.busy = False
        except Exception as exc:
            with self.lock:
                if task == 'arm_plan':
                    self.last_arm_plan_error = str(exc)
                    self.message = 'Robot arm plan generation failed'
                else:
                    self.last_error = str(exc)
                    self.message = 'Gemma insight generation failed'
                self.busy = False

    @staticmethod
    def _extract_response_text(data: Dict[str, Any]) -> str:
        parts = (
            data.get('candidates', [{}])[0]
            .get('content', {})
            .get('parts', [])
        )
        return '\n'.join(
            part.get('text', '').strip()
            for part in parts
            if part.get('text')
        ).strip()

    def _generate_from_google(self, prompt: str, image_b64: str) -> str:
        endpoint = GOOGLE_GENERATE_ENDPOINT.format(model=GOOGLE_MODEL)
        url = f'{endpoint}?key={urllib_parse.quote(GOOGLE_API_KEY, safe="")}'
        payload = json.dumps({
            'contents': [
                {
                    'role': 'user',
                    'parts': [
                        {'text': prompt},
                        {
                            'inline_data': {
                                'mime_type': 'image/jpeg',
                                'data': image_b64,
                            }
                        },
                    ],
                }
            ],
        }).encode('utf-8')

        req = urllib_request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib_request.urlopen(req, timeout=GOOGLE_TIMEOUT_S) as resp:
            body = resp.read().decode('utf-8')
        data = json.loads(body)
        return self._extract_response_text(data)

    @staticmethod
    def _build_insights_prompt(detector_payload: Dict[str, Any]) -> str:
        prompt = GOOGLE_INSIGHTS_PROMPT
        detections = detector_payload.get('detections_data') or []
        if detections:
            summary = '; '.join(
                f"{det.get('cls_name', 'obj')} conf={det.get('conf', 0):.2f} area={det.get('area_ratio', 0)}"
                for det in detections[:5]
            )
            prompt += f'\nCurrent detector summary: {summary}.'
        return prompt

    @staticmethod
    def _joint_context() -> List[Dict[str, Any]]:
        joints: List[Dict[str, Any]] = []
        for sid in KNOWN_IDS:
            state = servo_state.get(sid, {})
            raw = state.get('raw')
            min_raw = sw_min.get(sid, 0)
            max_raw = sw_max.get(sid, RAW_MAX)
            joints.append({
                'id': sid,
                'current_raw': raw,
                'current_angle_deg': round(raw / RAW_MAX * 270.0, 2) if raw is not None else None,
                'min_raw': min_raw,
                'max_raw': max_raw,
                'min_angle_deg': round(min_raw / RAW_MAX * 270.0, 2),
                'max_angle_deg': round(max_raw / RAW_MAX * 270.0, 2),
                'torque_enabled': torque_state.get(sid, True),
            })
        return joints

    def _build_arm_plan_prompt(self, detector_payload: Dict[str, Any]) -> str:
        detections = detector_payload.get('detections_data') or []
        selected_target = detector_payload.get('selected_target')
        target_summary = selected_target or (detections[0] if detections else None)
        return (
            f'{GOOGLE_ARM_PLAN_PROMPT}\n\n'
            'Return exactly one JSON object with this schema:\n'
            '{\n'
            '  "scene_summary": "short text",\n'
            '  "target_object": "object name or unknown",\n'
            '  "action": "hold|align|approach|grab",\n'
            '  "speed": 280,\n'
            '  "notes": "short operator note",\n'
            '  "joints": [\n'
            '    {"id": 1, "angle_deg": 135.0, "reason": "..."},\n'
            '    {"id": 2, "angle_deg": 120.0, "reason": "..."},\n'
            '    {"id": 3, "angle_deg": 90.0, "reason": "..."},\n'
            '    {"id": 4, "angle_deg": 140.0, "reason": "..."},\n'
            '    {"id": 5, "angle_deg": 135.0, "reason": "..."},\n'
            '    {"id": 6, "angle_deg": 200.0, "reason": "..."}\n'
            '  ]\n'
            '}\n'
            'Rules:\n'
            '- JSON only, no markdown, no code fences.\n'
            '- Include all six joints exactly once.\n'
            '- Keep every angle_deg within the provided min and max.\n'
            '- Use small changes from current pose unless the image clearly supports a larger move.\n'
            '- If uncertain, choose action "hold" and keep joints close to current values.\n\n'
            f'Current joints: {json.dumps(self._joint_context(), ensure_ascii=True)}\n'
            f'Selected target: {json.dumps(target_summary, ensure_ascii=True) if target_summary else "null"}\n'
            f'Visible detections: {json.dumps(detections[:6], ensure_ascii=True)}'
        )

    @staticmethod
    def _extract_json_object(text: str) -> Dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith('```'):
            lines = [line for line in cleaned.splitlines() if not line.strip().startswith('```')]
            cleaned = '\n'.join(lines).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            pass

        start = cleaned.find('{')
        if start == -1:
            raise RuntimeError('Gemma did not return a JSON object')
        depth = 0
        for idx in range(start, len(cleaned)):
            char = cleaned[idx]
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    return json.loads(cleaned[start:idx + 1])
        raise RuntimeError('Could not parse JSON object from Gemma response')

    @staticmethod
    def _clamp_angle_to_raw(sid: int, angle_deg: float) -> Tuple[float, int]:
        raw = int(round((float(angle_deg) / 270.0) * RAW_MAX))
        clamped_raw = clamp_raw_to_limits(sid, raw)
        clamped_angle = round(clamped_raw / RAW_MAX * 270.0, 2)
        return clamped_angle, clamped_raw

    def _parse_arm_plan(self, response_text: str) -> Dict[str, Any]:
        payload = self._extract_json_object(response_text)
        joints = payload.get('joints')
        if not isinstance(joints, list):
            raise RuntimeError('Arm plan JSON is missing joints[]')

        by_id: Dict[int, Dict[str, Any]] = {}
        for item in joints:
            if not isinstance(item, dict):
                continue
            sid = int(item.get('id', -1))
            if sid not in KNOWN_IDS:
                continue
            clamped_angle, clamped_raw = self._clamp_angle_to_raw(sid, float(item.get('angle_deg', 0.0)))
            by_id[sid] = {
                'id': sid,
                'angle_deg': clamped_angle,
                'raw_target': clamped_raw,
                'reason': str(item.get('reason', '') or ''),
            }

        if sorted(by_id.keys()) != KNOWN_IDS:
            raise RuntimeError('Arm plan must include all 6 joints exactly once')

        speed = int(payload.get('speed', GOOGLE_ARM_PLAN_SPEED))
        speed = max(80, min(1200, speed))
        return {
            'scene_summary': str(payload.get('scene_summary', '') or ''),
            'target_object': str(payload.get('target_object', 'unknown') or 'unknown'),
            'action': str(payload.get('action', 'hold') or 'hold'),
            'speed': speed,
            'notes': str(payload.get('notes', '') or ''),
            'joints': [by_id[sid] for sid in KNOWN_IDS],
        }

    def apply_last_arm_plan(self) -> Dict[str, Any]:
        with self.lock:
            plan = dict(self.last_arm_plan) if isinstance(self.last_arm_plan, dict) else None
        if not plan:
            raise RuntimeError('No generated arm plan available')

        speed = int(plan.get('speed', GOOGLE_ARM_PLAN_SPEED))
        for joint in plan.get('joints', []):
            move_servo_raw(int(joint['id']), int(joint['raw_target']), speed)

        with self.lock:
            self.message = 'Applied generated robot arm plan'
        return self.status()


_insights = VisionInsightsManager(_camera)


class HailoSegmentationStream:
    def __init__(self, camera: CameraStream):
        self.camera = camera
        self.lock = threading.Lock()
        self.thread = None
        self.running = False
        self.ready = False
        self.error = 'Detector idle'
        self.last_frame = None
        self.last_frame_at = 0.0
        self.last_input_seq = 0
        self.model_name = os.path.basename(YOLO26_HEF_PATH)
        self.network_group_name = None
        self.last_detection_count = 0
        self.last_latency_ms = None
        self.last_hailo_ms = None
        self.last_post_ms = None
        self.last_fps = None
        self.last_retry_at = 0.0
        self.engine = None
        self.preprocess_rgb_image = None
        self.scale_detections_to_original = None
        self.segmentation_postprocessor = None
        self.last_detections = []
        self.last_target = None
        self.selected_target = None

    def start(self) -> None:
        if cv2 is None or np is None:
            self.error = 'OpenCV is not installed'
            return
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.running = True
            self.thread = threading.Thread(target=self._inference_loop, daemon=True)
            self.thread.start()

    def _load_runtime(self) -> None:
        if not os.path.isdir(YOLO26_PYTHON_DIR):
            raise RuntimeError(f'YOLO26 python dir not found: {YOLO26_PYTHON_DIR}')
        if not os.path.exists(YOLO26_HEF_PATH):
            raise RuntimeError(f'HEF not found: {YOLO26_HEF_PATH}')
        if YOLO26_PYTHON_DIR not in sys.path:
            sys.path.insert(0, YOLO26_PYTHON_DIR)

        from common import (
            HailoSegmentationInferenceEngine,
            SegmentationPostProcessor,
            infer_segmentation_config_from_hef,
            preprocess_rgb_image,
            scale_detections_to_original,
        )

        inferred = infer_segmentation_config_from_hef(YOLO26_HEF_PATH)
        num_classes = inferred.get('num_classes')
        num_masks = inferred.get('num_masks')
        class_names = inferred.get('class_names')
        self.network_group_name = inferred.get('network_group_name')

        if num_classes is None or num_masks is None:
            raise RuntimeError(f'Could not infer segmentation layout from {YOLO26_HEF_PATH}')
        if class_names is None:
            class_names = [f'class_{idx}' for idx in range(num_classes)]

        self.engine = HailoSegmentationInferenceEngine(
            hef_path=YOLO26_HEF_PATH,
            num_classes=num_classes,
            num_masks=num_masks,
            class_names={idx: name for idx, name in enumerate(class_names)},
        )
        self.preprocess_rgb_image = preprocess_rgb_image
        self.scale_detections_to_original = scale_detections_to_original
        self.segmentation_postprocessor = SegmentationPostProcessor

    def _reset_engine(self) -> None:
        if self.engine is not None:
            try:
                self.engine.close()
            except Exception:
                pass
        self.engine = None

    def _status_frame(self) -> bytes:
        return render_status_jpeg(
            'YOLO26 Segmentation',
            'Waiting for Hailo inference...',
            self.error or 'Connecting to Hailo runtime',
            CAMERA_WIDTH,
            CAMERA_HEIGHT,
        )

    def _annotate_frame(self, image: np.ndarray, detections: List[dict], stats: Any) -> np.ndarray:
        overlay = image.copy()
        cv2.rectangle(overlay, (0, 0), (overlay.shape[1], 34), (6, 12, 24), -1)
        overlay = cv2.addWeighted(overlay, 0.72, image, 0.28, 0)

        label = (
            f'{self.model_name} | {len(detections)} obj | '
            f'{stats.total_time * 1000:.1f} ms | {self.last_fps:.1f} FPS'
            if self.last_fps is not None
            else f'{self.model_name} | {len(detections)} obj | {stats.total_time * 1000:.1f} ms'
        )
        cv2.putText(overlay, label, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (125, 211, 252), 2, cv2.LINE_AA)
        if self.last_target:
            x1 = int(self.last_target['x1'])
            y1 = int(self.last_target['y1'])
            x2 = int(self.last_target['x2'])
            y2 = int(self.last_target['y2'])
            cx = int(self.last_target['cx'])
            cy = int(self.last_target['cy'])
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 200, 255), 2)
            cv2.drawMarker(overlay, (cx, cy), (0, 200, 255), cv2.MARKER_CROSS, 18, 2)
            cv2.putText(overlay, 'TARGET', (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2, cv2.LINE_AA)
        return overlay

    @staticmethod
    def _serialize_detections(detections: List[dict], frame_width: int, frame_height: int) -> List[Dict[str, Any]]:
        serialized = []
        for det in detections[:12]:
            x1 = float(det['x1'])
            y1 = float(det['y1'])
            x2 = float(det['x2'])
            y2 = float(det['y2'])
            w = max(0.0, x2 - x1)
            h = max(0.0, y2 - y1)
            area = w * h
            serialized.append({
                'cls_name': det.get('cls_name', 'obj'),
                'conf': round(float(det.get('conf', 0.0)), 4),
                'x1': round(x1, 2),
                'y1': round(y1, 2),
                'x2': round(x2, 2),
                'y2': round(y2, 2),
                'w': round(w, 2),
                'h': round(h, 2),
                'cx': round(x1 + w / 2.0, 2),
                'cy': round(y1 + h / 2.0, 2),
                'area': round(area, 2),
                'area_ratio': round(area / float(max(frame_width * frame_height, 1)), 5),
                'frame_width': frame_width,
                'frame_height': frame_height,
            })
        return serialized

    @staticmethod
    def _pick_target_by_score(detections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not detections:
            return None
        return max(
            detections,
            key=lambda det: det['area_ratio'] * (0.5 + det['conf']) - abs(det['cx'] / max(det['frame_width'], 1) - 0.5) * 0.04,
        )

    def _pick_target(self, detections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not detections:
            return None
        if not self.selected_target:
            return self._pick_target_by_score(detections)

        selected_cls = self.selected_target.get('cls_name')
        ref_x = float(self.selected_target.get('cx', detections[0]['cx']))
        ref_y = float(self.selected_target.get('cy', detections[0]['cy']))
        candidates = [det for det in detections if det.get('cls_name') == selected_cls] or detections
        best = min(
            candidates,
            key=lambda det: ((det['cx'] - ref_x) ** 2 + (det['cy'] - ref_y) ** 2) - det['area_ratio'] * 2500.0,
        )
        self.selected_target = dict(best)
        return best

    def select_detection(self, index: int) -> Optional[Dict[str, Any]]:
        if index < 0 or index >= len(self.last_detections):
            return None
        self.selected_target = dict(self.last_detections[index])
        self.last_target = dict(self.selected_target)
        return dict(self.selected_target)

    def clear_selection(self) -> None:
        self.selected_target = None

    def _inference_loop(self) -> None:
        while self.running:
            if self.engine is None:
                try:
                    self._load_runtime()
                    self.error = None
                except Exception as exc:
                    self.ready = False
                    self.error = f'Hailo init failed: {exc}'
                    self.last_retry_at = time.time()
                    time.sleep(2.0)
                    continue

            frame_bgr, frame_at, frame_seq = self.camera.get_frame_data()
            if frame_bgr is None or frame_seq == self.last_input_seq:
                self.error = self.camera.error or 'Waiting for camera frame'
                time.sleep(0.05)
                continue

            self.last_input_seq = frame_seq

            try:
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                input_data, (orig_h, orig_w), scale, pad_w, pad_h = self.preprocess_rgb_image(
                    frame_rgb,
                    target_size=640,
                    normalize=False,
                )

                detections, masks, stats = self.engine.infer(
                    input_data,
                    verbose=False,
                    conf_threshold=DETECTION_CONFIDENCE,
                    mask_threshold=DETECTION_MASK_THRESHOLD,
                    iou_threshold=DETECTION_IOU,
                )
                detections = self.scale_detections_to_original(
                    detections,
                    orig_h,
                    orig_w,
                    scale,
                    pad_w,
                    pad_h,
                )
                serialized_detections = self._serialize_detections(detections, orig_w, orig_h)
                self.last_detections = serialized_detections
                self.last_target = self._pick_target(serialized_detections)

                if masks is not None and len(detections) > 0:
                    annotated = self.segmentation_postprocessor.draw_masks(
                        frame_bgr,
                        detections,
                        masks,
                        scale=scale,
                        pad_w=pad_w,
                        pad_h=pad_h,
                        alpha=0.35,
                    )
                else:
                    annotated = frame_bgr.copy()

                self.last_latency_ms = round(stats.total_time * 1000, 2)
                self.last_hailo_ms = round(stats.hailo_inference_time * 1000, 2)
                self.last_post_ms = round(stats.postprocess_time * 1000, 2)
                if self.last_frame_at:
                    dt = time.time() - self.last_frame_at
                    if dt > 0:
                        self.last_fps = 1.0 / dt
                self.last_detection_count = len(detections)
                self.error = None
                self.ready = True

                annotated = self._annotate_frame(annotated, detections, stats)
                ok, encoded = cv2.imencode(
                    '.jpg',
                    annotated,
                    [int(cv2.IMWRITE_JPEG_QUALITY), DETECTION_JPEG_QUALITY],
                )
                if ok:
                    with self.lock:
                        self.last_frame = encoded.tobytes()
                        self.last_frame_at = max(frame_at, time.time())

            except Exception as exc:
                self.ready = False
                self.error = f'Inference failed: {exc}'
                self.last_detections = []
                self.last_target = None
                self._reset_engine()
                time.sleep(0.5)
                continue

            time.sleep(1.0 / max(DETECTION_FPS, 1))

    def get_frame(self) -> bytes:
        self.start()
        with self.lock:
            frame = self.last_frame
            frame_at = self.last_frame_at
        age = time.time() - frame_at if frame_at else None
        if frame and (age is None or age < 2.5):
            return frame
        return self._status_frame()

    def status(self) -> Dict[str, Any]:
        age = round(time.time() - self.last_frame_at, 2) if self.last_frame_at else None
        return {
            'running': bool(self.thread and self.thread.is_alive()),
            'ready': self.ready,
            'error': self.error,
            'frame_age_s': age,
            'model': self.model_name,
            'hef_path': YOLO26_HEF_PATH,
            'network_group': self.network_group_name,
            'detections': self.last_detection_count,
            'latency_ms': self.last_latency_ms,
            'hailo_ms': self.last_hailo_ms,
            'post_ms': self.last_post_ms,
            'fps': round(self.last_fps, 2) if self.last_fps is not None else None,
            'confidence': DETECTION_CONFIDENCE,
            'target': self.last_target,
            'detections_data': self.last_detections,
            'selected_target': self.selected_target,
            'selection_active': self.selected_target is not None,
        }


_detector = HailoSegmentationStream(_camera)


class ArmAutoGrabController:
    def __init__(self, detector: HailoSegmentationStream):
        self.detector = detector
        self.lock = threading.Lock()
        self.thread = None
        self.running = False
        self.enabled = False
        self.state = 'idle'
        self.message = 'Auto-grab idle'
        self.last_action_at = 0.0
        self.last_target = None
        self.last_result = None

    def start(self) -> None:
        with self.lock:
            self.enabled = True
            self.state = 'arming'
            self.message = 'Opening gripper and starting visual servoing'
            if self.thread and self.thread.is_alive():
                return
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self, reason: str = 'Stopped by user') -> None:
        with self.lock:
            self.enabled = False
            self.state = 'idle'
            self.message = reason

    def status(self) -> Dict[str, Any]:
        with self.lock:
            target = dict(self.last_target) if self.last_target else None
            result = dict(self.last_result) if self.last_result else None
            return {
                'enabled': self.enabled,
                'running': bool(self.thread and self.thread.is_alive()),
                'state': self.state,
                'message': self.message,
                'target': target,
                'result': result,
            }

    def _update_status(self, state: str, message: str, target: Optional[Dict[str, Any]] = None) -> None:
        with self.lock:
            self.state = state
            self.message = message
            self.last_target = dict(target) if target else None

    def _loop(self) -> None:
        while self.running:
            with self.lock:
                enabled = self.enabled
            if not enabled:
                time.sleep(0.2)
                continue

            target = self.detector.last_target
            if not target:
                self._update_status('searching', 'Waiting for a detection target')
                time.sleep(1.0 / max(AUTO_LOOP_HZ, 1.0))
                continue

            try:
                if self.state == 'arming':
                    self._prepare_for_pick()
                    self._update_status('tracking', 'Tracking target', target)
                elif self.state in ('tracking', 'aligning'):
                    self._track_target(target)
                elif self.state == 'grabbing':
                    self._grab_target(target)
                elif self.state == 'lifting':
                    self._lift_target(target)
                    self.stop('Auto-grab complete')
                else:
                    self._update_status('tracking', 'Tracking target', target)
            except Exception as exc:
                self.stop(f'Auto-grab error: {exc}')
            time.sleep(1.0 / max(AUTO_LOOP_HZ, 1.0))

    def _prepare_for_pick(self) -> None:
        move_servo_raw(AUTO_GRIPPER_ID, AUTO_GRIPPER_OPEN, AUTO_GRAB_SPEED)
        time.sleep(0.25)

    def _track_target(self, target: Dict[str, Any]) -> None:
        frame_width = max(int(target.get('frame_width', CAMERA_WIDTH)), 1)
        frame_height = max(int(target.get('frame_height', CAMERA_HEIGHT)), 1)
        cx_norm = target['cx'] / frame_width
        cy_norm = target['cy'] / frame_height
        err_x = cx_norm - 0.5
        err_y = cy_norm - 0.5
        area_ratio = target['area_ratio']
        centered = abs(err_x) <= AUTO_CENTER_X_TOL and abs(err_y) <= AUTO_CENTER_Y_TOL
        close_enough = area_ratio >= AUTO_GRAB_AREA

        raw_base = get_servo_raw(AUTO_BASE_ID)
        raw_shoulder = get_servo_raw(AUTO_SHOULDER_ID)
        raw_elbow = get_servo_raw(AUTO_ELBOW_ID)
        raw_wrist = get_servo_raw(AUTO_WRIST_ID)
        if None in (raw_base, raw_shoulder, raw_elbow, raw_wrist):
            self._update_status('waiting', 'Servo telemetry not ready yet', target)
            return

        base_delta = int(err_x * AUTO_BASE_GAIN * AUTO_BASE_SIGN)
        vertical_delta = int(err_y * AUTO_SHOULDER_GAIN * AUTO_VERTICAL_SIGN)
        elbow_delta = int(err_y * AUTO_ELBOW_GAIN * AUTO_VERTICAL_SIGN)
        wrist_delta = int(err_y * AUTO_WRIST_GAIN * AUTO_VERTICAL_SIGN)

        if centered and close_enough:
            self._update_status('grabbing', 'Target is centered and close enough, closing gripper', target)
            return

        if abs(base_delta) > 4:
            move_servo_raw(AUTO_BASE_ID, raw_base + base_delta, AUTO_TRACK_SPEED)
        if abs(vertical_delta) > 4:
            move_servo_raw(AUTO_SHOULDER_ID, raw_shoulder + vertical_delta, AUTO_TRACK_SPEED)
        if abs(elbow_delta) > 4:
            move_servo_raw(AUTO_ELBOW_ID, raw_elbow + elbow_delta, AUTO_TRACK_SPEED)
        if abs(wrist_delta) > 4:
            move_servo_raw(AUTO_WRIST_ID, raw_wrist + wrist_delta, AUTO_TRACK_SPEED)

        if centered and not close_enough:
            move_servo_raw(AUTO_SHOULDER_ID, raw_shoulder + AUTO_APPROACH_SHOULDER, AUTO_TRACK_SPEED)
            move_servo_raw(AUTO_ELBOW_ID, raw_elbow + AUTO_APPROACH_ELBOW, AUTO_TRACK_SPEED)
            move_servo_raw(AUTO_WRIST_ID, raw_wrist + AUTO_APPROACH_WRIST, AUTO_TRACK_SPEED)
            self._update_status(
                'aligning',
                f'Centered on {target["cls_name"]}, advancing (area={area_ratio:.3f})',
                target,
            )
        else:
            self._update_status(
                'tracking',
                f'Tracking {target["cls_name"]} (dx={err_x:.2f}, dy={err_y:.2f}, area={area_ratio:.3f})',
                target,
            )

    def _grab_target(self, target: Dict[str, Any]) -> None:
        move_servo_raw(AUTO_GRIPPER_ID, AUTO_GRIPPER_CLOSE, AUTO_GRAB_SPEED)
        time.sleep(AUTO_GRIP_SETTLE)
        self.last_result = {
            'cls_name': target.get('cls_name'),
            'conf': target.get('conf'),
            'area_ratio': target.get('area_ratio'),
        }
        self._update_status('lifting', 'Gripper closed, lifting object', target)

    def _lift_target(self, target: Dict[str, Any]) -> None:
        raw_shoulder = get_servo_raw(AUTO_SHOULDER_ID)
        raw_elbow = get_servo_raw(AUTO_ELBOW_ID)
        raw_wrist = get_servo_raw(AUTO_WRIST_ID)
        if None in (raw_shoulder, raw_elbow, raw_wrist):
            self._update_status('done', 'Grab attempted but lift skipped: no servo telemetry', target)
            return
        move_servo_raw(AUTO_SHOULDER_ID, raw_shoulder + AUTO_LIFT_SHOULDER, AUTO_GRAB_SPEED)
        move_servo_raw(AUTO_ELBOW_ID, raw_elbow + AUTO_LIFT_ELBOW, AUTO_GRAB_SPEED)
        move_servo_raw(AUTO_WRIST_ID, raw_wrist + AUTO_LIFT_WRIST, AUTO_GRAB_SPEED)
        time.sleep(AUTO_ALIGN_SETTLE)
        self._update_status('done', 'Grab sequence complete', target)


_auto_grab = ArmAutoGrabController(_detector)


def camera_stream():
    delay = 1.0 / max(CAMERA_STREAM_FPS, 1)
    while True:
        frame = _camera.get_frame()
        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n'
            b'Cache-Control: no-cache\r\n\r\n' + frame + b'\r\n'
        )
        time.sleep(delay)


def detection_stream():
    delay = 1.0 / max(CAMERA_STREAM_FPS, 1)
    while True:
        frame = _detector.get_frame()
        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n'
            b'Cache-Control: no-cache\r\n\r\n' + frame + b'\r\n'
        )
        time.sleep(delay)


# ── Serial bus ───────────────────────────────────────────────────────────────
class Bus:
    def __init__(self, device: str, baud: int):
        self.lock = threading.Lock()
        ph = PortHandler(device)
        ph.baudrate = baud
        if not ph.openPort():
            raise RuntimeError(f'Cannot open {device}')
        self._pkt = protocol_packet_handler(ph)

    def r1(self, sid: int, addr: int):
        data, comm, _ = self._pkt.readTxRx(sid, addr, 1)
        if comm == 0 and isinstance(data, (list, bytes)) and len(data) == 1:
            return data[0]
        return None

    def r2(self, sid: int, addr: int):
        data, comm, _ = self._pkt.readTxRx(sid, addr, 2)
        if comm == 0 and isinstance(data, (list, bytes)) and len(data) == 2:
            return data[0] | (data[1] << 8)
        return None

    def write(self, sid: int, addr: int, values: list) -> tuple:
        return self._pkt.writeTxRx(sid, addr, len(values), values)


# ── Servo state ──────────────────────────────────────────────────────────────
servo_state: dict = {}
sw_offset:   dict = {}  # {sid: raw_position_at_zero}
sw_min:      Dict[int, int] = {}  # {sid: raw min limit}
sw_max:      Dict[int, int] = {}  # {sid: raw max limit}
sw_wrap:     Dict[int, bool] = {}  # {sid: True if range crosses 0/4095}
torque_state: Dict[int, bool] = {}  # last commanded torque state

# ── Recording state ───────────────────────────────────────────────────────────
recordings: Dict[int, Dict[str, Any]] = {}  # {sid: {active, writer, fh, path, count, last_raw}}


for _sid, _limits in DEFAULT_LIMITS.items():
    sw_min[_sid] = _limits['min']
    sw_max[_sid] = _limits['max']
    sw_offset[_sid] = _limits['min']
    sw_wrap[_sid] = False

for _sid in TRACKED_IDS:
    torque_state[_sid] = True


def raw_to_angle_deg(raw: Optional[int]) -> Optional[float]:
    if raw is None:
        return None
    return round(float(raw) / RAW_MAX * 270.0, 2)


def observed_range_deg(state: Dict[str, Any]) -> Optional[float]:
    min_seen = state.get('min_seen')
    max_seen = state.get('max_seen')
    if min_seen is None or max_seen is None:
        return None
    return round((float(max_seen) - float(min_seen)) / RAW_MAX * 270.0, 2)


class PairMappingManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.enabled = False
        self.thread = None
        self.stop_event = threading.Event()
        self.message = 'Pair mapping idle'
        self.last_test = None
        self.anchors: Dict[int, Dict[str, int]] = {}

    @staticmethod
    def _observed_raw_window(sid: int, state: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
        min_seen = state.get('min_seen')
        max_seen = state.get('max_seen')
        if min_seen is None or max_seen is None:
            return None, None
        offset = int(sw_offset.get(sid, 0))
        return int(min_seen + offset), int(max_seen + offset)

    @staticmethod
    def _effective_window(sid: int, state: Dict[str, Any], prefer_limits: bool) -> Tuple[int, int, str]:
        if prefer_limits:
            lo = sw_min.get(sid)
            hi = sw_max.get(sid)
            if lo is not None and hi is not None and hi > lo:
                return int(lo), int(hi), 'limits'

        obs_lo, obs_hi = PairMappingManager._observed_raw_window(sid, state)
        if obs_lo is not None and obs_hi is not None and obs_hi > obs_lo:
            return int(obs_lo), int(obs_hi), 'observed'

        lo = sw_min.get(sid, 0)
        hi = sw_max.get(sid, RAW_MAX)
        if hi <= lo:
            lo, hi = 0, RAW_MAX
        return int(lo), int(hi), 'fallback'

    def _compute_mapping(self, target_id: int, source_id: int) -> Dict[str, Any]:
        target_state = servo_state.get(target_id, {})
        source_state = servo_state.get(source_id, {})
        target_raw = target_state.get('raw')
        source_raw = source_state.get('raw')
        inverted = bool(PAIR_INVERTED.get(target_id, False))
        target_lo, target_hi, target_window = self._effective_window(target_id, target_state, prefer_limits=True)
        source_lo, source_hi, source_window = self._effective_window(source_id, source_state, prefer_limits=False)
        source_span = max(0, source_hi - source_lo)
        target_span = max(0, target_hi - target_lo)

        anchor = self.anchors.get(target_id, {})
        anchor_source = anchor.get('source_raw', source_raw if source_raw is not None else 0)
        anchor_target = anchor.get('target_raw', target_raw if target_raw is not None else target_lo)

        mapped_raw = None
        mode = 'unavailable'
        if source_raw is not None and target_raw is not None:
            if source_span >= PAIR_SYNC_RANGE_MIN_RAW and target_span > 0:
                ratio = (float(source_raw) - float(source_lo)) / float(max(source_span, 1))
                ratio = max(0.0, min(1.0, ratio))
                if inverted:
                    ratio = 1.0 - ratio
                mapped_raw = int(round(target_lo + ratio * target_span))
                mode = 'normalized-inverted' if inverted else 'normalized'
            else:
                offset = int(source_raw) - int(anchor_source)
                mapped_raw = int(anchor_target) - offset if inverted else int(anchor_target) + offset
                mode = 'delta-inverted' if inverted else 'delta'
            mapped_raw = clamp_raw_to_limits(target_id, mapped_raw)

        return {
            'target_raw': target_raw,
            'source_raw': source_raw,
            'mapped_raw': mapped_raw,
            'mapping_mode': mode,
            'inverted': inverted,
            'source_window_kind': source_window,
            'target_window_kind': target_window,
            'source_span_raw': source_span,
            'target_span_raw': target_span,
            'source_lo': source_lo,
            'source_hi': source_hi,
            'target_lo': target_lo,
            'target_hi': target_hi,
        }

    def _pair_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for target_id, source_id in PAIR_MAPPINGS.items():
            target_state = servo_state.get(target_id, {})
            source_state = servo_state.get(source_id, {})
            target_raw = target_state.get('raw')
            source_raw = source_state.get('raw')
            mapping = self._compute_mapping(target_id, source_id)
            target_angle = raw_to_angle_deg(target_raw)
            source_angle = raw_to_angle_deg(source_raw)
            delta_deg = None
            if target_angle is not None and source_angle is not None:
                delta_deg = round(target_angle - source_angle, 2)
            rows.append({
                'target_id': target_id,
                'source_id': source_id,
                'target_online': bool(target_state.get('online', False)),
                'source_online': bool(source_state.get('online', False)),
                'target_torque_enabled': torque_state.get(target_id, True),
                'source_torque_enabled': torque_state.get(source_id, False),
                'target_raw': target_raw,
                'source_raw': source_raw,
                'target_angle_deg': target_angle,
                'source_angle_deg': source_angle,
                'delta_deg': delta_deg,
                'mapped_target_raw': mapping['mapped_raw'],
                'mapped_target_angle_deg': raw_to_angle_deg(mapping['mapped_raw']),
                'mapping_mode': mapping['mapping_mode'],
                'inverted': mapping['inverted'],
                'source_span_raw': mapping['source_span_raw'],
                'target_span_raw': mapping['target_span_raw'],
                'source_window_kind': mapping['source_window_kind'],
                'target_window_kind': mapping['target_window_kind'],
                'target_range_deg': observed_range_deg(target_state),
                'source_range_deg': observed_range_deg(source_state),
                'target_min_seen': target_state.get('min_seen'),
                'target_max_seen': target_state.get('max_seen'),
                'source_min_seen': source_state.get('min_seen'),
                'source_max_seen': source_state.get('max_seen'),
                'source_mode': source_state.get('mode', 0),
                'target_mode': target_state.get('mode', 0),
            })
        return rows

    def test(self) -> Dict[str, Any]:
        rows = self._pair_rows()
        online_pairs = sum(1 for row in rows if row['target_online'] and row['source_online'])
        angle_deltas = [abs(row['delta_deg']) for row in rows if row['delta_deg'] is not None]
        range_deltas = [
            abs(row['target_range_deg'] - row['source_range_deg'])
            for row in rows
            if row['target_range_deg'] is not None and row['source_range_deg'] is not None
        ]
        summary = {
            'tested_at': datetime.now().isoformat(timespec='seconds'),
            'online_pairs': online_pairs,
            'max_angle_delta_deg': round(max(angle_deltas), 2) if angle_deltas else None,
            'max_observed_range_delta_deg': round(max(range_deltas), 2) if range_deltas else None,
            'rows': rows,
        }
        with self.lock:
            self.last_test = summary
            self.message = (
                f'Pair mapping test complete: {online_pairs}/{len(rows)} pairs online'
                + (
                    f', max angle delta {summary["max_angle_delta_deg"]}°'
                    if summary['max_angle_delta_deg'] is not None else ''
                )
            )
        return self.status()

    def start(self) -> Dict[str, Any]:
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.message = 'Pair mapping already running'
                self.enabled = True
                return self.status()
            enforce_leader_torque_disabled()
            self.anchors = {}
            for target_id, source_id in PAIR_MAPPINGS.items():
                target_raw = get_servo_raw(target_id)
                source_raw = get_servo_raw(source_id)
                if target_raw is None or source_raw is None:
                    continue
                self.anchors[target_id] = {
                    'target_raw': int(target_raw),
                    'source_raw': int(source_raw),
                }
            self.stop_event.clear()
            self.enabled = True
            self.message = 'Pair mapping enabled: leaders 7..12 stay torque-off and drive followers 1..6'
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        return self.status()

    def stop(self, reason: str = 'Pair mapping stopped') -> Dict[str, Any]:
        with self.lock:
            self.enabled = False
            self.stop_event.set()
            self.message = reason
        return self.status()

    def _run(self) -> None:
        period = 1.0 / max(PAIR_SYNC_HZ, 1.0)
        while not self.stop_event.is_set():
            for target_id, source_id in PAIR_MAPPINGS.items():
                source_raw = get_servo_raw(source_id)
                target_raw = get_servo_raw(target_id)
                mapping = self._compute_mapping(target_id, source_id)
                mapped_raw = mapping.get('mapped_raw')
                if source_raw is None or target_raw is None or mapped_raw is None:
                    continue
                ensure_servo_position_mode(target_id)
                delta = int(mapped_raw) - int(target_raw)
                if abs(delta) < PAIR_SYNC_DEADBAND_RAW:
                    continue
                commanded_raw = int(mapped_raw)
                if abs(delta) > PAIR_SYNC_MAX_STEP_RAW:
                    commanded_raw = int(target_raw) + (PAIR_SYNC_MAX_STEP_RAW if delta > 0 else -PAIR_SYNC_MAX_STEP_RAW)
                commanded_raw = clamp_raw_to_limits(target_id, commanded_raw)
                try:
                    move_servo_raw(target_id, commanded_raw, PAIR_SYNC_SPEED)
                except Exception:
                    continue
            time.sleep(period)

    def status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                'enabled': self.enabled,
                'running': bool(self.thread and self.thread.is_alive()),
                'message': self.message,
                'pairs': self._pair_rows(),
                'last_test': self.last_test,
            }


class MotionProgramManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = False
        self.frames: List[Dict[str, Any]] = []
        self.observed_ranges: Dict[int, Dict[str, int]] = {}
        self.started_at = 0.0
        self.last_path = None
        self.last_duration_ms = 0
        self.last_frame_count = 0
        self.last_message = 'No motion recording yet'
        self.playback_thread = None
        self.playback_stop = threading.Event()
        self.playback_active = False
        self.playback_message = 'Idle'
        self.last_learned_ranges: Dict[int, Dict[str, int]] = {}

    def start_recording(self) -> Dict[str, Any]:
        with self.lock:
            self.active = True
            self.frames = []
            self.observed_ranges = {}
            self.started_at = time.monotonic()
            self.last_message = 'Recording joint motion...'
        return self.status()

    def _capture_frame_locked(self, positions: Dict[int, int]) -> None:
        t_ms = int((time.monotonic() - self.started_at) * 1000)
        frame = {
            't_ms': t_ms,
            'positions': {str(sid): int(raw) for sid, raw in positions.items()},
        }
        if self.frames and self.frames[-1]['positions'] == frame['positions']:
            self.frames[-1]['t_ms'] = t_ms
        else:
            self.frames.append(frame)

    def maybe_record_snapshot(self, positions: Dict[int, int]) -> None:
        with self.lock:
            if not self.active or not positions:
                return
            for sid, raw in positions.items():
                observed = self.observed_ranges.setdefault(sid, {'min': int(raw), 'max': int(raw)})
                observed['min'] = min(observed['min'], int(raw))
                observed['max'] = max(observed['max'], int(raw))
            self._capture_frame_locked(positions)

    def stop_recording(self) -> Dict[str, Any]:
        with self.lock:
            if not self.active:
                pass
            else:
                self.active = False
                if self.frames:
                    self.last_duration_ms = int(self.frames[-1]['t_ms'])
                else:
                    self.last_duration_ms = 0
                self.last_frame_count = len(self.frames)
                os.makedirs(MOTION_RECORD_DIR, exist_ok=True)
                path = os.path.join(
                    MOTION_RECORD_DIR,
                    f'motion_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
                )
                payload = {
                    'created_at': datetime.now().isoformat(),
                    'frame_count': self.last_frame_count,
                    'duration_ms': self.last_duration_ms,
                    'servos': KNOWN_IDS,
                    'frames': self.frames,
                    'learned_ranges': {str(sid): rng for sid, rng in self.observed_ranges.items()},
                }
                with open(path, 'w', encoding='utf-8') as fh:
                    json.dump(payload, fh, indent=2)
                self.last_path = path
                self.last_learned_ranges = {sid: dict(rng) for sid, rng in self.observed_ranges.items()}
                servo6_range = self.observed_ranges.get(AUTO_GRIPPER_ID)
                if servo6_range and (servo6_range['max'] - servo6_range['min']) >= 8:
                    sw_min[AUTO_GRIPPER_ID] = servo6_range['min']
                    sw_max[AUTO_GRIPPER_ID] = servo6_range['max']
                    self.last_message = (
                        f'Saved {self.last_frame_count} frames to {path}; '
                        f'servo {AUTO_GRIPPER_ID} limits learned as {servo6_range["min"]}-{servo6_range["max"]}'
                    )
                else:
                    self.last_message = f'Saved {self.last_frame_count} frames to {path}'
        return self.status()

    def _load_latest(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            path = self.last_path
        if path and os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as fh:
                return json.load(fh)
        return None

    def start_playback(self) -> Dict[str, Any]:
        program = self._load_latest()
        if not program or not program.get('frames'):
            with self.lock:
                self.playback_message = 'No saved motion recording to play'
            return self.status()
        with self.lock:
            if self.playback_thread and self.playback_thread.is_alive():
                self.playback_message = 'Playback already running'
            else:
                self.playback_stop.clear()
                self.playback_active = True
                self.playback_message = f'Playing {os.path.basename(self.last_path)}'
                self.playback_thread = threading.Thread(
                    target=self._playback_worker,
                    args=(program,),
                    daemon=True,
                )
                self.playback_thread.start()
        return self.status()

    def stop_playback(self, reason: str = 'Playback stopped') -> Dict[str, Any]:
        with self.lock:
            self.playback_stop.set()
            self.playback_active = False
            self.playback_message = reason
        return self.status()

    def _playback_worker(self, program: Dict[str, Any]) -> None:
        frames = program.get('frames', [])
        if not frames:
            self.stop_playback('Playback aborted: empty program')
            return

        start = time.monotonic()
        last_time_ms = 0
        for frame in frames:
            if self.playback_stop.is_set():
                break
            target_ms = int(frame.get('t_ms', last_time_ms))
            delay = (target_ms - last_time_ms) / 1000.0
            if delay > 0:
                time.sleep(delay)
            positions = frame.get('positions', {})
            for sid_text, raw in positions.items():
                try:
                    move_servo_raw(int(sid_text), int(raw), MOTION_PLAYBACK_SPEED)
                except Exception:
                    continue
            last_time_ms = target_ms
        with self.lock:
            if self.playback_stop.is_set():
                self.playback_message = 'Playback stopped'
            else:
                self.playback_message = 'Playback complete'
            self.playback_active = False
            self.playback_stop.clear()

    def status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                'recording': self.active,
                'playback_active': self.playback_active,
                'last_path': self.last_path,
                'last_duration_ms': self.last_duration_ms,
                'last_frame_count': self.last_frame_count,
                'message': self.last_message,
                'playback_message': self.playback_message,
                'learned_ranges': self.last_learned_ranges,
                'servo6_min': sw_min.get(AUTO_GRIPPER_ID),
                'servo6_max': sw_max.get(AUTO_GRIPPER_ID),
            }


motion_program = MotionProgramManager()
pair_mapping = PairMappingManager()


class ServoTestManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_sid = None
        self.message = 'Idle'
        self.thread = None

    def status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                'active_sid': self.active_sid,
                'message': self.message,
                'running': bool(self.thread and self.thread.is_alive()),
            }

    def start(self, sid: int) -> Dict[str, Any]:
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.message = f'Servo {self.active_sid} test already running'
            else:
                self.active_sid = sid
                self.message = f'Testing servo {sid}...'
                self.thread = threading.Thread(target=self._run_test, args=(sid,), daemon=True)
                self.thread.start()
        return self.status()

    def _run_test(self, sid: int) -> None:
        current = get_servo_raw(sid)
        if current is None:
            with self.lock:
                self.message = f'Servo {sid} has no telemetry yet'
                self.active_sid = None
            return

        lo = sw_min.get(sid, 0)
        hi = sw_max.get(sid, RAW_MAX)
        span = max(hi - lo, 1)
        if sid == AUTO_GRIPPER_ID and span > 40:
            positions = [lo, hi, current]
        else:
            delta = max(30, min(120, span // 10))
            positions = [
                clamp_raw_to_limits(sid, current - delta),
                clamp_raw_to_limits(sid, current + delta),
                clamp_raw_to_limits(sid, current),
            ]

        try:
            for raw in positions:
                move_servo_raw(sid, raw, 500)
                time.sleep(0.6)
            with self.lock:
                self.message = f'Servo {sid} test complete'
                self.active_sid = None
        except Exception as exc:
            with self.lock:
                self.message = f'Servo {sid} test failed: {exc}'
                self.active_sid = None


servo_test_manager = ServoTestManager()


class AutoLimitCalibrator:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_sid = None
        self.message = 'Idle'
        self.thread = None

    def status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                'active_sid': self.active_sid,
                'message': self.message,
                'running': bool(self.thread and self.thread.is_alive()),
            }

    def start(self, sid: int) -> Dict[str, Any]:
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.message = f'Calibration already running for servo {self.active_sid}'
            else:
                self.active_sid = sid
                self.message = f'Learning joint limits for servo {sid}...'
                self.thread = threading.Thread(target=self._run, args=(sid,), daemon=True)
                self.thread.start()
        return self.status()

    def _run(self, sid: int) -> None:
        try:
            current = get_servo_raw(sid)
            if current is None:
                raise RuntimeError('No telemetry yet for this servo')
            torque_state[sid] = True
            move_servo_raw(sid, current, AUTO_LIMIT_SPEED, clamp=False)
            time.sleep(0.2)

            learned_min = self._find_limit(sid, -1)
            time.sleep(0.2)
            learned_max = self._find_limit(sid, +1)

            if learned_min is None or learned_max is None:
                raise RuntimeError('Could not determine both end stops')

            if learned_min > learned_max:
                learned_min, learned_max = learned_max, learned_min

            sw_min[sid] = learned_min
            sw_max[sid] = learned_max
            if sid not in sw_offset:
                sw_offset[sid] = learned_min

            midpoint = int((learned_min + learned_max) / 2)
            move_servo_raw(sid, midpoint, AUTO_LIMIT_SPEED, clamp=False)

            with self.lock:
                self.message = f'Servo {sid} limits learned: min={learned_min}, max={learned_max}'
                self.active_sid = None
        except Exception as exc:
            with self.lock:
                self.message = f'Servo {sid} auto-limit failed: {exc}'
                self.active_sid = None

    def _find_limit(self, sid: int, direction: int) -> Optional[int]:
        raw = get_servo_raw(sid)
        if raw is None:
            return None
        best = raw
        stall_hits = 0

        for _ in range(AUTO_LIMIT_MAX_STEPS):
            target = max(0, min(RAW_MAX, raw + direction * AUTO_LIMIT_STEP))
            if target == raw:
                break

            move_servo_raw(sid, target, AUTO_LIMIT_SPEED, clamp=False)
            time.sleep(AUTO_LIMIT_SETTLE)

            new_raw = get_servo_raw(sid)
            state = servo_state.get(sid, {})
            load_raw = int(state.get('load_raw') or 0)
            current_raw = int(state.get('current_raw') or 0)
            if new_raw is None:
                stall_hits += 1
                continue

            moved = abs(new_raw - raw)
            best = new_raw
            stalled = moved <= AUTO_LIMIT_STALL_DELTA
            overloaded = load_raw >= AUTO_LIMIT_LOAD_THRESHOLD or current_raw >= AUTO_LIMIT_CURRENT_THRESHOLD

            if stalled or overloaded:
                stall_hits += 1
            else:
                stall_hits = 0

            raw = new_raw
            if stall_hits >= AUTO_LIMIT_STALL_COUNT:
                return best

        return best


auto_limit_calibrator = AutoLimitCalibrator()


def travel_limit(sid: int) -> int | None:
    lo = sw_min.get(sid)
    hi = sw_max.get(sid)
    if lo is None or hi is None:
        return None
    return abs(hi - lo)


def calibrated(sid: int, raw: int) -> int:
    return raw - sw_offset.get(sid, 0)


def calibrated_to_raw(sid: int, cal_pos: int) -> int:
    lo = sw_min.get(sid)
    hi = sw_max.get(sid)
    raw_pos = cal_pos + sw_offset.get(sid, 0)
    if lo is None or hi is None:
        return raw_pos
    return max(lo, min(hi, raw_pos))


def clamp_raw_to_limits(sid: int, raw_pos: int) -> int:
    lo = sw_min.get(sid, 0)
    hi = sw_max.get(sid, RAW_MAX)
    return max(lo, min(hi, raw_pos))


def get_servo_raw(sid: int) -> Optional[int]:
    return servo_state.get(sid, {}).get('raw')


def send_servo_goal_raw(sid: int, raw_pos: int, speed: int = AUTO_TRACK_SPEED) -> int:
    if _bus is None:
        raise RuntimeError('Servo bus is not initialized')
    with _bus.lock:
        _bus.write(sid, V.STS_GOAL_POSITION_L, [
            raw_pos & 0xFF, (raw_pos >> 8) & 0xFF,
            0, 0,
            speed & 0xFF, (speed >> 8) & 0xFF,
        ])
    return raw_pos


def move_servo_raw(sid: int, raw_pos: int, speed: int = AUTO_TRACK_SPEED, clamp: bool = True) -> Optional[int]:
    if _bus is None:
        return None
    if clamp:
        raw_pos = clamp_raw_to_limits(sid, raw_pos)
    else:
        raw_pos = max(0, min(RAW_MAX, raw_pos))
    return send_servo_goal_raw(sid, raw_pos, speed)


def set_torque_enabled(sid: int, enabled: bool) -> None:
    if _bus is None:
        raise RuntimeError('Servo bus is not initialized')
    with _bus.lock:
        _bus.write(sid, V.STS_TORQUE_ENABLE, [1 if enabled else 0])
    torque_state[sid] = bool(enabled)


def enforce_leader_torque_disabled() -> None:
    if _bus is None:
        return
    with _bus.lock:
        for sid in LEADER_IDS:
            _bus.write(sid, V.STS_TORQUE_ENABLE, [0])
            torque_state[sid] = False


def ensure_servo_position_mode(sid: int) -> None:
    state = servo_state.get(sid, {})
    if state.get('mode', 0) == 0 and torque_state.get(sid, True):
        return
    if _bus is None:
        return
    with _bus.lock:
        _bus.write(sid, V.STS_LOCK, [0])
        time.sleep(0.02)
        _bus.write(sid, V.STS_MODE, [0])
        time.sleep(0.02)
        _bus.write(sid, V.STS_TORQUE_ENABLE, [1])
        time.sleep(0.02)
        _bus.write(sid, V.STS_LOCK, [1])
        time.sleep(0.02)
    torque_state[sid] = True


def update_state(sid: int, raw: int, volt, temp, moving: bool, mode: int, load=None, current=None) -> None:
    cal = calibrated(sid, raw)
    s = servo_state.setdefault(sid, {'min_seen': cal, 'max_seen': cal})
    s['pos']      = cal
    s['raw']      = raw
    s['volt']     = round(volt / 10, 1) if volt is not None else None
    s['temp']     = temp
    s['moving']   = moving
    s['mode']     = mode   # 0=servo, 1=motor, 2=pwm, 3=step
    s['load_raw'] = load
    s['current_raw'] = current
    s['online']   = True
    s['min_seen'] = min(s['min_seen'], cal)
    s['max_seen'] = max(s['max_seen'], cal)


def poll_loop(bus: Bus) -> None:
    while True:
        snapshot_positions: Dict[int, int] = {}
        with bus.lock:
            for sid in TRACKED_IDS:
                raw  = bus.r2(sid, V.STS_PRESENT_POSITION_L)
                load = bus.r2(sid, V.STS_PRESENT_LOAD_L)
                volt = bus.r1(sid, V.STS_PRESENT_VOLTAGE)
                temp = bus.r1(sid, V.STS_PRESENT_TEMPERATURE)
                mov  = bus.r1(sid, V.STS_MOVING)
                mode = bus.r1(sid, V.STS_MODE)
                current = bus.r2(sid, V.STS_PRESENT_CURRENT_L)
                if raw is not None:
                    if sid in KNOWN_IDS:
                        snapshot_positions[sid] = raw
                    update_state(sid, raw, volt, temp, bool(mov), mode or 0, load=load, current=current)
                    # Write to CSV if recording and value changed
                    rec = recordings.get(sid)
                    if rec and rec['active'] and raw != rec.get('last_raw'):
                        rec['last_raw'] = raw
                        rec['count']   += 1
                        now = datetime.now()
                        ms  = now.microsecond // 1000
                        ts  = f"{now.strftime('%H:%M:%S')}.{ms:03d}"
                        rec['writer'].writerow([
                            ts,
                            raw,
                            round(raw / RAW_MAX * 270, 2),
                            calibrated(sid, raw),
                        ])
                else:
                    servo_state.setdefault(sid, {})['online'] = False
        motion_program.maybe_record_snapshot(snapshot_positions)
        time.sleep(0.2)


# ── Flask routes ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status')
def api_status():
    result = {}
    for sid in TRACKED_IDS:
        s = servo_state.get(sid, {})
        result[str(sid)] = {
            'online':    s.get('online', False),
            'pos':       s.get('pos'),
            'raw':       s.get('raw'),
            'offset':    sw_offset.get(sid, 0),
            'min_seen':  s.get('min_seen'),
            'max_seen':  s.get('max_seen'),
            'volt':      s.get('volt'),
            'temp':      s.get('temp'),
            'moving':    s.get('moving', False),
            'mode':      s.get('mode', 0),
            'sw_min':    sw_min.get(sid),
            'sw_max':    sw_max.get(sid),
            'sw_wrap':   False,
            'travel':    travel_limit(sid),
            'angle_deg': raw_to_angle_deg(s.get('raw')),
            'torque_enabled': torque_state.get(sid, True),
            'load_raw':   s.get('load_raw'),
            'current_raw': s.get('current_raw'),
        }
    return jsonify(result)


@app.route('/api/camera/status')
def api_camera_status():
    return jsonify(_camera.status())


@app.route('/api/camera/stream')
def api_camera_stream():
    return Response(
        camera_stream(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'},
    )


@app.route('/api/insights/status')
def api_insights_status():
    return jsonify(_insights.status())


@app.route('/api/insights/generate', methods=['POST'])
def api_insights_generate():
    detector_payload = _detector.status()
    return jsonify({'ok': True, **_insights.start(detector_payload)})


@app.route('/api/insights/generate_arm_plan', methods=['POST'])
def api_insights_generate_arm_plan():
    detector_payload = _detector.status()
    return jsonify({'ok': True, **_insights.start_arm_plan(detector_payload)})


@app.route('/api/insights/apply_arm_plan', methods=['POST'])
def api_insights_apply_arm_plan():
    _auto_grab.stop('Stopped auto-grab for Gemini arm plan')
    motion_program.stop_playback('Stopped playback for Gemini arm plan')
    pair_mapping.stop('Stopped pair mapping for Gemini arm plan')
    try:
        return jsonify({'ok': True, **_insights.apply_last_arm_plan()})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


@app.route('/api/pair_mapping/status')
def api_pair_mapping_status():
    return jsonify(pair_mapping.status())


@app.route('/api/pair_mapping/test', methods=['POST'])
def api_pair_mapping_test():
    return jsonify({'ok': True, **pair_mapping.test()})


@app.route('/api/pair_mapping/start', methods=['POST'])
def api_pair_mapping_start():
    _auto_grab.stop('Stopped auto-grab for pair mapping')
    motion_program.stop_playback('Stopped playback for pair mapping')
    return jsonify({'ok': True, **pair_mapping.start()})


@app.route('/api/pair_mapping/stop', methods=['POST'])
def api_pair_mapping_stop():
    return jsonify({'ok': True, **pair_mapping.stop('Pair mapping stopped by user')})


@app.route('/api/detection/status')
def api_detection_status():
    return jsonify(_detector.status())


@app.route('/api/detection/select', methods=['POST'])
def api_detection_select():
    index = int((request.json or {}).get('index', -1))
    selected = _detector.select_detection(index)
    if selected is None:
        return jsonify({'ok': False, 'error': 'Invalid detection index'}), 400
    return jsonify({'ok': True, 'selected_target': selected, 'selection_active': True})


@app.route('/api/detection/clear_selection', methods=['POST'])
def api_detection_clear_selection():
    _detector.clear_selection()
    return jsonify({'ok': True, 'selection_active': False})


@app.route('/api/detection/stream')
def api_detection_stream():
    return Response(
        detection_stream(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'},
    )


@app.route('/api/autograb/status')
def api_autograb_status():
    return jsonify(_auto_grab.status())


@app.route('/api/autograb/start', methods=['POST'])
def api_autograb_start():
    pair_mapping.stop('Stopped pair mapping for auto-grab')
    _auto_grab.start()
    return jsonify({'ok': True, **_auto_grab.status()})


@app.route('/api/autograb/stop', methods=['POST'])
def api_autograb_stop():
    _auto_grab.stop('Stopped by user')
    return jsonify({'ok': True, **_auto_grab.status()})


@app.route('/api/motion_program/status')
def api_motion_program_status():
    return jsonify(motion_program.status())


@app.route('/api/motion_program/start_record', methods=['POST'])
def api_motion_program_start_record():
    _auto_grab.stop('Stopped auto-grab for motion recording')
    pair_mapping.stop('Stopped pair mapping for motion recording')
    return jsonify({'ok': True, **motion_program.start_recording()})


@app.route('/api/motion_program/stop_record', methods=['POST'])
def api_motion_program_stop_record():
    return jsonify({'ok': True, **motion_program.stop_recording()})


@app.route('/api/motion_program/start_playback', methods=['POST'])
def api_motion_program_start_playback():
    _auto_grab.stop('Stopped auto-grab for motion playback')
    pair_mapping.stop('Stopped pair mapping for motion playback')
    return jsonify({'ok': True, **motion_program.start_playback()})


@app.route('/api/motion_program/stop_playback', methods=['POST'])
def api_motion_program_stop_playback():
    return jsonify({'ok': True, **motion_program.stop_playback('Playback stopped by user')})


@app.route('/api/servo_test/status')
def api_servo_test_status():
    return jsonify(servo_test_manager.status())


@app.route('/api/servo_test/<int:sid>', methods=['POST'])
def api_servo_test(sid: int):
    if sid not in KNOWN_IDS:
        return jsonify({'ok': False, 'error': 'Unknown servo id'}), 400
    _auto_grab.stop('Stopped auto-grab for servo test')
    motion_program.stop_playback('Stopped playback for servo test')
    pair_mapping.stop('Stopped pair mapping for servo test')
    return jsonify({'ok': True, **servo_test_manager.start(sid)})


@app.route('/api/auto_limit/status')
def api_auto_limit_status():
    return jsonify(auto_limit_calibrator.status())


@app.route('/api/auto_limit/<int:sid>', methods=['POST'])
def api_auto_limit(sid: int):
    if sid not in KNOWN_IDS:
        return jsonify({'ok': False, 'error': 'Unknown servo id'}), 400
    _auto_grab.stop('Stopped auto-grab for auto-limit calibration')
    motion_program.stop_playback('Stopped playback for auto-limit calibration')
    pair_mapping.stop('Stopped pair mapping for auto-limit calibration')
    return jsonify({'ok': True, **auto_limit_calibrator.start(sid)})


@app.route('/api/move', methods=['POST'])
def api_move():
    data    = request.json or {}
    sid     = int(data['id'])
    cal_pos = int(data['pos'])
    speed   = int(data.get('speed', 500))
    raw_pos = calibrated_to_raw(sid, cal_pos)

    with _bus.lock:
        _bus.write(sid, V.STS_GOAL_POSITION_L, [
            raw_pos & 0xFF, (raw_pos >> 8) & 0xFF,
            0, 0,
            speed & 0xFF, (speed >> 8) & 0xFF,
        ])
    return jsonify({'ok': True, 'pos': cal_pos})


@app.route('/api/motor_speed', methods=['POST'])
def api_motor_speed():
    """Set motor wheel speed. speed > 0 = CW, speed < 0 = CCW, 0 = stop."""
    data  = request.json or {}
    sid   = int(data['id'])
    speed = int(data.get('speed', 0))   # signed, -3400 to +3400

    # STS encoding: bit15=direction(1=CCW), bits0-14=magnitude
    magnitude = min(abs(speed), 3400)
    direction = 0x8000 if speed < 0 else 0
    raw_speed = magnitude | direction

    with _bus.lock:
        _bus.write(sid, V.STS_GOAL_SPEED_L, [raw_speed & 0xFF, (raw_speed >> 8) & 0xFF])
    return jsonify({'ok': True, 'speed': speed})


@app.route('/api/set_mode', methods=['POST'])
def api_set_mode():
    """Switch servo between mode 0 (servo/position) and mode 1 (motor/wheel)."""
    data = request.json or {}
    sid  = int(data['id'])
    mode = int(data['mode'])   # 0=servo, 1=motor

    with _bus.lock:
        _bus.write(sid, V.STS_LOCK, [0])
        time.sleep(0.05)
        _bus.write(sid, V.STS_MODE, [mode])
        time.sleep(0.05)
        # In servo mode re-enable torque; in motor mode set speed to 0 first
        if mode == 1:
            _bus.write(sid, V.STS_GOAL_SPEED_L, [0, 0])
        _bus.write(sid, V.STS_TORQUE_ENABLE, [1])
        time.sleep(0.05)
        _bus.write(sid, V.STS_LOCK, [1])
        time.sleep(0.05)

    # Reset range tracking on mode switch
    if sid in servo_state:
        raw = servo_state[sid].get('raw', 0)
        cal = calibrated(sid, raw)
        servo_state[sid]['min_seen'] = cal
        servo_state[sid]['max_seen'] = cal

    return jsonify({'ok': True, 'mode': mode})


@app.route('/api/start_record', methods=['POST'])
def api_start_record():
    sid = int((request.json or {})['id'])
    if recordings.get(sid, {}).get('active'):
        return jsonify({'ok': False, 'error': 'Already recording'})

    os.makedirs('recordings', exist_ok=True)
    fname = f"recordings/servo_{sid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fh    = open(fname, 'w', newline='')
    writer = csv.writer(fh)
    writer.writerow(['time', 'raw', 'degrees', 'calibrated'])
    recordings[sid] = {
        'active':   True,
        'writer':   writer,
        'fh':       fh,
        'path':     fname,
        'count':    0,
        'last_raw': -1,
    }
    return jsonify({'ok': True, 'file': fname})


@app.route('/api/stop_record', methods=['POST'])
def api_stop_record():
    sid = int((request.json or {})['id'])
    if sid not in recordings or not recordings[sid]['active']:
        return jsonify({'ok': False, 'error': 'Not recording'})

    recordings[sid]['active'] = False
    recordings[sid]['fh'].flush()
    recordings[sid]['fh'].close()
    return jsonify({'ok': True, 'file': recordings[sid]['path'], 'samples': recordings[sid]['count']})


@app.route('/api/record_status')
def api_record_status():
    result = {}
    for sid in KNOWN_IDS:
        rec = recordings.get(sid)
        result[str(sid)] = {
            'active':  rec['active'] if rec else False,
            'count':   rec['count']  if rec else 0,
            'file':    rec['path']   if rec else None,
        }
    return jsonify(result)


@app.route('/api/download_record/<int:sid>')
def api_download_record(sid: int):
    rec = recordings.get(sid)
    if not rec or not os.path.exists(rec['path']):
        return jsonify({'error': 'No recording found'}), 404
    return send_file(rec['path'], as_attachment=True,
                     download_name=os.path.basename(rec['path']))


@app.route('/api/apply_recording', methods=['POST'])
def api_apply_recording():
    """Analyse the last recording CSV for a servo and auto-set min/max/wrap limits."""
    sid = int((request.json or {})['id'])
    rec = recordings.get(sid)
    if not rec or not os.path.exists(rec['path']):
        return jsonify({'ok': False, 'error': 'No recording found for this servo'}), 404

    raws: List[int] = []
    with open(rec['path'], newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raws.append(int(row['raw']))

    if len(raws) < 2:
        return jsonify({'ok': False, 'error': 'Recording too short'}), 400

    # Detect wrap: a large jump between consecutive values (> 2048) signals 0/4095 crossing
    wraps = any(abs(raws[i] - raws[i-1]) > 2048 for i in range(1, len(raws)))

    if wraps:
        # Min = first value (where recording started = physical min end-stop)
        # Max = last stable value (where recording ended = physical max end-stop)
        detected_min = raws[0]
        detected_max = raws[-1]
    else:
        detected_min = min(raws)
        detected_max = max(raws)

    sw_min[sid]  = detected_min
    sw_max[sid]  = detected_max
    sw_wrap[sid] = False

    travel = abs(detected_max - detected_min)
    degrees = int(travel * 2700 / RAW_MAX) / 10.0

    return jsonify({
        'ok':      True,
        'min':     detected_min,
        'max':     detected_max,
        'wraps':   wraps,
        'travel':  travel,
        'degrees': degrees,
        'samples': len(raws),
    })


@app.route('/api/set_limits_direct', methods=['POST'])
def api_set_limits_direct():
    """Directly set min/max/wrap for a servo from known values (e.g. from a CSV analysis)."""
    data = request.json or {}
    sid  = int(data['id'])
    sw_min[sid]  = int(data['min'])
    sw_max[sid]  = int(data['max'])
    sw_wrap[sid] = False
    travel = abs(sw_max[sid] - sw_min[sid])
    degrees = int(travel * 2700 / RAW_MAX) / 10.0
    return jsonify({'ok': True, 'min': sw_min[sid], 'max': sw_max[sid],
                    'wrap': sw_wrap[sid], 'travel': travel, 'degrees': degrees})


@app.route('/api/set_joint_limit', methods=['POST'])
def api_set_joint_limit():
    """Save current raw position as the min or max software limit for a servo."""
    data  = request.json or {}
    sid   = int(data['id'])
    which = data['which']   # 'min' or 'max'
    raw   = servo_state.get(sid, {}).get('raw')
    if raw is None:
        return jsonify({'ok': False, 'error': 'No position data'}), 500

    if which == 'min':
        sw_min[sid] = raw
    else:
        sw_max[sid] = raw

    return jsonify({'ok': True, 'which': which, 'raw': raw})


@app.route('/api/clear_joint_limit', methods=['POST'])
def api_clear_joint_limit():
    """Remove the software min/max limit for a servo."""
    data  = request.json or {}
    sid   = int(data['id'])
    which = data.get('which', 'both')
    if which in ('min', 'both'):  sw_min.pop(sid, None)
    if which in ('max', 'both'):  sw_max.pop(sid, None)
    return jsonify({'ok': True})


@app.route('/api/set_zero', methods=['POST'])
def api_set_zero():
    """Set current position as software zero — no EEPROM writes."""
    sid = int((request.json or {})['id'])
    raw = servo_state.get(sid, {}).get('raw')
    if raw is None:
        return jsonify({'ok': False, 'error': 'No position data yet'}), 500

    sw_offset[sid] = raw
    if sid in servo_state:
        servo_state[sid]['min_seen'] = 0
        servo_state[sid]['max_seen'] = 0

    return jsonify({'ok': True, 'offset_raw': raw})


@app.route('/api/define_middle', methods=['POST'])
def api_define_middle():
    """Use Feetech's define-middle action, then clear dashboard-side offsets/limits."""
    sid = int((request.json or {})['id'])

    with _bus.lock:
        _bus.write(sid, V.STS_TORQUE_ENABLE, [0])
        time.sleep(0.05)
        _bus.write(sid, V.STS_TORQUE_ENABLE, [128])
        time.sleep(0.3)
        _bus.write(sid, V.STS_LOCK, [0])
        time.sleep(0.05)
        _bus.write(sid, V.STS_MODE, [0])
        time.sleep(0.05)
        _bus.write(sid, V.STS_GOAL_SPEED_L, [0, 0])
        time.sleep(0.05)
        _bus.write(sid, V.STS_TORQUE_ENABLE, [1])
        time.sleep(0.05)
        _bus.write(sid, V.STS_LOCK, [1])
        time.sleep(0.1)
        raw = _bus.r2(sid, V.STS_PRESENT_POSITION_L)

    sw_offset.pop(sid, None)
    sw_min.pop(sid, None)
    sw_max.pop(sid, None)
    sw_wrap[sid] = False

    if raw is not None:
        update_state(sid, raw, servo_state.get(sid, {}).get('volt', 0), servo_state.get(sid, {}).get('temp'), False, 0)
        if sid in servo_state:
            servo_state[sid]['min_seen'] = 0
            servo_state[sid]['max_seen'] = 0

    return jsonify({'ok': True, 'raw': raw, 'message': 'Middle defined; software limits cleared'})


@app.route('/api/torque', methods=['POST'])
def api_torque():
    data   = request.json or {}
    sid    = int(data['id'])
    enable = int(bool(data.get('enable', True)))
    if sid in LEADER_IDS and enable:
        enforce_leader_torque_disabled()
        return jsonify({'ok': False, 'error': f'Servo {sid} is a leader joint and must stay torque disabled'}), 400
    set_torque_enabled(sid, bool(enable))
    if sid in LEADER_IDS:
        torque_state[sid] = False
    return jsonify({'ok': True, 'torque': int(bool(enable and sid not in LEADER_IDS))})


@app.route('/api/torque_all', methods=['POST'])
def api_torque_all():
    enable = int(bool((request.json or {}).get('enable', True)))
    with _bus.lock:
        for sid in FOLLOWER_IDS:
            _bus.write(sid, V.STS_TORQUE_ENABLE, [enable])
            torque_state[sid] = bool(enable)
        for sid in LEADER_IDS:
            _bus.write(sid, V.STS_TORQUE_ENABLE, [0])
            torque_state[sid] = False
    return jsonify({'ok': True, 'torque': enable, 'leaders_forced_off': LEADER_IDS})


@app.route('/api/estop', methods=['POST'])
def api_estop():
    _auto_grab.stop('Emergency stop triggered')
    motion_program.stop_playback('Emergency stop triggered')
    pair_mapping.stop('Emergency stop triggered')
    with _bus.lock:
        for sid in TRACKED_IDS:
            _bus.write(sid, V.STS_TORQUE_ENABLE, [0])
            torque_state[sid] = False
    return jsonify({'ok': True})


@app.route('/api/clear_limits', methods=['POST'])
def api_clear_limits():
    sid = int((request.json or {})['id'])
    with _bus.lock:
        _bus.write(sid, V.STS_LOCK, [0])
        time.sleep(0.05)
        _bus.write(sid, V.STS_MIN_ANGLE_LIMIT_L, [0x00, 0x00])
        time.sleep(0.05)
        _bus.write(sid, V.STS_MAX_ANGLE_LIMIT_L, [0xFF, 0x0F])
        time.sleep(0.05)
        _bus.write(sid, V.STS_LOCK, [1])
        time.sleep(0.05)
    return jsonify({'ok': True})


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f'Opening {DEVICE} at {BAUD:,} bps...')
    _bus = Bus(DEVICE, BAUD)
    print('Connected.')
    enforce_leader_torque_disabled()
    print(f'Leader torque forced off for IDs {LEADER_IDS}.')

    t = threading.Thread(target=poll_loop, args=(_bus,), daemon=True)
    t.start()
    print('Telemetry polling started.')
    _camera.start()
    _detector.start()
    print(f'Camera stream → http://localhost:5000/api/camera/stream (source={CAMERA_SOURCE})')
    print(f'Detection stream → http://localhost:5000/api/detection/stream (hef={YOLO26_HEF_PATH})')
    print('Dashboard → http://localhost:5000')

    app.run(host='0.0.0.0', port=5000, debug=False)
