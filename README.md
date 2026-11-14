# Phone Snatch Detector

Real-time detection of mobile phone snatching in railway and bus stations from CCTV footage,
with automatic capture of the suspect's and the victim's faces.

![Python](https://img.shields.io/badge/python-3.11-blue)
![YOLO](https://img.shields.io/badge/models-YOLO26%20%2B%20YOLO11--pose-orange)
![License](https://img.shields.io/badge/license-MIT-green)

## Screenshots

**Snatch Watch** - upload a recorded video (Option 1) or connect a CCTV camera (Option 2).
Every captured snatch appears as a card: suspect's face → victim's face, confidence, the
evidence that fired, and buttons to inspect, confirm or dismiss it.

![Snatch Watch page](docs/dashboard.png)

**Event details** - the scanned video jumps to the moment of the snatch; all face shots, body
pictures, the score behind each piece of evidence, operator notes and downloads.

![Event details](docs/inspect.png)

**Live Monitoring** - the annotated picture while an analysis runs, the scanned video when it is
done, with download buttons and the detections of that analysis.

![Live Monitoring page](docs/monitor.png)

**Video Management** - every uploaded video with its analysis, results, downloads and delete.

![Video Management page](docs/videos.png)

**Detection** - the suspect is outlined in red the moment the snatch is confirmed; the stolen phone is boxed in yellow.

![Annotated frame at the moment of the alert](docs/detection.jpg)

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

When a snatch is detected the system saves the best face shots of the suspect and the victim,
their body pictures, the alert frame and a short clip, and shows them on a web dashboard.

## Features

- **Snatch detection, not object detection** - combines contact, flight, victim reaction and phone evidence
- **Hand-over aware** - passing a phone to a friend does not raise an alert
- **Crowd ready** - every person is tracked with an ID; scoring is per pair of people
- **Phones in the hand** - YOLO26 phone detector at 1280 px; weak detections are accepted only when they sit at a wrist
- **Best-face capture** - keeps the four best faces of each tracked person, ranked by size, frontal pose and sharpness
- **One analysis per video** - results of different videos never mix; re-analysing a video replaces its old result
- **Operator dashboard** - Overview, Snatch Watch, Live Monitoring, Snatch Events, Video Management and Settings
- **Downloads** - scanned (annotated) video, original video, each event's photos and clip as a zip, all events as CSV
- **Live CCTV** - RTSP / HTTP streams and USB cameras, saved cameras, automatic reconnect, pop-up alerts
- **Adjustable** - models and every detection threshold can be changed on the Settings page
- **No training required** - pretrained models; weights download on first run

## How it works

```mermaid
flowchart LR
    A[Video file / CCTV stream] --> B[YOLO11 pose + ByteTrack<br>people, IDs, 17 keypoints]
    A --> C[YOLO26 detect<br>phones at 1280 px]
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

A pair of people is watched when either of two things happens:

- **Hand contact** - one person's wrist comes within 0.2 body heights of the other's.
- **Phone appears** - a phone suddenly shows up in someone's hand (none there for the previous
  1.5 s) right next to a person who held one a moment ago. A thief reaching over a bench from
  behind is half hidden and the pose model often misplaces his wrists, so hand contact is never
  seen; the phone moving is.

An alert needs a score of at least **0.55** and one of two patterns:

- **Sprint** - the suspect bolts (runs at least 0.5 body heights/s faster than just before the
  contact), a phone was seen at the victim, and the victim reacts or the phone is seen in the
  suspect's hand at least 0.5 body heights away from the victim's hands (carried away). A thief
  stops or slows down to grab and leaves with the phone; when someone running for a train brushes
  past people holding phones, the phones never leave their owners.
- **Grab** - the phone is seen changing hands, the victim reacts strongly, and the taker leaves.
  This covers a thief running straight away from the camera, whose speed in the image looks small.

The suspect must have been tracked for at least 1.5 s before the contact: without that there is
no way to tell whether they slowed down to grab, or already had the phone in their own hand.

The suspect is always the one who moved further from the contact point, so a thief's own
sprint is never counted as a "victim reaction". When two people next to the thief both held a
phone, the one whose phone is gone afterwards is reported as the victim.

### Tracking through a grab

A thief who bends over a bench and then sprints changes shape and speed so fast that ByteTrack
can give him a new ID several times in half a second. A new ID that appears within about a
second where a lost person is expected to be (their last position plus their velocity), with a
similar body size, continues that person, so their history - phone in hand, face shots - is
kept. If the tracker later brings back the original ID, the two are separated again.

Speeds and distances are normalised by each person's body height, so the same thresholds work
for people near to and far from the camera.

### Phone detection

A phone held in the hand is 10-25 pixels on a station camera and partly covered by fingers.
Three things make it visible to the system:

- **YOLO26s** as the phone detector. On the test clips it found 46 of 48 held phones against 35 for YOLO11s, and runs faster.
- **1280 px** inference resolution for phones, higher than the 960 px used for people.
- **Wrist-guided threshold** - a box needs 25 % confidence anywhere in the picture, but only 5 % when it sits at someone's wrist. A weak box at a hand is almost always a real phone; elsewhere it is usually noise.

YOLO26 has no NMS step, so one phone can come with weaker boxes on top of it; overlapping boxes are merged.

### Face capture

Faces are located from the pose keypoints (nose, eyes, shoulders) and scored every frame:

`quality = eye distance x frontal pose x sharpness x keypoint confidence`

The four best faces of every track are kept, at least half a second apart, so the capture of a
suspect normally comes from *before* the snatch, while they were still walking toward the camera.
Faces keep improving for three seconds after the alert.

## Project structure

```
detect.py          detection pipeline and command line tool
dashboard.py       dashboard server: analyses queue, videos, cameras, events, settings (standard library only)
web/               dashboard page: index.html, app.css, app.js (no build step)
requirements.txt
docs/              screenshots used in this README
output/            created at run time: uploaded videos, analyses, events, settings
```

## Installation

Requires Python 3.11. FFmpeg on the `PATH` is recommended: it makes the scanned video and the
event clips playable in the browser.

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

| Page | What it does |
|------|--------------|
| **Overview** | Totals (snatches, suspect faces, analyses, running now), analyses in progress, recent snatch alerts, recent analyses |
| **Snatch Watch** | *Option 1 - Saved video:* drop a recorded file. *Option 2 - CCTV live:* camera name, optional location and RTSP address (or `0` for a camera on the PC), then *Connect & start*; saved cameras can be started, stopped and removed. Below: one card per detection. The source filter shows the newest analysis by default, so a new scan never mixes with old results; pick *All videos and cameras* to see everything |
| **Live Monitoring** | Pick an analysis: the live annotated picture while it runs, the scanned video when it is done. *Stop*, *Scanned video* and *Original* downloads, live status and the detections of that analysis |
| **Snatch Events** | Table of every detection with filters (analysis, review status, minimum confidence), review buttons, zip download per event and *Export CSV* |
| **Video Management** | Upload several videos at once (they are analysed one after another), follow progress, open, download the scanned or original video, *Analyse again*, *Delete* (removes the video, its scanned video and all its detections). CCTV sessions are listed and deletable too |
| **Settings** | Phone and pose models, resolutions, processor, frame step and every detection threshold. Applies to the next analysis |

Each detection card shows the source (**Video** / **CCTV**), the suspect's face → the victim's face
with their track IDs, **Confidence**, **Alert after** (seconds from the grab to the alert) and
**At** (position in the video, or clock time for a camera), the evidence that fired, and
*Inspect*, ✓ *confirm*, ✕ *dismiss* (press again to undo). *Inspect* opens the event details,
where the operator can add notes and mark the event *confirmed*, *reviewed* or *dismissed*.

While a camera is connected, new detections pop up in the corner. A detection can be linked to
directly: `http://localhost:8000/#/watch?event=<analysis>/<event folder>`.

The dashboard listens on `127.0.0.1` only and is meant to be used on the machine that runs it.
Camera passwords are never sent to the page.

### Command line

```bash
.venv\Scripts\python detect.py --source video.mp4
.venv\Scripts\python detect.py --source rtsp://user:password@192.168.1.10:554/stream1 --name "CAM 03" --location "Platform 2" --show
.venv\Scripts\python detect.py --source 0 --show
```

## Limitations

- **Validated on short test clips only.** Thresholds were tuned on them; expect to re-tune on footage from the actual station, and expect both missed events and false alerts until then.
- **Facial expression is not used.** A face on a station camera is typically 20-40 pixels, too small for reliable emotion recognition. The victim's reaction is read from body pose and movement instead.
- **Motion toward or away from the camera** is under-measured in the image. The *grab* pattern compensates, but depends on the phone being seen in both hands.
- **Phone visibility.** Phones hidden in a palm or pocket are missed; an alert is still possible from a clear sprint plus a victim reaction.
- **Face quality** depends on camera position and resolution. A cap, hood, mask or a face turned away gives a poor capture.
- **One analysis at a time.** Further videos wait in a queue; a suspect is not followed from one camera to another.
- **Identity switches** in dense crowds can split one person into two tracks and lose evidence.
- **A thief who appears less than 1.5 s before the grab** (stepping out from behind a pillar or entering at the frame edge) is not flagged.
- **Edited videos** with scene cuts confuse tracking; the system is built for continuous CCTV footage.
- **YOLOE models** need the `clip` package; Ultralytics installs it automatically the first time one is selected.

## Responsible use

This system produces *leads for a human operator*, not proof. Every alert should be reviewed
by a person before any action is taken. Recording and storing faces of people in public places
is regulated in many jurisdictions - check the applicable law, display the required notices,
restrict access to the output folder, and delete videos and events that are not needed.

## Roadmap

- Fine-tuned phone detector trained on station footage
- GPU / TensorRT export for multi-camera real-time use
- Camera calibration for true ground-plane speed
- Cross-camera re-identification of a suspect
- Operator notifications (sound, SMS, messaging)

## License

MIT - see [LICENSE](LICENSE).
