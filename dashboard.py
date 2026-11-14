"""Control room for the phone snatch detector.

  python dashboard.py            -> http://localhost:8000

Every run of the detector is an *analysis* (job): one uploaded video, or one session of a CCTV
camera. Each analysis keeps its own annotated video, live picture and detections, so results
of different videos never mix, and deleting a video deletes everything that came from it.

  output/
    settings.json            detection settings used for new analyses
    cameras.json             saved CCTV cameras
    videos/<id>/             uploaded file + video.json
    jobs/<id>/               job.json, annotated.mp4, live.jpg, status.json, detector.log,
                             events/<event folder>/   (faces, clip, event.json, review.json)

Analyses run one at a time in a queue. The dashboard starts detect.py as a separate process and
reads the files it writes, so a crash in one does not take down the other.
The page itself lives in web/ (index.html, app.css, app.js).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
WEB_FILES = {"index.html": "text/html; charset=utf-8", "app.css": "text/css; charset=utf-8",
             "app.js": "text/javascript; charset=utf-8"}
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
MAX_UPLOAD = 4 * 1024 ** 3   # 4 GB
REVIEW_STATES = ("new", "confirmed", "reviewed", "dismissed")
EVENT_DIR = re.compile(r"event_[\w-]{1,80}")
FILE_NAME = re.compile(r"[\w.\-]{1,120}")
LEGACY_STAMP = re.compile(r"^\d{8}_\d{6}_")

# Settings shown on the Settings page: [key, label, help, {min, max, step} | {options}].
# Defaults match Config in detect.py.
SETTINGS_SCHEMA = [
    {"title": "Models", "fields": [
        ["phone_model", "Phone detector", "Model that finds phones. Larger models find more phones held in the hand but are slower",
         {"options": ["yolo26s.pt", "yolo26m.pt", "yolo11s.pt", "yoloe-26s-seg.pt"]}],
        ["phone_imgsz", "Phone resolution (px)", "Phones are tiny on CCTV: higher finds more of them but is slower",
         {"options": [960, 1280, 1600, 1920]}],
        ["pose_model", "People / pose model", "Finds people and their body keypoints",
         {"options": ["yolo11s-pose.pt", "yolo11m-pose.pt"]}],
        ["imgsz", "People resolution (px)", "Higher finds people further from the camera",
         {"options": [640, 960, 1280]}],
        ["device", "Processor", "auto uses an NVIDIA GPU when one is available",
         {"options": ["auto", "cpu", "0"]}],
        ["stride", "Analyse every Nth frame", "Saved videos only. 1 = every frame; 3 still works on 24 fps footage",
         {"min": 1, "max": 4, "step": 1}],
    ]},
    {"title": "Snatch detection", "fields": [
        ["alert_score", "Alert score", "Combined evidence needed before an alert is raised",
         {"min": 0.3, "max": 0.9, "step": 0.01}],
        ["walk_speed", "Walking speed", "Body heights per second that count as normal walking",
         {"min": 0.5, "max": 1.5, "step": 0.05}],
        ["run_speed", "Running speed", "Body heights per second that count as clearly running",
         {"min": 1.2, "max": 3.5, "step": 0.1}],
        ["flee_min_speed", "Minimum flee speed", "Peak speed the suspect must reach for the sprint pattern",
         {"min": 0.8, "max": 3.0, "step": 0.1}],
        ["flee_min_dist", "Minimum flee distance", "Body heights the suspect must move away from the contact point",
         {"min": 0.3, "max": 3.0, "step": 0.1}],
        ["contact_dist", "Contact distance", "Hand-to-hand distance (x body height) that counts as contact",
         {"min": 0.05, "max": 0.5, "step": 0.01}],
        ["watch_seconds", "Watch time after contact (s)", "How long a contact is followed before it is dropped",
         {"min": 1.0, "max": 8.0, "step": 0.5}],
    ]},
    {"title": "Phones", "fields": [
        ["phone_conf", "Phone confidence (anywhere)", "Score a phone box needs when it is not in someone's hand",
         {"min": 0.05, "max": 0.9, "step": 0.01}],
        ["phone_conf_hand", "Phone confidence (in hand)", "Lower score accepted for a box right at a wrist",
         {"min": 0.01, "max": 0.5, "step": 0.01}],
        ["phone_wrist_dist", "Hand distance", "Phone-to-wrist distance (x body height) that counts as holding",
         {"min": 0.05, "max": 0.5, "step": 0.01}],
    ]},
]
DEFAULTS = {
    "phone_model": "yolo26s.pt", "phone_imgsz": 1280, "pose_model": "yolo11s-pose.pt", "imgsz": 960,
    "device": "auto", "stride": 1,
    "alert_score": 0.55, "walk_speed": 0.9, "run_speed": 2.0, "flee_min_speed": 1.4, "flee_min_dist": 0.9,
    "contact_dist": 0.20, "watch_seconds": 3.5,
    "phone_conf": 0.25, "phone_conf_hand": 0.05, "phone_wrist_dist": 0.22,
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data):
    """Atomic write; retried because Windows refuses to replace a file someone is reading."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    for _ in range(20):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.05)
    tmp.replace(path)


