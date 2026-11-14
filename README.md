# Phone Snatch Detector

Real-time detection of mobile phone snatching in railway and bus stations from CCTV footage,
with automatic capture of the suspect's face.

![Python](https://img.shields.io/badge/python-3.11-blue)
![YOLO11](https://img.shields.io/badge/model-YOLO11-orange)
![License](https://img.shields.io/badge/license-MIT-green)

## Screenshots

**Detection** - the suspect is outlined in red the moment the snatch is confirmed; the stolen phone is boxed in yellow.

![Annotated frame at the moment of the alert](docs/detection.jpg)

**Dashboard** - live view, video upload, camera connection, and one card per captured event with the suspect's faces, capture time, evidence and clip.

![Dashboard with two captured events](docs/dashboard.png)

## Overview

A station camera sees dozens of phones at any moment, and people hand phones to friends all the
time. Detecting "a phone" or "a phone changing hands" is therefore not enough, and neither is
detecting "a person running" - people run for trains.

This project detects the **behaviour pattern of a snatch** instead:

1. someone's hand reaches another person's hands or phone,
2. that person then leaves the spot fast,
3. the other person reacts - jumps up, reaches out, chases,
4. the victim was holding a phone before the contact and the phone is now with the runner.

Each contact between two people is watched for a few seconds and scored on this evidence.
A friendly hand-over has no flight and no reaction, so it stays below the alert threshold.

When a snatch is detected the system saves the suspect's best face shots, body image, the
victim, the alert frame and a short video clip, and shows them on a web dashboard with the
capture time.

## Features

- **Snatch detection, not object detection** - combines contact, flight, victim reaction and phone evidence
- **Hand-over aware** - passing a phone to a friend does not raise an alert
- **Crowd ready** - every person is tracked with an ID; scoring is per pair of people
- **Best-face capture** - keeps the four best faces of each tracked person, ranked by size, frontal pose and sharpness, taken at different moments
- **Evidence package** - faces, body, victim, alert frame, video clip and a JSON record per event
- **Web dashboard** - upload a recorded video or connect a live camera, watch the annotated picture, review captured events
- **Live CCTV** - RTSP / HTTP streams and USB cameras, with automatic reconnect and frame dropping to stay in real time
- **No training required** - uses pretrained YOLO11 models; weights download on first run

## How it works

```mermaid
flowchart LR
    A[Video file / CCTV stream] --> B[YOLO11 pose + ByteTrack<br>people, IDs, 17 keypoints]
    A --> C[YOLO11 detect<br>cell phones at 1280 px]
    B --> D[Phone-to-wrist association]
    C --> D
    B --> E[Contact detection<br>hand reaches hand]
    D --> F[Evidence scoring<br>3.5 s after contact]
    E --> F
    B --> G[Best-face tracker]
    F -->|score above threshold| H[Alert]
    G --> H
    H --> I[Event folder + dashboard]
```

### Evidence and scoring

| Evidence | Weight | How it is measured |
|----------|:------:|--------------------|
| **Flee** | 0.40 | Peak speed of the suspect after the contact, in body-heights per second (0.9 = walking, 2.0 = running), and distance covered from the contact point |
| **Victim reaction** | 0.25 | Strongest of: sudden speed burst, standing up, arm stretched toward the suspect |
| **Victim had phone** | 0.20 | Phone attached to the victim's wrist during the 3 s before the contact |
| **Phone changed hands** | 0.15 | Phone appears at the suspect's wrist after the contact, or disappears from the victim |

An alert needs a score of at least **0.55** and one of two patterns:

- **Sprint** - the suspect clearly runs away, and the victim either reacts or was holding a phone.
- **Grab** - the phone is seen changing hands, the victim reacts strongly, and the taker leaves.
  This covers a thief running straight away from the camera, whose speed in the image looks small.

Speeds and distances are normalised by each person's body height, so the same thresholds work
for people near to and far from the camera.

### Face capture

Faces are located from the pose keypoints (nose, eyes, shoulders) and scored every frame:

`quality = eye distance x frontal pose x sharpness x keypoint confidence`

The four best faces of every track are kept, at least half a second apart, so the capture of a
suspect normally comes from *before* the snatch, while they were still walking toward the camera.
Faces keep improving for three seconds after the alert.

## Project structure

```
detect.py          detection pipeline and command line tool
dashboard.py       web dashboard (Python standard library only)
requirements.txt
output/            created at run time
  events/          one folder per detected snatch
  uploads/         videos uploaded through the dashboard
```

## Installation

Requires Python 3.11. FFmpeg on the `PATH` is optional; it makes event clips playable in the browser.

```bash
git clone https://github.com/sanaulislamzihad/Phone-Snatch-detector.git
cd Phone-Snatch-detector
py -3.11 -m venv .venv
```

Install PyTorch for your hardware, then the remaining packages:

```bash
# CPU only
.venv\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
# NVIDIA GPU (recommended for live cameras) - pick the build for your CUDA version at pytorch.org
.venv\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

.venv\Scripts\pip install -r requirements.txt
```

## Usage

### Dashboard

```bash
.venv\Scripts\python dashboard.py
```

Open <http://localhost:8000>.

- **Analyse a recorded video** - drop a file on the upload box. Progress and the annotated picture appear in *Live view*.
- **Connect a CCTV camera** - enter the camera's RTSP address (for example `rtsp://user:password@192.168.1.10:554/stream1`) or `0` for a camera attached to the PC, then *Start camera*. *Stop* ends the session cleanly.
- **Captured events** - each card shows the suspect's best face, other face shots, capture time, source camera, confidence, the evidence that fired, images of the suspect and victim, and the clip. Click any image to enlarge it.

The dashboard listens on `127.0.0.1` only and is meant to be used on the machine that runs it.

### Command line

```bash
.venv\Scripts\python detect.py --source video.mp4
.venv\Scripts\python detect.py --source rtsp://user:password@192.168.1.10:554/stream1 --name "Platform 2" --show
.venv\Scripts\python detect.py --source 0 --show
```

| Option | Default | Description |
|--------|---------|-------------|
| `--source` | required | Video file, camera index, or RTSP / HTTP stream address |
| `--out` | `output` | Output folder |
| `--name` | source name | Camera or video name stored with each event |
| `--pose-model` | `yolo11s-pose.pt` | Person / keypoint model |
| `--phone-model` | `yolo11s.pt` | Phone detection model |
| `--imgsz` | `960` | Inference resolution for people |
| `--phone-imgsz` | `1280` | Inference resolution for phones |
| `--device` | auto | `cpu`, or a GPU index such as `0` |
| `--stride` | `1` | Video files: process every Nth frame |
| `--show` | off | Show a live window (`q` to quit) |
| `--debug` | off | Print the score of every watched contact |

## Output

```
output/
  annotated.mp4                      full annotated copy (video files only)
  events/event_<date>_<time>_001/
    suspect_face.jpg                 best face of the suspect
    suspect_face_2.jpg ... _4.jpg    next best faces, from other moments
    suspect_body.jpg
    victim.jpg
    alert_frame.jpg                  full frame at the alert, suspect outlined
    clip.mp4                         from 3 s before the contact to 3 s after the alert
    event.json
```

`event.json`:

```json
{
  "captured_at": "2026-11-14 00:58:34",
  "source": "Platform 2 - CAM 03",
  "video_time": 7.46,
  "suspect_id": 5,
  "victim_id": 1,
  "score": 0.56,
  "evidence": { "flee": 0.0, "reaction": 0.82, "had_phone": 1.0, "transfer": 1.0 },
  "face_captured": true
}
```

## Configuration

Detection thresholds live in the `Config` dataclass at the top of `detect.py`.

| Setting | Default | Meaning |
|---------|:-------:|---------|
| `walk_speed` / `run_speed` | 0.9 / 2.0 | Body-heights per second that count as walking / running |
| `flee_min_speed` | 1.4 | Minimum peak speed for the sprint pattern |
| `flee_min_dist` | 0.9 | Body-heights the suspect must move away from the contact point |
| `contact_dist` | 0.20 | Hand-to-hand distance (x body height) that counts as contact |
| `phone_wrist_dist` | 0.22 | Phone-to-wrist distance (x body height) that counts as holding |
| `watch_seconds` | 3.5 | How long a contact is watched |
| `alert_score` | 0.55 | Score needed for an alert |

## Performance

Measured on the development machine (laptop CPU, no GPU), 1280x720 video, default settings:

| Measurement | Result |
|-------------|--------|
| Processing speed | about 1 frame per second |
| Phone held by a seated person, detected at 960 px | 3 of 55 sampled frames |
| Same phone, detected at 1280 px (default) | 37 of 55 sampled frames |
| Snatch detected when processing 24 frames/s | 2 of 2 test clips |
| Snatch detected when processing 8 frames/s | 2 of 2 test clips |
| Snatch detected when processing 4 frames/s | 0 of 2 test clips |

**Live cameras need about 8 processed frames per second or more.** A snatch lasts well under a
second, and at lower rates the contact falls between frames. On a CPU-only machine recorded
videos are analysed correctly (slower than real time), but a live camera needs an NVIDIA GPU
(`--device 0`).

## Limitations

- **Validated on two short clips only.** Thresholds were tuned on them; expect to re-tune on footage from the actual station, and expect both missed events and false alerts until then.
- **Facial expression is not used.** A face on a station camera is typically 20-40 pixels, too small for reliable emotion recognition. The victim's reaction is read from body pose and movement instead.
- **Motion toward or away from the camera** is under-measured in the image. The *grab* pattern compensates, but depends on the phone being seen in both hands.
- **Phone visibility.** Small, dark or hidden phones are missed; an alert is still possible from a clear sprint plus a victim reaction.
- **Face quality** depends on camera position and resolution. A cap, hood, mask or a face turned away gives a poor capture.
- **One camera at a time.** A suspect is not followed from one camera to another.
- **Identity switches** in dense crowds can split one person into two tracks and lose evidence.

## Responsible use

This system produces *leads for a human operator*, not proof. Every alert should be reviewed
by a person before any action is taken. Recording and storing faces of people in public places
is regulated in many jurisdictions - check the applicable law, display the required notices,
restrict access to the output folder, and delete events that are not needed.

## Roadmap

- Fine-tuned phone detector trained on station footage
- GPU / TensorRT export for multi-camera real-time use
- Camera calibration for true ground-plane speed
- Cross-camera re-identification of a suspect
- Operator notifications (sound, SMS, messaging)

## License

MIT - see [LICENSE](LICENSE).
