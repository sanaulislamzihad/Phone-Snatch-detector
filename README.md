# Phone Snatch Detector

Detects phone snatching at railway / bus stations from CCTV video and captures the thief's face.

A phone in someone's hand is not suspicious, and handing a phone to a friend is not theft.
So the detector does not alert on phones or on running alone. It looks for the whole pattern:

1. **Contact** - one person's hand reaches another person's hands / phone
2. **Flee** - that person then runs away from the spot
3. **Victim reaction** - the other person jumps up, reaches toward the runner or chases
4. **Phone evidence** - the victim was holding a phone before, and it is now with the runner

A friendly hand-over has contact and a phone changing hands, but nobody flees and nobody
reacts, so it stays below the alert score.

## How it works

| Step | Model |
|------|-------|
| People + body keypoints + tracking IDs | YOLO11 pose + ByteTrack |
| Phones (attached to the nearest wrist) | YOLO11 detect, COCO class `cell phone` |
| Snatch decision | rule-based score over ~3.5 s after each contact (`detect.py`) |
| Face capture | best (largest, sharpest, most frontal) face of the suspect's track |

Speeds are measured in body-heights per second, so they work for people near and far from the camera.

## Setup

```
py -3.11 -m venv .venv
.venv\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\pip install -r requirements.txt
```

Model weights download automatically on the first run.

## Run

```
.venv\Scripts\python detect.py --source video.mp4          # video file
.venv\Scripts\python detect.py --source 0 --show           # webcam
.venv\Scripts\python detect.py --source rtsp://... --show  # CCTV stream
.venv\Scripts\python dashboard.py                          # http://localhost:8000
```

Useful options: `--stride 2` (process every 2nd frame, faster on CPU), `--device 0` (GPU),
`--debug` (print the score of every watched contact).

## Output

```
output/
  annotated.mp4                 full video with boxes and alert banner
  events/event_<time>_001/
    suspect_face.jpg            best face of the thief
    suspect_body.jpg
    victim.jpg
    alert_frame.jpg
    clip.mp4                    few seconds before and after the snatch
    event.json                  capture time, IDs, score, evidence
```

The dashboard lists every event with the face, capture time, evidence and clip, and refreshes itself.

## Limits

- Facial expression is not used: on CCTV a face is only 20-40 px, too small for reliable
  emotion recognition. The victim's reaction is read from body pose and movement instead.
- A thief running straight away from the camera moves little in the image; that case relies
  on the phone being seen changing hands plus a strong victim reaction.
- Face quality depends on the camera: a cap, a hood or a face turned away gives a poor crop.
- Thresholds in `Config` were tuned on two sample clips; real station footage will need more tuning.