def safe_name(name: str) -> str:
    name = re.sub(r"[^\w.\- ]", "_", Path(name).name).strip(" .")
    return name[:120] or "video.mp4"


def mask_url(url: str) -> str:
    """rtsp://user:secret@host/... -> rtsp://user:***@host/..."""
    return re.sub(r"(://[^:/@]+):[^@/]*@", r"\1:***@", url)


def probe_video(path: Path) -> dict:
    try:
        import cv2   # only needed here; keeps dashboard start-up fast
        cap = cv2.VideoCapture(str(path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return dict(fps=round(fps, 2), frames=frames, width=w, height=h,
                    duration=round(frames / fps, 2) if fps else 0)
    except Exception:
        return dict(fps=0, frames=0, width=0, height=0, duration=0)


class Store:
    """All state lives in files under the output folder; this class is the only writer."""

    def __init__(self, out: Path):
        self.out = out
        self.videos_dir = out / "videos"
        self.jobs_dir = out / "jobs"
        for d in (self.videos_dir, self.jobs_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.procs: dict[int, subprocess.Popen] = {}
        self._migrate_legacy()
        # an analysis that was running when the dashboard stopped cannot be resumed
        for j in self._jobs_raw():
            if j["status"] == "running":
                j.update(status="failed", error="Interrupted: the dashboard was closed while it ran",
                         finished_at=now_str())
                write_json(self.jobs_dir / str(j["id"]) / "job.json", j)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _next_id(folder: Path) -> int:
        ids = [int(p.name) for p in folder.iterdir() if p.is_dir() and p.name.isdigit()]
        return max(ids, default=0) + 1

    def settings(self) -> dict:
        s = dict(DEFAULTS)
        s.update({k: v for k, v in (read_json(self.out / "settings.json", {}) or {}).items() if k in DEFAULTS})
        return s

    def save_settings(self, data: dict) -> dict:
        clean = {}
        for section in SETTINGS_SCHEMA:
            for key, _, _, spec in section["fields"]:
                if key not in data:
                    continue
                value = data[key]
                if "options" in spec:
                    if str(value) not in [str(o) for o in spec["options"]]:
                        continue
                    value = next(o for o in spec["options"] if str(o) == str(value))
                else:
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        continue
                    value = min(spec["max"], max(spec["min"], value))
                    if isinstance(DEFAULTS[key], int):
                        value = int(round(value))
                clean[key] = value
        merged = self.settings()
        merged.update(clean)
        write_json(self.out / "settings.json", merged)
        return merged

    def cameras(self) -> list[dict]:
        return read_json(self.out / "cameras.json", []) or []

    # ------------------------------------------------------------------ videos
    def video_dir(self, vid: int) -> Path:
        return self.videos_dir / str(vid)

    def new_video_dir(self) -> tuple[int, Path]:
        with self.lock:
            vid = self._next_id(self.videos_dir)
            d = self.video_dir(vid)
            d.mkdir()
            return vid, d

    def finish_video(self, vid: int, name: str, path: Path, uploaded_at: str | None = None) -> dict:
        info = dict(id=vid, name=name, file=path.name, size=path.stat().st_size, uploaded_at=uploaded_at or now_str())
        info.update(probe_video(path))
        write_json(self.video_dir(vid) / "video.json", info)
        return info

    def video(self, vid: int) -> dict | None:
        return read_json(self.video_dir(vid) / "video.json")

    def video_path(self, vid: int) -> Path | None:
        v = self.video(vid)
        return self.video_dir(vid) / v["file"] if v else None

    def videos(self) -> list[dict]:
        jobs = self.jobs()
        out = []
        for d in self.videos_dir.iterdir():
            v = read_json(d / "video.json") if d.name.isdigit() else None
            if not v:
                continue
            mine = [j for j in jobs if j.get("video_id") == v["id"]]
            v["latest_job"] = mine[0] if mine else None
            out.append(v)
        out.sort(key=lambda v: v["id"], reverse=True)
        return out

    def delete_video(self, vid: int) -> str | None:
        with self.lock:
            mine = [j for j in self._jobs_raw() if j.get("video_id") == vid]
            if any(j["status"] == "running" for j in mine):
                return "This video is being analysed. Stop the analysis first."
            for j in mine:
                shutil.rmtree(self.jobs_dir / str(j["id"]), ignore_errors=True)
            shutil.rmtree(self.video_dir(vid), ignore_errors=True)
        return None

    # -------------------------------------------------------------------- jobs
    def job_dir(self, jid: int) -> Path:
        return self.jobs_dir / str(jid)

    def _jobs_raw(self) -> list[dict]:
        out = []
        for d in self.jobs_dir.iterdir():
            j = read_json(d / "job.json") if d.name.isdigit() else None
            if j:
                out.append(j)
        return out

    def job(self, jid: int) -> dict | None:
        j = read_json(self.job_dir(jid) / "job.json")
        return self._decorate(j) if j else None

    def _decorate(self, j: dict) -> dict:
        d = self.job_dir(j["id"])
        st = read_json(d / "status.json", {}) or {}
        total = st.get("total") or 0
        j = dict(j)
        j.update(frame=st.get("frame", 0), total=total, speed=st.get("speed"), people=st.get("people"),
                 progress=(1.0 if j["status"] == "completed" else
                           min(1.0, st.get("frame", 0) / total) if total else 0.0),
                 has_output=(d / "annotated.mp4").is_file() and j["status"] != "running",
                 has_live=(d / "live.jpg").is_file(),
                 event_count=sum(1 for e in (d / "events").glob("event_*") if (e / "event.json").is_file())
                 if (d / "events").is_dir() else 0)
        return j

    def jobs(self) -> list[dict]:
        out = [self._decorate(j) for j in self._jobs_raw()]
        out.sort(key=lambda j: j["id"], reverse=True)
        return out

    def create_job(self, video_id: int | None = None, camera_id: int | None = None) -> tuple[dict | None, str | None]:
        with self.lock:
            if video_id is not None:
                v = self.video(video_id)
                if not v:
                    return None, "Video not found."
                old = [j for j in self._jobs_raw() if j.get("video_id") == video_id]
                if any(j["status"] in ("running", "queued") for j in old):
                    return None, "This video is already being analysed."
                # a new analysis replaces the previous one, so a video never shows two result sets
                for j in old:
                    shutil.rmtree(self.job_dir(j["id"]), ignore_errors=True)
                info = dict(kind="video", video_id=video_id, camera_id=None, is_live=False,
                            source_name=v["name"], location="", duration=v.get("duration", 0))
            else:
                cam = next((c for c in self.cameras() if c["id"] == camera_id), None)
                if not cam:
                    return None, "Camera not found."
                if any(j.get("camera_id") == camera_id and j["status"] in ("running", "queued")
                       for j in self._jobs_raw()):
                    return None, "This camera is already running."
                info = dict(kind="camera", video_id=None, camera_id=camera_id, is_live=True,
                            source_name=cam["name"], location=cam.get("location", ""), duration=0)
            jid = self._next_id(self.jobs_dir)
            self.job_dir(jid).mkdir()
            job = dict(id=jid, status="queued", created_at=now_str(), started_at=None, finished_at=None,
                       error="", **info)
            write_json(self.job_dir(jid) / "job.json", job)
            return self._decorate(job), None

    def update_job(self, jid: int, **changes):
        with self.lock:
            p = self.job_dir(jid) / "job.json"
            j = read_json(p)
            if j:
                j.update(changes)
                write_json(p, j)

    def stop_job(self, jid: int) -> str | None:
        with self.lock:
            j = read_json(self.job_dir(jid) / "job.json")
            if not j:
                return "Analysis not found."
            if j["status"] == "queued":
                self.update_job(jid, status="stopped", finished_at=now_str())
            elif j["status"] == "running":
                (self.job_dir(jid) / "stop").write_text("stop")   # detect.py finishes cleanly
                proc = self.procs.get(jid)

                def kill_later():
                    try:
                        proc.wait(timeout=25)
                    except subprocess.TimeoutExpired:
                        proc.terminate()
                if proc:
                    threading.Thread(target=kill_later, daemon=True).start()
        return None

    def delete_job(self, jid: int) -> str | None:
        with self.lock:
            j = read_json(self.job_dir(jid) / "job.json")
            if not j:
                return "Analysis not found."
            if j["status"] == "running":
                return "Stop the analysis before deleting it."
            shutil.rmtree(self.job_dir(jid), ignore_errors=True)
        return None

    # ----------------------------------------------------------------- cameras
    def add_camera(self, name: str, location: str, url: str) -> dict:
        with self.lock:
            cams = self.cameras()
            cam = dict(id=max([c["id"] for c in cams], default=0) + 1, name=name, location=location,
                       source_url=url, created_at=now_str())
            cams.append(cam)
            write_json(self.out / "cameras.json", cams)
            return cam

    def delete_camera(self, cid: int) -> str | None:
        with self.lock:
            if any(j.get("camera_id") == cid and j["status"] in ("running", "queued") for j in self._jobs_raw()):
                return "Stop the camera before removing it."
            write_json(self.out / "cameras.json", [c for c in self.cameras() if c["id"] != cid])
        return None

    def cameras_public(self) -> list[dict]:
        jobs = self._jobs_raw()
        out = []
        for c in self.cameras():
            live = next((j["id"] for j in jobs if j.get("camera_id") == c["id"]
                         and j["status"] in ("running", "queued")), None)
            out.append(dict(id=c["id"], name=c["name"], location=c.get("location", ""),
                            source=mask_url(c["source_url"]), live_job_id=live))
        return out

    # ------------------------------------------------------------------ events
    def events(self, job_id: int | None = None) -> list[dict]:
        jobs = {j["id"]: j for j in self._jobs_raw()}
        now = datetime.now()
        out = []
        for jid, j in jobs.items():
            if job_id is not None and jid != job_id:
                continue
            ev_dir = self.job_dir(jid) / "events"
            if not ev_dir.is_dir():
                continue
            folders = sorted(d for d in ev_dir.iterdir() if EVENT_DIR.fullmatch(d.name))
            for n, d in enumerate(folders, 1):
                e = read_json(d / "event.json")
                if not e:
                    continue   # being written right now
                try:
                    files = sorted(f.name for f in d.iterdir() if f.is_file() and not f.name.endswith(".tmp"))
                    mtime = int(max(f.stat().st_mtime for f in d.iterdir()))
                except (OSError, ValueError):
                    continue
                review = read_json(d / "review.json", {}) or {}
                try:
                    age = (now - datetime.strptime(e.get("captured_at", ""), "%Y-%m-%d %H:%M:%S")).total_seconds()
                except ValueError:
                    age = None
                e.update(id=f"{jid}/{d.name}", job_id=jid, folder=d.name, number=n, files=files, mtime=mtime,
                         source_name=j["source_name"], location=e.get("location") or j.get("location", ""),
                         is_live=j["is_live"], status=review.get("status", "new"),
                         notes=review.get("notes", ""), reviewed_at=review.get("at"),
                         is_active=bool(j["is_live"] and j["status"] == "running" and age is not None and age < 120))
                out.append(e)
        out.sort(key=lambda e: e.get("captured_at", ""), reverse=True)
        return out

    def review(self, jid: int, folder: str, status: str, notes: str | None) -> str | None:
        d = self.job_dir(jid) / "events" / folder
        if not EVENT_DIR.fullmatch(folder) or status not in REVIEW_STATES or not (d / "event.json").is_file():
            return "Unknown event."
        old = read_json(d / "review.json", {}) or {}
        write_json(d / "review.json", dict(status=status, notes=(old.get("notes", "") if notes is None else notes)[:1000],
                                            at=now_str()))
        return None

    # ---------------------------------------------------------- legacy layout
    def _migrate_legacy(self):
        """Earlier versions kept output/uploads and output/events flat: move them into videos / jobs."""
        uploads, events = self.out / "uploads", self.out / "events"
        by_name: dict[str, int] = {}
        if uploads.is_dir():
            for f in sorted(uploads.iterdir()):
                if f.is_file() and f.suffix.lower() in VIDEO_EXT:
                    vid, d = self.new_video_dir()
                    name = safe_name(LEGACY_STAMP.sub("", f.name))
                    stamp = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    shutil.move(str(f), d / name)
                    self.finish_video(vid, name, d / name, stamp)
                    by_name[name] = vid
        if events.is_dir():
            groups: dict[str, list[Path]] = {}
            for d in sorted(events.iterdir()):
                e = read_json(d / "event.json") if d.is_dir() else None
                if e:
                    groups.setdefault(e.get("source") or "earlier analysis", []).append(d)
            for source, folders in groups.items():
                first = read_json(folders[0] / "event.json") or {}
                jid = self._next_id(self.jobs_dir)
                jd = self.job_dir(jid)
                (jd / "events").mkdir(parents=True)
                for d in folders:
                    shutil.move(str(d), jd / "events" / d.name)
                vid = by_name.get(source)
                write_json(jd / "job.json", dict(
                    id=jid, status="completed", created_at=first.get("captured_at", now_str()),
                    started_at=first.get("captured_at"), finished_at=first.get("captured_at"), error="",
                    kind="video" if not first.get("live") else "camera", video_id=vid, camera_id=None,
                    is_live=bool(first.get("live")), source_name=source, location=first.get("location", ""),
                    duration=0))
        for d in (uploads, events):
            try:
                d.rmdir()   # only when empty: nothing is ever deleted here
            except OSError:
                pass


class Runner(threading.Thread):
    """Runs queued analyses one at a time."""

    def __init__(self, store: Store):
        super().__init__(daemon=True)
        self.store = store
        self.current: int | None = None

    def run(self):
        while True:
            try:
                self.tick()
            except Exception as exc:   # never let the queue die
                print("runner:", exc, file=sys.stderr)
            time.sleep(1.0)

    def tick(self):
        s = self.store
        if self.current is not None:
            proc = s.procs.get(self.current)
            if proc and proc.poll() is None:
                return
            self.finish(self.current, proc)
            self.current = None
        with s.lock:
            queued = sorted((j for j in s._jobs_raw() if j["status"] == "queued"), key=lambda j: j["id"])
            if queued:
                self.launch(queued[0])

    def launch(self, job: dict):
        s, jid = self.store, job["id"]
        d = s.job_dir(jid)
        for f in ("live.jpg", "status.json", "stop"):
            (d / f).unlink(missing_ok=True)
        write_json(d / "settings.json", s.settings())
        if job["kind"] == "video":
            path = s.video_path(job["video_id"])
            if not path or not path.is_file():
                s.update_job(jid, status="failed", error="Video file is missing.", finished_at=now_str())
                return
            source = str(path)
        else:
            cam = next((c for c in s.cameras() if c["id"] == job["camera_id"]), None)
            if not cam:
                s.update_job(jid, status="failed", error="Camera was removed.", finished_at=now_str())
                return
            source = cam["source_url"]
        cmd = [sys.executable, str(ROOT / "detect.py"), "--source", source, "--out", str(d),
               "--name", job["source_name"], "--settings", str(d / "settings.json")]
        if job.get("location"):
            cmd += ["--location", job["location"]]
        log = open(d / "detector.log", "w", encoding="utf-8", errors="replace")
        s.procs[jid] = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        s.update_job(jid, status="running", started_at=now_str())
        self.current = jid

    def finish(self, jid: int, proc: subprocess.Popen | None):
        s = self.store
        d = s.job_dir(jid)
        job = read_json(d / "job.json")
        s.procs.pop(jid, None)
        if not job:
            return   # deleted while running
        st = read_json(d / "status.json", {}) or {}
        state = st.get("state")
        if state == "stopped" or (job["is_live"] and state == "finished"):
            status, error = "stopped", ""
        elif proc is not None and proc.returncode == 0 and state == "finished":
            status, error = "completed", ""
        else:
            try:
                tail = (d / "detector.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-3:]
            except OSError:
                tail = []
            status, error = "failed", (st.get("message") or " | ".join(tail) or "Detector stopped unexpectedly")[:400]
        # OpenCV writes MPEG-4 part 2, which browsers do not play: re-encode to H.264 for the player
        out = d / "annotated.mp4"
        if out.is_file() and shutil.which("ffmpeg"):
            web = d / "annotated_web.mp4"
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out), "-c:v", "libx264",
                                "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                                "-movflags", "+faststart", str(web)])
            if r.returncode == 0:
                web.replace(out)
            else:
                web.unlink(missing_ok=True)
        s.update_job(jid, status=status, error=error, finished_at=now_str())


def make_handler(store: Store):

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console quiet
            pass

        # ------------------------------------------------------------ output
        def _send(self, code: int, body: bytes, ctype: str, headers: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass   # the browser left the page or cancelled a load

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _err(self, msg: str | None):
            self._json({"error": msg} if msg else {"ok": True}, 400 if msg else 200)

        def _file(self, path: Path, download: str | None = None):
            """Serve a file with HTTP range support (needed to seek in a <video>)."""
            if not path or not path.is_file():
                return self._send(404, b"not found", "text/plain")
            size = path.stat().st_size
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            start, end, code = 0, size - 1, 200
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
            if m and size:
                a, b = m.groups()
                if a:
                    start, end = int(a), min(int(b), size - 1) if b else size - 1
                elif b:
                    start = max(0, size - int(b))
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                code = 206
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-cache")
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            try:
                with open(path, "rb") as f:
                    f.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = f.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass

        def _local(self) -> bool:
            # only this PC's browser may talk to the dashboard (blocks DNS-rebinding tricks)
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("localhost", "127.0.0.1")

        # ------------------------------------------------------------ GET
        def do_GET(self):
            if not self._local():
                return self._send(403, b"forbidden", "text/plain")
            url = urlsplit(self.path)
            path, q = url.path, {k: v[0] for k, v in parse_qs(url.query).items()}
            download = q.get("download") == "1"

            if path == "/" or path.lstrip("/") in WEB_FILES:
                name = "index.html" if path == "/" else path.lstrip("/")
                return self._send(200, (WEB / name).read_bytes(), WEB_FILES[name])
            if path == "/api/overview":
                return self._json(self.overview())
            if path == "/api/jobs":
                return self._json(store.jobs())
            if path == "/api/videos":
                return self._json(store.videos())
            if path == "/api/cameras":
                return self._json(store.cameras_public())
            if path == "/api/settings":
                return self._json({"values": store.settings(), "defaults": DEFAULTS, "schema": SETTINGS_SCHEMA})
            if path in ("/api/events", "/api/events.csv"):
                jid = int(q["job"]) if q.get("job", "").isdigit() else None
                events = store.events(jid)
                return self._json(events) if path == "/api/events" else self.csv(events)

            m = re.fullmatch(r"/api/jobs/(\d+)(?:/(.*))?", path)
            if m:
                jid, rest = int(m.group(1)), m.group(2) or ""
                job = store.job(jid)
                if not job:
                    return self._send(404, b"not found", "text/plain")
                d = store.job_dir(jid)
                if rest == "":
                    return self._json(job)
                if rest == "live":
                    return self._file(d / "live.jpg")
                if rest == "video":
                    name = Path(job["source_name"]).stem + "_scanned.mp4"
                    return self._file(d / "annotated.mp4", safe_name(name) if download else None)
                if rest == "log":
                    return self._file(d / "detector.log")
                e = re.fullmatch(r"events/(event_[\w-]{1,80})/([\w.\-]{1,120})", rest)
                if e and EVENT_DIR.fullmatch(e.group(1)):
                    folder = d / "events" / e.group(1)
                    if e.group(2) == "package.zip":
                        return self.package(job, folder)
                    if FILE_NAME.fullmatch(e.group(2)):
                        dl = f"job{jid}_{e.group(1)}_{e.group(2)}" if download else None
                        return self._file(folder / e.group(2), dl)
                return self._send(404, b"not found", "text/plain")

            m = re.fullmatch(r"/api/videos/(\d+)/file", path)
            if m:
                v = store.video(int(m.group(1)))
                return self._file(store.video_path(int(m.group(1))) if v else None,
                                  safe_name(v["name"]) if v and download else None)
            self._send(404, b"not found", "text/plain")

        def overview(self) -> dict:
            jobs, events = store.jobs(), store.events()
            return dict(
                events=len(events), unreviewed=sum(e["status"] == "new" for e in events),
                confirmed=sum(e["status"] == "confirmed" for e in events),
                faces=sum("suspect_face.jpg" in e["files"] for e in events),
                jobs_completed=sum(j["status"] == "completed" for j in jobs),
                jobs_running=sum(j["status"] == "running" for j in jobs),
                videos=len(list(store.videos_dir.glob("*/video.json"))), cameras=len(store.cameras()),
                running_jobs=[j for j in jobs if j["status"] in ("running", "queued")],
                recent_events=events[:6], recent_jobs=jobs[:6])

        def csv(self, events: list[dict]):
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["analysis", "event", "source", "location", "type", "captured_at", "video_time_s",
                        "suspect_id", "victim_id", "confidence", "ran_away", "victim_reaction",
                        "victim_had_phone", "phone_changed_hands", "status", "notes"])
            for e in events:
                v = e.get("evidence", {})
                w.writerow([e["job_id"], e["number"], e["source_name"], e["location"],
                            "CCTV" if e["is_live"] else "Video", e.get("captured_at"), e.get("video_time"),
                            e.get("suspect_id"), e.get("victim_id"), e.get("score"), v.get("flee"),
                            v.get("reaction"), v.get("had_phone"), v.get("transfer"), e["status"], e["notes"]])
            self._send(200, buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8",
                       {"Content-Disposition": 'attachment; filename="snatch_events.csv"'})

        def package(self, job: dict, folder: Path):
            if not (folder / "event.json").is_file():
                return self._send(404, b"not found", "text/plain")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(folder.iterdir()):
                    if f.is_file() and not f.name.endswith(".tmp"):
                        z.write(f, f.name)
            name = safe_name(f"{Path(job['source_name']).stem}_{folder.name}.zip")
            self._send(200, buf.getvalue(), "application/zip",
                       {"Content-Disposition": f'attachment; filename="{name}"'})

        # ------------------------------------------------------------ POST
        def _body(self, length: int) -> dict:
            try:
                data = json.loads(self.rfile.read(min(length, 16384)) or b"{}")
            except ValueError:
                return {}
            return data if isinstance(data, dict) else {}

        def do_POST(self):
            # The custom header cannot be sent by a form or a cross-site script without a CORS
            # preflight, which this server never approves: other web pages cannot press our buttons.
            if not self._local() or self.headers.get("X-Requested-With") != "dashboard":
                return self._send(403, b"forbidden", "text/plain")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            path = urlsplit(self.path).path

            if path == "/api/videos":
                return self.upload(length)
            m = re.fullmatch(r"/api/videos/(\d+)/(delete|analyse)", path)
            if m:
                vid = int(m.group(1))
                if m.group(2) == "delete":
                    return self._err(store.delete_video(vid))
                job, err = store.create_job(video_id=vid)
                return self._json({"error": err} if err else job, 400 if err else 200)
            m = re.fullmatch(r"/api/jobs/(\d+)/(stop|delete)", path)
            if m:
                jid = int(m.group(1))
                return self._err(store.stop_job(jid) if m.group(2) == "stop" else store.delete_job(jid))
            if path == "/api/cameras":
                data = self._body(length)
                url = str(data.get("source_url", "")).strip()
                name = str(data.get("name", "")).strip()[:60] or "CCTV camera"
                location = str(data.get("location", "")).strip()[:60]
                # only a camera number or a stream address: never a local file path or an option
                if not (re.fullmatch(r"\d{1,2}", url)
                        or re.fullmatch(r"(rtsp|rtsps|rtmp|http|https)://\S{3,400}", url)):
                    return self._err("Enter an RTSP address (rtsp://...) or a camera number like 0.")
                cam = store.add_camera(name, location, url)
                job, err = store.create_job(camera_id=cam["id"])
                return self._json({"error": err} if err else job, 400 if err else 200)
            m = re.fullmatch(r"/api/cameras/(\d+)/(start|delete)", path)
            if m:
                cid = int(m.group(1))
                if m.group(2) == "delete":
                    return self._err(store.delete_camera(cid))
                job, err = store.create_job(camera_id=cid)
                return self._json({"error": err} if err else job, 400 if err else 200)
            if path == "/api/events/review":
                data = self._body(length)
                jid = data.get("job_id")
                notes = data.get("notes")
                return self._err(store.review(int(jid) if str(jid).isdigit() else -1, str(data.get("folder", "")),
                                              str(data.get("status", "")), None if notes is None else str(notes)))
            if path == "/api/settings":
                return self._json({"values": store.save_settings(self._body(length))})
            if path == "/api/settings/reset":
                write_json(store.out / "settings.json", dict(DEFAULTS))
                return self._json({"values": store.settings()})
            self._send(404, b"not found", "text/plain")

        def upload(self, length: int):
            name = safe_name(unquote(self.headers.get("X-Filename") or ""))
            if Path(name).suffix.lower() not in VIDEO_EXT:
                return self._err("Please upload a video file (mp4, mov, avi, mkv, webm).")
            if not 0 < length <= MAX_UPLOAD:
                return self._err("File is empty or larger than 4 GB.")
            vid, d = store.new_video_dir()
            dest, left = d / name, length
            with open(dest, "wb") as f:
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            if left:
                shutil.rmtree(d, ignore_errors=True)
                return self._err("Upload was interrupted.")
            video = store.finish_video(vid, name, dest)
            job, err = store.create_job(video_id=vid)
            video["latest_job"] = job
            return self._json({"error": err} if err else video, 400 if err else 200)

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Phone snatch detector dashboard")
    ap.add_argument("--out", default="output", help="folder for videos, analyses and settings")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    store = Store(Path(args.out).resolve())
    Runner(store).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
    print(f"Dashboard: http://localhost:{args.port}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for jid in list(store.procs):
            store.stop_job(jid)


if __name__ == "__main__":
    main()
