"""Station phone-snatch detector.

Pipeline per frame:
  1. YOLO pose + ByteTrack  -> every person gets an ID and 17 body keypoints
  2. YOLO detect (cell phone) -> each phone is attached to the nearest wrist
  3. Contact: someone's hand reaches another person's hands / phone
  4. After the contact the pair is watched for a few seconds and scored:
       flee      - one of them sprints away           (required)
       reaction  - the other one jumps up / reaches / chases
       had_phone - the victim was holding a phone before the contact
       transfer  - the phone is now with the runner / gone from the victim
     A calm hand-over between friends has no flee and no reaction -> no alert.
  5. On alert: best face of the suspect seen so far + body + frame + clip saved.

Usage:
  python detect.py --source video.mp4
  python detect.py --source 0 --show            (webcam)
  python detect.py --source rtsp://... --show   (CCTV)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

PHONE_CLASS = 67  # COCO "cell phone"
NOSE, LEYE, REYE, LEAR, REAR, LSH, RSH, LWR, RWR, LHIP, RHIP = 0, 1, 2, 3, 4, 5, 6, 9, 10, 11, 12


@dataclass
class Config:
    # speeds are in "body heights per second" so they work near and far from the camera
    walk_speed: float = 0.9          # normal walking
    run_speed: float = 2.0           # clearly running -> flee score 1.0
    flee_min_speed: float = 1.4      # below this nobody is "fleeing"
    flee_min_dist: float = 0.9       # runner must get this far from the contact point
    speed_window: float = 0.4        # seconds used to measure speed
    contact_dist: float = 0.20       # hand-to-hand distance (x body height) that counts as contact
    phone_wrist_dist: float = 0.22   # phone-to-wrist distance (x body height) for "holding"
    watch_seconds: float = 3.5       # how long a contact is watched
    before_seconds: float = 3.0      # history looked at before the contact
    alert_score: float = 0.55
    kpt_conf: float = 0.3
    clip_before: float = 3.0
    clip_after: float = 3.0


@dataclass
class Sample:
    t: float
    pos: np.ndarray
    h: float
    box: np.ndarray
    kpts: np.ndarray
    speed: float = 0.0
    phone: bool = False


@dataclass
class Track:
    id: int
    hist: deque = field(default_factory=lambda: deque(maxlen=400))
    face_score: float = 0.0
    face_img: np.ndarray | None = None
    body_img: np.ndarray | None = None

    @property
    def last(self) -> Sample:
        return self.hist[-1]

    def scale(self) -> float:
        hs = [s.h for s in list(self.hist)[-12:]]
        return float(np.median(hs)) if hs else 1.0

    def between(self, t0: float, t1: float) -> list[Sample]:
        return [s for s in self.hist if t0 <= s.t <= t1]

    def at(self, t: float) -> Sample | None:
        best = None
        for s in self.hist:
            if s.t <= t:
                best = s
            else:
                break
        return best or (self.hist[0] if self.hist else None)


@dataclass
class Event:
    a: int
    b: int
    t0: float            # first contact
    t1: float            # last contact
    alerted: bool = False
    suspect: int = -1
    victim: int = -1
    score: float = 0.0
    parts: dict = field(default_factory=dict)
    folder: Path | None = None
    t_alert: float = 0.0
    captured_at: str = ""
    clip: list = field(default_factory=list)
    done: bool = False


def clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


class TheftDetector:
    def __init__(self, cfg: Config, out_dir: Path, pose_weights: str, det_weights: str,
                 imgsz: int, device: str | None):
        self.cfg = cfg
        self.out = out_dir
        (out_dir / "events").mkdir(parents=True, exist_ok=True)
        self.pose = YOLO(pose_weights)
        self.det = YOLO(det_weights)
        self.imgsz = imgsz
        self.device = device
        self.tracks: dict[int, Track] = {}
        self.events: dict[tuple[int, int], Event] = {}
        self.alerts: list[Event] = []
        self.buffer: deque = deque()   # (t, jpeg bytes) of annotated frames
        self.phones: list[np.ndarray] = []

    # ------------------------------------------------------------------ models
    def _infer(self, frame: np.ndarray, t: float) -> list[int]:
        r = self.pose.track(frame, persist=True, tracker="bytetrack.yaml", conf=0.25,
                            imgsz=self.imgsz, device=self.device, verbose=False)[0]
        ids: list[int] = []
        if r.boxes.id is not None:
            boxes = r.boxes.xyxy.cpu().numpy()
            kpts = r.keypoints.data.cpu().numpy()
            for box, k, tid in zip(boxes, kpts, r.boxes.id.int().tolist()):
                self._update_track(tid, t, box, k, frame)
                ids.append(tid)

        d = self.det.predict(frame, classes=[PHONE_CLASS], conf=0.12, imgsz=self.imgsz,
                             device=self.device, verbose=False)[0]
        self.phones = list(d.boxes.xyxy.cpu().numpy())
        self._assign_phones(ids)
        return ids

    def _update_track(self, tid: int, t: float, box: np.ndarray, k: np.ndarray, frame: np.ndarray):
        tr = self.tracks.setdefault(tid, Track(tid))
        h = float(box[3] - box[1])
        hips = k[[LHIP, RHIP]]
        if (hips[:, 2] > self.cfg.kpt_conf).all():
            pos = hips[:, :2].mean(axis=0)
        else:
            pos = np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
        s = Sample(t, pos.astype(float), h, box, k)
        tr.hist.append(s)
        # speed over a short window, normalised by body height
        old = None
        for p in reversed(tr.hist):
            if t - p.t >= self.cfg.speed_window:
                old = p
                break
        if old is not None and t - old.t < 3 * self.cfg.speed_window:
            s.speed = self._dist(tr, old, s) / (t - old.t)
        self._update_face(tr, s, frame)

    @staticmethod
    def _dist(tr: Track, a: Sample, b: Sample) -> float:
        """Distance travelled between two samples, in body heights."""
        return float(np.linalg.norm(b.pos - a.pos)) / max(tr.scale(), 1.0)

    def _hands(self, s: Sample) -> list[np.ndarray]:
        return [s.kpts[i, :2] for i in (LWR, RWR) if s.kpts[i, 2] > self.cfg.kpt_conf]

    def _assign_phones(self, ids: list[int]):
        for pb in self.phones:
            c = np.array([(pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2])
            best, best_d = None, 1e9
            for tid in ids:
                tr = self.tracks[tid]
                s = tr.last
                for w in self._hands(s):
                    d = np.linalg.norm(w - c) / max(tr.scale(), 1.0)
                    if d < best_d:
                        best, best_d = s, d
            if best is not None and best_d < self.cfg.phone_wrist_dist:
                best.phone = True

    # ------------------------------------------------------------------- faces
    def _update_face(self, tr: Track, s: Sample, frame: np.ndarray):
        k = s.kpts
        conf = float(min(k[NOSE, 2], k[LEYE, 2], k[REYE, 2]))
        if conf < 0.5:
            if tr.body_img is None:
                tr.body_img = self._crop(frame, s.box, 0.05)
            return
        eye = float(np.linalg.norm(k[LEYE, :2] - k[REYE, :2]))
        side = 2.8 * eye
        if k[LSH, 2] > 0.5 and k[RSH, 2] > 0.5:
            side = max(side, 0.7 * float(np.linalg.norm(k[LSH, :2] - k[RSH, :2])))
        side = max(side, 20.0) * 1.35   # a bit of margin: hair, cap, chin
        cx, cy = k[NOSE, :2]
        box = np.array([cx - side / 2, cy - side * 0.6, cx + side / 2, cy + side * 0.5])
        crop = self._crop(frame, box, 0.0)
        if crop is None or min(crop.shape[:2]) < 12:
            return
        sharp = cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
        score = side * conf * (1.0 + min(sharp, 400.0) / 400.0)
        if score > tr.face_score:
            tr.face_score = score
            tr.face_img = crop
            tr.body_img = self._crop(frame, s.box, 0.05)

    @staticmethod
    def _crop(frame: np.ndarray, box: np.ndarray, pad: float) -> np.ndarray | None:
        H, W = frame.shape[:2]
        w, h = box[2] - box[0], box[3] - box[1]
        x0, y0 = int(max(0, box[0] - pad * w)), int(max(0, box[1] - pad * h))
        x1, y1 = int(min(W, box[2] + pad * w)), int(min(H, box[3] + pad * h))
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
        return frame[y0:y1, x0:x1].copy()

    # ---------------------------------------------------------------- contacts
    def _find_contacts(self, ids: list[int], t: float):
        cfg = self.cfg
        for i, a in enumerate(ids):
            sa = self.tracks[a].last
            ha = self._hands(sa)
            for b in ids[i + 1:]:
                sb = self.tracks[b].last
                # quick reject: boxes (slightly grown) must overlap
                m = 0.15 * max(sa.h, sb.h)
                if (sa.box[0] - m > sb.box[2] or sb.box[0] - m > sa.box[2]
                        or sa.box[1] - m > sb.box[3] or sb.box[1] - m > sa.box[3]):
                    continue
                hb = self._hands(sb)
                if not ha or not hb:
                    continue
                d = min(np.linalg.norm(p - q) for p in ha for q in hb)
                if d / max(self.tracks[a].scale(), self.tracks[b].scale(), 1.0) > cfg.contact_dist:
                    continue
                key = (a, b)
                ev = self.events.get(key)
                if ev is None or ev.done:
                    self.events[key] = Event(a, b, t, t)
                elif not ev.alerted:
                    ev.t1 = t

    # ----------------------------------------------------------------- scoring
    def _score(self, ev: Event, s_id: int, v_id: int, t: float) -> tuple[float, dict, bool]:
        cfg = self.cfg
        S, V = self.tracks[s_id], self.tracks[v_id]
        s_after = S.between(ev.t1, t)
        v_after = V.between(ev.t1, t)
        v_before = V.between(ev.t0 - cfg.before_seconds, ev.t0)
        s_at = S.at(ev.t1)
        if not s_after or s_at is None:
            return 0.0, {}, False

        # --- flee: suspect sprints away from the contact point
        peak = max(x.speed for x in s_after)
        dist = max(self._dist(S, s_at, x) for x in s_after)
        flee = clip01((peak - cfg.walk_speed) / (cfg.run_speed - cfg.walk_speed))
        flee_ok = peak >= cfg.flee_min_speed and dist >= cfg.flee_min_dist

        # --- victim reaction: speed burst, standing up, arm reaching toward the runner
        burst = stand = reach = 0.0
        if v_after:
            base_speed = float(np.median([x.speed for x in v_before])) if v_before else 0.0
            burst = clip01((max(x.speed for x in v_after) - base_speed - 0.2) / 0.6)
            if len(v_before) >= 5 and len(v_after) >= 5:
                # medians, because box height flickers when people overlap in a crowd
                base_h = float(np.median([x.h for x in v_before]))
                now_h = float(np.median([x.h for x in v_after[-8:]]))
                stand = clip01((now_h / max(base_h, 1.0) - 1.1) / 0.25)
            for x in v_after:
                sx = S.at(x.t)
                if sx is None:
                    continue
                k = x.kpts
                torso = 0.3 * x.h
                if min(k[LSH, 2], k[RSH, 2], k[LHIP, 2], k[RHIP, 2]) > cfg.kpt_conf:
                    torso = float(np.linalg.norm(k[[LSH, RSH], :2].mean(0) - k[[LHIP, RHIP], :2].mean(0)))
                for sh, wr in ((LSH, LWR), (RSH, RWR)):
                    if k[sh, 2] < cfg.kpt_conf or k[wr, 2] < cfg.kpt_conf:
                        continue
                    arm = k[wr, :2] - k[sh, :2]
                    to_s = sx.pos - k[sh, :2]
                    n = np.linalg.norm(arm) * np.linalg.norm(to_s)
                    if n < 1e-6 or float(arm @ to_s) / n < 0.3:
                        continue
                    reach = max(reach, clip01((np.linalg.norm(arm) / max(torso, 1.0) - 0.9) / 0.5))
        reaction = max(burst, stand, reach)

        # --- phone evidence
        had_phone = clip01(sum(x.phone for x in v_before) / 4.0)
        s_before = S.between(ev.t0 - 1.5, ev.t0)
        s_new_phone = any(x.phone for x in s_after) and not any(x.phone for x in s_before)
        v_lost_phone = had_phone > 0 and len(v_after) >= 5 and not any(x.phone for x in v_after[-5:])
        # only meaningful if the victim really had a phone (the runner may carry their own)
        transfer = 0.0 if had_phone == 0 else (1.0 if s_new_phone else (0.6 if v_lost_phone else 0.0))

        score = 0.40 * flee + 0.25 * reaction + 0.20 * had_phone + 0.15 * transfer
        parts = dict(flee=round(flee, 2), peak_speed=round(peak, 2), flee_dist=round(dist, 2),
                     reaction=round(reaction, 2), burst=round(burst, 2), stand=round(stand, 2),
                     reach=round(reach, 2), had_phone=round(had_phone, 2), transfer=transfer)
        # Path A: a clear sprint. Running alone is never enough: the victim must react or
        #         must have been holding a phone.
        sprint = flee_ok and (reaction >= 0.3 or had_phone >= 0.5)
        # Path B: the phone visibly changed hands, the victim reacts strongly and the taker
        #         leaves. Covers a thief running straight away from the camera, where the
        #         speed in the image looks small. A friendly hand-over has no strong reaction.
        grabbed = (had_phone >= 0.5 and transfer >= 1.0 and reaction >= 0.6
                   and dist >= cfg.flee_min_dist)
        ok = score >= cfg.alert_score and (sprint or grabbed)
        return score, parts, ok

    def _evaluate(self, t: float, frame: np.ndarray):
        for key, ev in list(self.events.items()):
            if ev.alerted or ev.done:
                continue
            if t - ev.t1 > self.cfg.watch_seconds:
                ev.done = True
                continue
            if ev.a not in self.tracks or ev.b not in self.tracks:
                continue
            for s_id, v_id in ((ev.a, ev.b), (ev.b, ev.a)):
                score, parts, ok = self._score(ev, s_id, v_id, t)
                if score > ev.score:
                    ev.score, ev.parts, ev.suspect, ev.victim = score, parts, s_id, v_id
                if ok:
                    ev.score, ev.parts, ev.suspect, ev.victim = score, parts, s_id, v_id
                    self._alert(ev, t, frame)
                    break

    # ------------------------------------------------------------------ alerts
    def _alert(self, ev: Event, t: float, frame: np.ndarray):
        # one alert per suspect; if a later contact fits better, it only corrects the victim
        for e in self.alerts:
            if e.suspect == ev.suspect and e is not ev:
                if ev.score > e.score and not e.done:
                    e.victim, e.score, e.parts, e.t0 = ev.victim, ev.score, ev.parts, ev.t0
                    print(f"[ALERT] victim corrected to #{e.victim}  score={e.score:.2f}  {e.parts}")
                    self._save_event(e)
                ev.done = True
                return
        ev.alerted, ev.t_alert = True, t
        ev.captured_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.alerts.append(ev)
        frame = frame.copy()
        x0, y0, x1, y1 = map(int, self.tracks[ev.suspect].last.box)
        cv2.rectangle(frame, (x0, y0), (x1, y1), (0, 0, 255), 3)
        # time in the name, so earlier runs stay on the dashboard instead of being overwritten
        ev.folder = self.out / "events" / f"event_{datetime.now():%Y%m%d_%H%M%S}_{len(self.alerts):03d}"
        ev.folder.mkdir(parents=True, exist_ok=True)
        ev.clip = [j for (ft, j) in self.buffer if ft >= ev.t0 - self.cfg.clip_before]
        print(f"[ALERT] t={t:.2f}s  suspect=#{ev.suspect}  victim=#{ev.victim}  "
              f"score={ev.score:.2f}  {ev.parts}")
        self._save_event(ev, frame)

    def _save_event(self, ev: Event, frame: np.ndarray | None = None):
        S = self.tracks.get(ev.suspect)
        if S is not None:
            if S.face_img is not None:
                f = S.face_img
                k = max(1.0, 256.0 / max(f.shape[:2]))
                cv2.imwrite(str(ev.folder / "suspect_face.jpg"),
                            cv2.resize(f, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC))
            if S.body_img is not None:
                cv2.imwrite(str(ev.folder / "suspect_body.jpg"), S.body_img)
        V = self.tracks.get(ev.victim)
        if V is not None and V.body_img is not None:
            cv2.imwrite(str(ev.folder / "victim.jpg"), V.body_img)
        if frame is not None:
            cv2.imwrite(str(ev.folder / "alert_frame.jpg"), frame)
        info = dict(captured_at=ev.captured_at, video_time=round(ev.t_alert, 2), suspect_id=ev.suspect, victim_id=ev.victim, contact_time=round(ev.t0, 2),
                    alert_time=round(ev.t_alert, 2), score=round(ev.score, 2), evidence=ev.parts,
                    face_captured=bool(S is not None and S.face_img is not None))
        (ev.folder / "event.json").write_text(json.dumps(info, indent=2))

    def _finish_events(self, t: float, fps: float, force: bool = False):
        for ev in self.alerts:
            if ev.done or not (force or t - ev.t_alert >= self.cfg.clip_after):
                continue
            ev.done = True
            self._save_event(ev)  # face may have improved since the alert
            if ev.clip:
                first = cv2.imdecode(ev.clip[0], cv2.IMREAD_COLOR)
                vw = cv2.VideoWriter(str(ev.folder / "clip.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                     fps, (first.shape[1], first.shape[0]))
                for j in ev.clip:
                    vw.write(cv2.imdecode(j, cv2.IMREAD_COLOR))
                vw.release()
                ev.clip = []
                # browsers cannot play OpenCV's mp4v, so re-encode to H.264 when ffmpeg exists
                if shutil.which("ffmpeg"):
                    raw, web = ev.folder / "clip.mp4", ev.folder / "clip_web.mp4"
                    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(web)])
                    if r.returncode == 0:
                        web.replace(raw)

    # ----------------------------------------------------------------- drawing
    def _draw(self, frame: np.ndarray, ids: list[int], t: float) -> np.ndarray:
        img = frame.copy()
        suspects = {e.suspect for e in self.alerts}
        victims = {e.victim for e in self.alerts}
        for pb in self.phones:
            cv2.rectangle(img, (int(pb[0]), int(pb[1])), (int(pb[2]), int(pb[3])), (0, 255, 255), 2)
        for tid in ids:
            s = self.tracks[tid].last
            x0, y0, x1, y1 = map(int, s.box)
            if tid in suspects:
                col, label, th = (0, 0, 255), f"THIEF #{tid}", 3
            elif tid in victims:
                col, label, th = (0, 165, 255), f"VICTIM #{tid}", 2
            else:
                col, label, th = (170, 170, 170), f"#{tid}" + (" phone" if s.phone else ""), 1
            cv2.rectangle(img, (x0, y0), (x1, y1), col, th)
            cv2.putText(img, label, (x0, max(12, y0 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
        if any(t - e.t_alert < 4.0 for e in self.alerts):
            cv2.rectangle(img, (0, 0), (img.shape[1], 44), (0, 0, 255), -1)
            cv2.putText(img, "PHONE SNATCHING DETECTED", (12, 31),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        return img

    # -------------------------------------------------------------------- loop
    def step(self, frame: np.ndarray, t: float, fps: float) -> np.ndarray:
        ids = self._infer(frame, t)
        self._find_contacts(ids, t)
        self._evaluate(t, frame)
        # keep refreshing the suspect's best face while they are still visible
        img = self._draw(frame, ids, t)
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            self.buffer.append((t, jpg))
            for ev in self.alerts:
                if not ev.done:
                    ev.clip.append(jpg)
        while self.buffer and t - self.buffer[0][0] > self.cfg.clip_before + self.cfg.watch_seconds + 1:
            self.buffer.popleft()
        self._finish_events(t, fps)
        # forget people not seen for a while (unless they are part of an alert)
        keep = {e.suspect for e in self.alerts} | {e.victim for e in self.alerts}
        for tid in [k for k, tr in self.tracks.items() if t - tr.last.t > 15 and k not in keep]:
            del self.tracks[tid]
        return img


def main():
    ap = argparse.ArgumentParser(description="Phone snatching detector for stations")
    ap.add_argument("--source", required=True, help="video file, camera index or RTSP url")
    ap.add_argument("--out", default="output")
    ap.add_argument("--pose-model", default="yolo11s-pose.pt")
    ap.add_argument("--phone-model", default="yolo11s.pt")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--device", default=None, help="cpu, 0 (GPU) ...")
    ap.add_argument("--stride", type=int, default=1, help="process every Nth frame (faster)")
    ap.add_argument("--show", action="store_true", help="show live window")
    ap.add_argument("--debug", action="store_true", help="print every watched contact")
    args = ap.parse_args()

    live = args.source.isdigit() or "://" in args.source
    cap = cv2.VideoCapture(int(args.source) if args.source.isdigit() else args.source)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open source: {args.source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    if not 1 <= fps <= 120:
        fps = 25.0
    out_fps = fps / args.stride
    out = Path(args.out)
    det = TheftDetector(Config(), out, args.pose_model, args.phone_model, args.imgsz, args.device)

    writer = None
    n, t = 0, 0.0
    t_start = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        if (n - 1) % args.stride:
            continue
        t = time.time() - t_start if live else (n - 1) / fps
        img = det.step(frame, t, out_fps)
        if writer is None:
            writer = cv2.VideoWriter(str(out / "annotated.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                     out_fps, (img.shape[1], img.shape[0]))
        writer.write(img)
        if args.show:
            cv2.imshow("station theft detector (q = quit)", img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    det._finish_events(t, out_fps, force=True)
    cap.release()
    if writer is not None:
        writer.release()
    cv2.destroyAllWindows()

    if args.debug:
        top = sorted(((max(s.speed for s in tr.hist), tid) for tid, tr in det.tracks.items()), reverse=True)
        print("  fastest tracks:", [(tid, round(v, 2)) for v, tid in top[:8]])
        for ev in det.events.values():
            if ev.score > 0.2:
                print(f"  contact #{ev.a}-#{ev.b} t={ev.t0:.2f} alerted={ev.alerted} "
                      f"score={ev.score:.2f} {ev.parts}")
    print(f"\nFrames: {n}   alerts: {len(det.alerts)}   output: {out.resolve()}")


if __name__ == "__main__":
    main()
