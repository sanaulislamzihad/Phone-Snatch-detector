"""Control room for the phone snatch detector.

  python dashboard.py            -> http://localhost:8000

Views
  Overview          totals, latest detections, detector state
  Snatch Watch      upload a recorded video or connect a CCTV camera; every captured snatch
                    as a card (suspect face -> victim face) with confirm / dismiss review
  Live Monitoring   the annotated picture of whatever is being analysed right now
  Videos            uploaded videos, their detections, analyse again

The dashboard starts detect.py as a separate process and talks to it through files in the
output folder (status.json, live.jpg, stop), so a crash in one does not take down the other.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
MAX_UPLOAD = 4 * 1024 ** 3   # 4 GB
REVIEW_STATES = {"new", "confirmed", "dismissed"}
EVENT_ID = re.compile(r"event_[\w-]{1,80}")
UPLOAD_STAMP = re.compile(r"^\d{8}_\d{6}_")


def display_name(upload_name: str) -> str:
    """'20261114_090000_platform1.mp4' -> 'platform1.mp4'"""
    return UPLOAD_STAMP.sub("", upload_name)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phone Snatch Detector</title>
<style>
  :root {
    --bg:#f4f6f8; --card:#fff; --line:#e4e8ed; --text:#18212c; --dim:#6b7785; --faint:#98a2af;
    --side:#0f1722; --side2:#1b2634; --side-text:#c5cdd8;
    --accent:#2f6f62; --accent-soft:#e6f2ee; --red:#d33a4c; --red-soft:#fdedef;
    --amber:#d9862a; --amber-soft:#fdf4e6; --violet:#6a50c6; --violet-soft:#f4f0fd;
    --green:#1f9d63; --green-soft:#e5f5ed; --blue:#2f6fd6; --blue-soft:#e9f1fd;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.45 "Segoe UI", system-ui, -apple-system, sans-serif; }
  [hidden] { display:none !important; }
  svg { flex:none; }
  .app { display:grid; grid-template-columns:232px minmax(0, 1fr); min-height:100vh; }

  /* sidebar */
  aside { background:var(--side); color:var(--side-text); padding:16px 12px; position:sticky; top:0;
          height:100vh; display:flex; flex-direction:column; }
  .brand { display:flex; gap:10px; align-items:center; padding:4px 8px 18px; margin-bottom:12px;
           border-bottom:1px solid rgba(255,255,255,.07); }
  .logo { width:34px; height:34px; border-radius:8px; background:var(--accent); color:#fff;
          display:grid; place-items:center; flex:none; }
  .brand b { display:block; color:#fff; font-size:14px; line-height:1.2; }
  .brand small { color:#8c98a8; font-size:11px; }
  nav a { display:flex; align-items:center; gap:10px; padding:9px 10px; border-radius:7px; margin-bottom:2px;
          color:var(--side-text); text-decoration:none; font-size:13px; white-space:nowrap; }
  nav a:hover { background:var(--side2); }
  nav a.on { background:var(--accent); color:#fff; }
  nav .count { margin-left:auto; background:var(--red); color:#fff; border-radius:999px; font-size:11px;
               font-weight:600; padding:0 7px; }
  .side-status { margin-top:auto; display:flex; gap:8px; align-items:center; font-size:12px;
                 padding:10px; border-radius:8px; background:var(--side2); }
  .side-status span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .dot { width:8px; height:8px; border-radius:50%; background:#6b7785; flex:none; }
  .dot.on { background:#3ddc84; box-shadow:0 0 6px #3ddc84; }
  .dot.err { background:var(--red); }

  /* page */
  main { padding:28px 32px 48px; min-width:0; }
  h1 { font-size:22px; margin:0; }
  .sub { color:var(--dim); margin:2px 0 20px; font-size:13px; }
  h3.sec { font-size:15px; margin:0 0 12px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px;
          box-shadow:0 1px 2px rgba(16,24,40,.04); }
  .eyebrow { font-size:10.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--faint); font-weight:600; }
  .dim { color:var(--dim); font-size:12.5px; }
  .link { color:var(--accent); font-weight:600; font-size:12.5px; text-decoration:none; cursor:pointer;
          background:none; border:0; padding:0; font-family:inherit; }
  .link:hover { text-decoration:underline; }
  input[type=text], select { background:#fff; border:1px solid var(--line); border-radius:7px; padding:8px 10px;
          font:inherit; font-size:13px; color:var(--text); min-width:0; }
  input[type=text]:focus, select:focus { outline:3px solid var(--accent-soft); border-color:var(--accent); }
  .btn { display:inline-flex; align-items:center; justify-content:center; gap:6px; border:1px solid var(--line);
         background:#fff; color:var(--text); border-radius:7px; padding:7px 12px; font:inherit; font-size:13px;
         font-weight:600; cursor:pointer; white-space:nowrap; }
  .btn:hover { background:#f6f8f9; }
  a.btn { text-decoration:none; }
  .btn:disabled { opacity:.5; cursor:not-allowed; }
  .btn.red { background:var(--red); border-color:var(--red); color:#fff; }
  .btn.red:hover { background:#bf2f40; }
  .btn.teal { background:var(--accent); border-color:var(--accent); color:#fff; }
  .btn.sq { padding:7px 9px; }
  .btn.ok { background:var(--green-soft); border-color:var(--green); color:var(--green); }
  .btn.no { background:#eef0f3; border-color:#a9b2bd; color:#4b5562; }

  /* option cards */
  .options { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .opt { padding:18px; display:flex; flex-direction:column; }
  .opt-head { display:flex; gap:12px; align-items:flex-start; margin-bottom:14px; }
  .opt-ic { width:38px; height:38px; border-radius:9px; display:grid; place-items:center; flex:none; }
  .opt-ic.g { background:var(--accent-soft); color:var(--accent); }
  .opt-ic.r { background:var(--red-soft); color:var(--red); }
  .opt h2 { font-size:15px; margin:0; }
  .opt p { margin:2px 0 0; color:var(--dim); font-size:12.5px; }
  .drop { border:1.5px dashed #cdd5dd; border-radius:9px; padding:24px 12px; text-align:center; cursor:pointer;
          transition:background .15s, border-color .15s; flex:1; display:flex; flex-direction:column;
          align-items:center; justify-content:center; }
  .drop:hover, .drop.over { border-color:var(--accent); background:var(--accent-soft); }
  .drop.off { opacity:.5; cursor:not-allowed; }
  .drop > svg { color:var(--accent); }
  .drop b { display:block; font-size:13px; margin-top:6px; }
  .drop small { color:var(--faint); font-size:11.5px; }
  .opt-foot { margin-top:12px; }
  .fields { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .fields .wide { grid-column:1 / -1; display:flex; gap:8px; }
  .fields .wide input { flex:1; }
  .note { font-size:12.5px; margin-top:10px; min-height:18px; color:var(--accent); }
  .note.err { color:var(--red); }

  /* running job strip */
  .job { display:flex; align-items:center; gap:12px; padding:10px 14px; margin-top:14px; flex-wrap:wrap; }
  .job .grow { flex:1; min-width:180px; }
  .job .txt { font-size:13px; font-weight:600; }
  .bar { height:6px; background:#edf0f3; border-radius:3px; overflow:hidden; margin-top:6px; }
  .bar i { display:block; height:100%; background:var(--accent); border-radius:3px; transition:width .4s; }
  .bar.red i { background:var(--red); }

  /* filters */
  .filters { display:flex; align-items:flex-end; gap:18px; flex-wrap:wrap; padding:14px 16px; margin:14px 0 22px; }
  .filters .f { display:flex; flex-direction:column; gap:4px; min-width:220px; }
  .check { display:flex; align-items:center; gap:6px; font-size:13px; padding-bottom:8px; cursor:pointer; }
  .check input { accent-color:var(--accent); width:15px; height:15px; margin:0; }
  .filters .meta { margin-left:auto; font-size:12.5px; color:var(--dim); padding-bottom:8px; }
  .meta b { color:var(--red); font-weight:600; }

  /* detection cards */
  .grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(min(380px, 100%), 1fr)); gap:14px; }
  .det { padding:14px 16px; }
  .det.dismissed { opacity:.55; }
  .det-head { display:flex; align-items:center; gap:8px; font-size:12.5px; color:var(--dim); min-width:0; }
  .det-head .name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .tag { display:inline-flex; align-items:center; gap:4px; background:var(--accent-soft); color:var(--accent);
         font-weight:600; font-size:11.5px; padding:2px 7px; border-radius:5px; flex:none; }
  .tag.live { background:var(--red-soft); color:var(--red); }
  .badge { margin-left:auto; font-size:11px; font-weight:600; padding:2px 9px; border-radius:999px; flex:none;
           background:var(--blue-soft); color:var(--blue); }
  .badge.confirmed { background:var(--green-soft); color:var(--green); }
  .badge.dismissed { background:#eef0f3; color:#5d6773; }
  .pair { display:flex; align-items:flex-start; justify-content:center; gap:14px; margin:16px 0 4px; }
  .who { text-align:center; }
  .ph { width:92px; height:92px; border-radius:10px; overflow:hidden; border:2.5px solid var(--red); background:#1b1f24;
        display:grid; place-items:center; color:#9aa4b1; font-size:11px; cursor:zoom-in; }
  .who.victim .ph { border-color:var(--amber); }
  .ph img { width:100%; height:100%; object-fit:cover; object-position:center top; display:block; }
  .who > span { display:block; font-size:11.5px; font-weight:600; color:var(--red); margin-top:6px; }
  .who.victim > span { color:var(--amber); }
  .arrow { color:var(--red); text-align:center; font-size:9.5px; font-weight:700; letter-spacing:.08em; padding-top:30px; }
  .stats { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin:14px 0 10px; }
  .stat { background:#f8f9fb; border:1px solid var(--line); border-radius:8px; padding:8px 6px; text-align:center; }
  .stat small { display:block; font-size:10px; letter-spacing:.07em; text-transform:uppercase; color:var(--dim); font-weight:600; }
  .stat b { font-size:16px; font-variant-numeric:tabular-nums; }
  .stat b.red { color:var(--red); }
  .evbox { background:var(--violet-soft); color:var(--violet); border-radius:7px; padding:8px 10px; font-size:12px; }
  .evbox div + div { color:#8a7bc4; margin-top:2px; }
  .det-foot { display:flex; align-items:center; gap:6px; margin-top:12px; }
  .det-foot .link { margin-left:auto; }
  .empty { grid-column:1 / -1; text-align:center; color:var(--dim); padding:48px 16px; }

  /* overview */
  .tiles { display:grid; grid-template-columns:repeat(4, 1fr); gap:14px; margin-bottom:16px; }
  .tile { padding:16px; }
  .tile b { display:block; font-size:26px; margin-top:4px; font-variant-numeric:tabular-nums; }
  .two { display:grid; grid-template-columns:minmax(0, 3fr) minmax(260px, 2fr); gap:14px; }
  .pad { padding:16px; }
  .latest { display:flex; align-items:center; gap:12px; padding:10px 0; border-top:1px solid var(--line); cursor:pointer; }
  .latest:first-of-type { border-top:0; }
  .latest img, .latest .noimg { width:44px; height:44px; border-radius:8px; object-fit:cover; object-position:center top;
          border:2px solid var(--red); background:#1b1f24; flex:none; }
  .latest .grow { flex:1; min-width:0; }
  .latest .grow div { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .kv { display:grid; grid-template-columns:auto 1fr; gap:6px 14px; font-size:13px; margin:10px 0 14px; }
  .kv dt { color:var(--dim); } .kv dd { margin:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

  /* live */
  .screen { background:#0b0f14; border-radius:8px; aspect-ratio:16/9; overflow:hidden; display:grid;
            place-items:center; color:#8c98a8; text-align:center; }
  .screen img { width:100%; height:100%; object-fit:contain; display:block; }
  .live-head { display:flex; align-items:center; gap:10px; margin-bottom:12px; flex-wrap:wrap; }
  .live-head .grow { flex:1; min-width:0; font-weight:600; }

  /* videos */
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; font-size:10.5px; letter-spacing:.07em; text-transform:uppercase; color:var(--dim);
       font-weight:600; padding:10px 14px; border-bottom:1px solid var(--line); }
  td { padding:11px 14px; border-bottom:1px solid var(--line); }
  tr:last-child td { border-bottom:0; }
  td.num { font-variant-numeric:tabular-nums; }
  .pill { display:inline-block; font-size:11.5px; font-weight:600; padding:1px 8px; border-radius:999px;
          background:var(--red-soft); color:var(--red); }
  .pill.zero { background:#eef0f3; color:#5d6773; }
  .table-wrap { overflow-x:auto; }

  /* inspect dialog */
  dialog#insp { border:0; padding:0; border-radius:12px; width:min(1120px, 96vw); max-height:94vh;
                box-shadow:0 24px 64px rgba(0,0,0,.3); color:var(--text); }
  dialog::backdrop { background:rgba(15,23,34,.6); }
  .m-head { display:flex; gap:12px; align-items:flex-start; padding:16px 20px; border-bottom:1px solid var(--line); }
  .m-head h2 { font-size:17px; margin:2px 0; }
  .m-head .grow { flex:1; min-width:0; }
  .m-body { display:grid; grid-template-columns:minmax(0, 1fr) 320px; gap:20px; padding:20px; }
  .m-main { background:#0b0f14; border-radius:8px; display:grid; place-items:center; aspect-ratio:16/9; overflow:hidden; }
  .m-main img { max-width:100%; max-height:100%; object-fit:contain; display:block; }
  .m-cap { font-size:12px; color:var(--dim); margin:6px 0 10px; }
  .strip { display:flex; gap:8px; flex-wrap:wrap; }
  .strip button { padding:0; border:2px solid var(--line); border-radius:7px; overflow:hidden; width:64px; height:64px;
                  cursor:pointer; background:#1b1f24; }
  .strip button.on { border-color:var(--accent); }
  .strip img { width:100%; height:100%; object-fit:cover; object-position:center top; display:block; }
  .m-body video { width:100%; border-radius:8px; margin-top:14px; background:#000; display:block; }
  .er { margin-bottom:12px; }
  .er-top { display:flex; justify-content:space-between; font-size:13px; }
  .er small { display:block; color:var(--dim); font-size:11.5px; margin-top:3px; }
  .m-review { display:flex; gap:8px; margin-top:16px; flex-wrap:wrap; }

  /* toasts */
  #toasts { position:fixed; top:16px; right:16px; display:flex; flex-direction:column; gap:8px; z-index:20; }
  .toast { background:#fff; border:1px solid var(--line); border-left:4px solid var(--red); border-radius:8px;
           box-shadow:0 10px 28px rgba(16,24,40,.16); padding:10px 14px; display:flex; gap:10px; align-items:center;
           cursor:pointer; width:min(340px, calc(100vw - 32px)); animation:pop .2s ease-out; }
  .toast img { width:40px; height:40px; border-radius:6px; object-fit:cover; object-position:center top; }
  .toast b { color:var(--red); font-size:13px; display:block; }
  @keyframes pop { from { transform:translateY(-8px); opacity:0; } }

  @media (max-width:1000px) { .tiles { grid-template-columns:repeat(2, 1fr); } .two, .m-body { grid-template-columns:1fr; } }
  @media (max-width:900px) {
    .app { grid-template-columns:minmax(0, 1fr); }
    aside { position:static; height:auto; padding:12px 16px; min-width:0; }
    .brand { border:0; padding:0 0 10px; margin:0; }
    nav { display:flex; gap:4px; overflow-x:auto; }
    .side-status { display:none; }
    main { padding:20px 16px 40px; }
    .options { grid-template-columns:1fr; }
  }
  @media (max-width:480px) {
    .fields { grid-template-columns:minmax(0, 1fr); }
    .fields .wide { flex-direction:column; }
    .filters .f { min-width:0; width:100%; } .filters .meta { margin-left:0; }
    .pair { gap:8px; } .ph { width:80px; height:80px; }
  }
</style></head><body>
<div class="app">
  <aside>
    <div class="brand"><div class="logo" data-ic="shield" data-s="18"></div>
      <div><b>Phone Snatch Detector</b><small>Station theft monitoring</small></div></div>
    <nav>
      <a href="#overview" data-ic="grid">Overview</a>
      <a href="#watch" data-ic="scan">Snatch Watch<span class="count" id="newCount" hidden></span></a>
      <a href="#live" data-ic="monitor">Live Monitoring</a>
      <a href="#videos" data-ic="film">Videos</a>
    </nav>
    <div class="side-status"><span class="dot" id="sDot"></span><span id="sText">Detector idle</span></div>
  </aside>

  <main>
    <!-- ======================= OVERVIEW ======================= -->
    <section id="v-overview" hidden>
      <h1>Overview</h1>
      <p class="sub">Everything the detector has captured so far</p>
      <div class="tiles">
        <div class="card tile"><div class="eyebrow">Snatches captured</div><b id="tTotal">0</b></div>
        <div class="card tile"><div class="eyebrow">Suspect faces</div><b id="tFaces">0</b></div>
        <div class="card tile"><div class="eyebrow">Awaiting review</div><b id="tNew">0</b></div>
        <div class="card tile"><div class="eyebrow">Confirmed</div><b id="tOk">0</b></div>
      </div>
      <div class="two">
        <div class="card pad"><h3 class="sec">Latest detections</h3><div id="latest"></div></div>
        <div class="card pad"><h3 class="sec">Detector</h3>
          <dl class="kv"><dt>State</dt><dd id="oState">idle</dd><dt>Source</dt><dd id="oSource">-</dd>
            <dt>Speed</dt><dd id="oSpeed">-</dd><dt>Alerts</dt><dd id="oAlerts">-</dd></dl>
          <div class="row" style="display:flex;gap:8px;flex-wrap:wrap">
            <a class="btn teal" href="#watch" data-ic="upload">Upload video</a>
            <a class="btn" href="#watch" data-ic="cctv">Connect camera</a></div>
        </div>
      </div>
    </section>

    <!-- ======================= SNATCH WATCH ======================= -->
    <section id="v-watch" hidden>
      <h1>Snatch Watch</h1>
      <p class="sub">Who snatched whose phone &mdash; suspect faces are captured automatically from saved videos and live CCTV</p>
      <div class="options">
        <div class="card opt">
          <div class="opt-head"><div class="opt-ic g" data-ic="film" data-s="18"></div>
            <div><div class="eyebrow">Option 1</div><h2>Saved video</h2>
              <p>Upload recorded footage. It is analysed in the background; results and photos appear below.</p></div></div>
          <div class="drop" id="drop" role="button" tabindex="0" data-ic="upload" data-s="22">
            <b id="dropText">Drop a video here or click to browse</b><small>MP4, MOV, AVI, MKV, WEBM</small></div>
          <input type="file" id="file" accept="video/*" hidden>
          <div class="opt-foot"><a class="link" href="#videos">All uploaded videos &rarr;</a></div>
        </div>
        <div class="card opt">
          <div class="opt-head"><div class="opt-ic r" data-ic="cctv" data-s="18"></div>
            <div><div class="eyebrow">Option 2</div><h2>CCTV live</h2>
              <p>Connect a camera stream. It is analysed in real time and alerts pop up as they happen.</p></div></div>
          <div class="fields">
            <input type="text" id="camName" placeholder="Camera name (e.g. Platform 2 - CAM 03)" maxlength="60" aria-label="Camera name">
            <input type="text" id="camLoc" placeholder="Location (optional)" maxlength="60" aria-label="Location">
            <div class="wide">
              <input type="text" id="camSrc" placeholder="rtsp://user:pass@192.168.1.20:554/stream1  (or 0 for this PC's camera)"
                     autocomplete="off" aria-label="Stream address">
              <button class="btn red" id="startBtn" data-ic="radio">Connect &amp; start</button></div>
          </div>
        </div>
      </div>
      <div class="note" id="note"></div>
      <div class="card job" id="job" hidden>
        <span class="dot on" id="jDot"></span>
        <div class="grow"><div class="txt" id="jText"></div><div class="bar" id="jBar"><i style="width:0"></i></div></div>
        <a class="link" href="#live">Watch live &rarr;</a>
        <button class="btn sq stopBtn" data-ic="stop" title="Stop">Stop</button>
      </div>

      <div class="card filters">
        <label class="f"><span class="eyebrow">Source</span>
          <select id="fSource"><option value="">All videos and cameras</option></select></label>
        <label class="check"><input type="checkbox" id="fNow"> Happening now only</label>
        <label class="check"><input type="checkbox" id="fHide" checked> Hide dismissed</label>
        <div class="meta" id="fMeta"></div>
      </div>
      <h3 class="sec">Detected</h3>
      <div class="grid" id="grid"></div>
    </section>

    <!-- ======================= LIVE ======================= -->
    <section id="v-live" hidden>
      <h1>Live Monitoring</h1>
      <p class="sub">The annotated picture of the video or camera being analysed right now</p>
      <div class="card pad">
        <div class="live-head"><span class="dot" id="lDot"></span><span class="grow" id="lText">Nothing is running</span>
          <button class="btn sq stopBtn" data-ic="stop" hidden>Stop</button></div>
        <div class="screen"><img id="liveImg" alt="Live annotated picture" hidden>
          <div id="liveIdle">Nothing is running.<br><a class="link" href="#watch">Upload a video or connect a camera &rarr;</a></div></div>
        <div class="bar" id="lBar" hidden><i style="width:0"></i></div>
      </div>
    </section>

    <!-- ======================= VIDEOS ======================= -->
    <section id="v-videos" hidden>
      <h1>Videos</h1>
      <p class="sub">Recorded footage uploaded through the dashboard</p>
      <div class="card table-wrap"><table>
        <thead><tr><th>Video</th><th>Size</th><th>Uploaded</th><th>Detections</th><th></th></tr></thead>
        <tbody id="vRows"></tbody></table></div>
    </section>
  </main>
</div>

<dialog id="insp" aria-label="Snatch details"></dialog>
<div id="toasts" aria-live="polite"></div>

<script>
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ICONS = {
  shield:'<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  grid:'<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
  scan:'<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01"/><path d="M15 9h.01"/>',
  monitor:'<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
  film:'<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M3 7.5h4"/><path d="M3 12h18"/><path d="M3 16.5h4"/><path d="M17 3v18"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/>',
  cctv:'<path d="M16.75 12h3.632a1 1 0 0 1 .894 1.447l-2.034 4.069a1 1 0 0 1-1.708.134l-2.124-2.97"/><path d="M17.106 9.053a1 1 0 0 1 .447 1.341l-3.106 6.211a1 1 0 0 1-1.342.447L3.61 12.3a2.92 2.92 0 0 1-1.3-3.91L3.69 5.6a2.92 2.92 0 0 1 3.92-1.3z"/><path d="M2 19h3.76a2 2 0 0 0 1.8-1.1L9 15"/><path d="M2 21v-4"/><path d="M7 9h.01"/>',
  upload:'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
  radio:'<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
  eye:'<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
  check:'<path d="M20 6 9 17l-5-5"/>',
  x:'<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  arrow:'<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  stop:'<rect width="12" height="12" x="6" y="6" rx="1"/>',
  redo:'<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
};
const ic = (n, s = 16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n]}</svg>`;
document.querySelectorAll("[data-ic]").forEach(el => el.insertAdjacentHTML("afterbegin", ic(el.dataset.ic, +el.dataset.s || 16)));

const S = { events: [], status: {}, videos: [], seen: null, sig: "", view: "watch" };
const post = (url, data) => fetch(url, { method: "POST", body: JSON.stringify(data || {}),
  headers: { "X-Requested-With": "dashboard", "Content-Type": "application/json" } }).then(r => r.json());

/* ---------- helpers ---------- */
const pct = x => Math.round((+x || 0) * 100) + "%";
const clock = s => { s = Math.max(0, +s || 0); const m = Math.floor(s / 60);
  return String(m).padStart(2, "0") + ":" + (s - m * 60).toFixed(1).padStart(4, "0"); };
const isNow = e => e.live && e.age != null && e.age < 120;
const has = (e, f) => e.files.includes(f);
const src = (e, f) => `/files/${encodeURIComponent(e.id)}/${f}?v=${e.mtime}`;
function evidenceText(e) {
  const v = e.evidence || {}, out = [];
  if (v.flee >= 0.3) out.push("Ran away");
  if (v.reaction >= 0.3) out.push("Victim reacted");
  if (v.had_phone > 0) out.push("Victim was holding a phone");
  if (v.transfer > 0) out.push("Phone changed hands");
  return out.join(" · ") || "Contact followed by a fast exit";
}
function photo(e, faceFile, bodyFile, alt) {
  const f = has(e, faceFile) ? faceFile : has(e, bodyFile) ? bodyFile : null;
  return f ? `<img src="${src(e, f)}" alt="${alt}" loading="lazy">` : "no photo";
}
function where(e) { return esc(e.source || "unknown source") + (e.location ? " · " + esc(e.location) : ""); }
function note(text, err) { const n = $("#note"); n.textContent = text || ""; n.className = "note" + (err ? " err" : ""); }

/* ---------- views ---------- */
const VIEWS = ["overview", "watch", "live", "videos"];
function route() {
  let h = location.hash.slice(1);
  if (h.startsWith("inspect=")) {          // direct link to one event: #inspect=<event id>
    S.pending = decodeURIComponent(h.slice(8));
    history.replaceState(null, "", "#watch");
    h = "watch";
    if (S.events.length) openPending();
  }
  S.view = VIEWS.includes(h) ? h : "watch";
  for (const v of VIEWS) {
    $("#v-" + v).hidden = v !== S.view;
    document.querySelector(`nav a[href="#${v}"]`).classList.toggle("on", v === S.view);
  }
  if (S.view === "videos") loadVideos();
  if (S.view === "live") refreshLive(true);
}
window.addEventListener("hashchange", route);

/* ---------- detection cards ---------- */
function card(e) {
  const r = e.review || "new";
  const at = e.live ? esc((e.captured_at || "").slice(11)) : clock(e.video_time);
  const after = Math.max(0, (+e.alert_time || 0) - (+e.contact_time || 0)).toFixed(1) + "s";
  return `<article class="card det ${r}">
    <div class="det-head">
      <span class="tag ${e.live ? "live" : ""}">${ic(e.live ? "cctv" : "film", 12)}${e.live ? "CCTV" : "Video"}</span>
      <span class="name">${where(e)}</span>
      <span class="badge ${r}">${r === "new" ? "New" : r === "confirmed" ? "Confirmed" : "Dismissed"}</span>
    </div>
    <div class="pair">
      <div class="who"><div class="ph" data-act="inspect" data-id="${e.id}">${photo(e, "suspect_face.jpg", "suspect_body.jpg", "suspect")}</div>
        <span>Suspect · ID ${esc(e.suspect_id)}</span></div>
      <div class="arrow">SNATCHED<br>${ic("arrow", 18)}</div>
      <div class="who victim"><div class="ph" data-act="inspect" data-id="${e.id}">${photo(e, "victim_face.jpg", "victim.jpg", "victim")}</div>
        <span>Victim · ID ${esc(e.victim_id)}</span></div>
    </div>
    <div class="stats">
      <div class="stat"><small>Confidence</small><b class="red">${pct(e.score)}</b></div>
      <div class="stat"><small>Alert after</small><b>${after}</b></div>
      <div class="stat"><small>At</small><b>${at}</b></div>
    </div>
    <div class="evbox"><div>${esc(evidenceText(e))}</div><div>Captured ${esc(e.captured_at || "-")}</div></div>
    <div class="det-foot">
      <button class="btn" data-act="inspect" data-id="${e.id}">${ic("eye", 14)}Inspect</button>
      <button class="btn sq ${r === "confirmed" ? "ok" : ""}" data-act="confirmed" data-id="${e.id}" title="Confirm theft" aria-label="Confirm">${ic("check", 14)}</button>
      <button class="btn sq ${r === "dismissed" ? "no" : ""}" data-act="dismissed" data-id="${e.id}" title="Dismiss (false alarm)" aria-label="Dismiss">${ic("x", 14)}</button>
      ${has(e, "clip.mp4") ? `<button class="link" data-act="clip" data-id="${e.id}">Open clip &rarr;</button>` : ""}
    </div>
  </article>`;
}

function renderWatch() {
  const sel = $("#fSource"), keep = sel.value;
  const sources = [...new Set(S.events.map(e => e.source).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">All videos and cameras</option>' +
    sources.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
  sel.value = sources.includes(keep) ? keep : "";
  const nowOnly = $("#fNow").checked, hide = $("#fHide").checked;
  const list = S.events.filter(e => (!sel.value || e.source === sel.value) && (!nowOnly || isNow(e))
                                     && (!hide || e.review !== "dismissed"));
  $("#fMeta").innerHTML = `${list.length} detection${list.length === 1 ? "" : "s"} · <b>${S.events.filter(isNow).length} happening now</b>`;
  $("#grid").innerHTML = list.length ? list.map(card).join("")
    : `<div class="card empty">${S.events.length ? "No detections match the filters." : "No snatch detected yet. Upload a video or connect a camera above."}</div>`;
}

function renderOverview() {
  const ev = S.events;
  $("#tTotal").textContent = ev.length;
  $("#tFaces").textContent = ev.filter(e => has(e, "suspect_face.jpg")).length;
  $("#tNew").textContent = ev.filter(e => e.review === "new").length;
  $("#tOk").textContent = ev.filter(e => e.review === "confirmed").length;
  $("#latest").innerHTML = ev.length ? ev.slice(0, 6).map(e => `
    <div class="latest" data-act="inspect" data-id="${e.id}">
      ${has(e, "suspect_face.jpg") ? `<img src="${src(e, "suspect_face.jpg")}" alt="suspect">` : '<span class="noimg"></span>'}
      <div class="grow"><div><b>${where(e)}</b></div><div class="dim">${esc(e.captured_at)} · suspect #${esc(e.suspect_id)}</div></div>
      <span class="pill">${pct(e.score)}</span></div>`).join("")
    : '<div class="dim">Nothing captured yet.</div>';
}

function renderAll() {
  renderWatch(); renderOverview();
  const n = S.events.filter(e => e.review === "new").length;
  $("#newCount").textContent = n; $("#newCount").hidden = !n;
}

/* ---------- inspect dialog ---------- */
function inspect(id, toClip) {
  const e = S.events.find(x => x.id === id);
  if (!e) return;
  S.insp = id;
  const v = e.evidence || {}, r = e.review || "new";
  const shots = [["alert_frame.jpg", "Alert frame - suspect outlined in red"]];
  ["suspect_face.jpg", "suspect_face_2.jpg", "suspect_face_3.jpg", "suspect_face_4.jpg"].forEach((f, i) =>
    shots.push([f, i ? `Suspect face ${i + 1}` : "Suspect - best face"]));
  shots.push(["victim_face.jpg", "Victim face"], ["suspect_body.jpg", "Suspect"], ["victim.jpg", "Victim"]);
  const list = shots.filter(([f]) => has(e, f));
  const row = (label, val, sub) => `<div class="er"><div class="er-top"><span>${label}</span><b>${pct(val)}</b></div>
    <div class="bar red"><i style="width:${pct(val)}"></i></div>${sub ? `<small>${sub}</small>` : ""}</div>`;
  const d = $("#insp");
  d.innerHTML = `
    <div class="m-head"><div class="grow"><div class="eyebrow">Phone snatching · ${e.live ? "CCTV" : "Video"}</div>
      <h2>${where(e)}</h2><div class="dim">Captured ${esc(e.captured_at)} · suspect #${esc(e.suspect_id)} · victim #${esc(e.victim_id)}</div></div>
      <button class="btn sq" data-act="close" aria-label="Close">${ic("x", 16)}</button></div>
    <div class="m-body">
      <div>
        <div class="m-main">${list.length ? `<img id="mImg" src="${src(e, list[0][0])}" alt="">` : "no images"}</div>
        <div class="m-cap" id="mCap">${list.length ? esc(list[0][1]) : ""}</div>
        <div class="strip">${list.map(([f, cap], i) => `<button class="${i ? "" : "on"}" data-shot="${f}" data-cap="${esc(cap)}" title="${esc(cap)}"><img src="${src(e, f)}" alt="${esc(cap)}"></button>`).join("")}</div>
        ${has(e, "clip.mp4") ? `<video id="mClip" src="${src(e, "clip.mp4")}" controls muted preload="metadata"></video>` : ""}
      </div>
      <div>
        <div class="eyebrow" style="margin-bottom:10px">Why it was flagged</div>
        ${row("Confidence", e.score, "")}
        ${row("Ran away", v.flee, `peak ${esc(v.peak_speed)} body-heights/s · moved ${esc(v.flee_dist)} body-heights`)}
        ${row("Victim reaction", v.reaction, `speed burst ${pct(v.burst)} · stood up ${pct(v.stand)} · reached out ${pct(v.reach)}`)}
        ${row("Victim was holding a phone", v.had_phone, "")}
        ${row("Phone changed hands", v.transfer, "")}
        <dl class="kv"><dt>Contact</dt><dd>${clock(e.contact_time)}</dd><dt>Alert</dt><dd>${clock(e.alert_time)}</dd>
          <dt>Captured</dt><dd>${esc(e.captured_at)}</dd></dl>
        <div class="eyebrow">Review</div>
        <div class="m-review">
          <button class="btn ${r === "confirmed" ? "ok" : ""}" data-act="confirmed" data-id="${e.id}">${ic("check", 14)}Confirm theft</button>
          <button class="btn ${r === "dismissed" ? "no" : ""}" data-act="dismissed" data-id="${e.id}">${ic("x", 14)}False alarm</button>
        </div>
      </div>
    </div>`;
  if (!d.open) d.showModal();
  if (toClip && $("#mClip")) { $("#mClip").scrollIntoView({ block: "center" }); $("#mClip").play().catch(() => {}); }
}
$("#insp").addEventListener("click", ev => {
  if (ev.target === ev.currentTarget) return ev.currentTarget.close();   // click on the backdrop
  const shot = ev.target.closest("[data-shot]");
  if (shot) {
    const e = S.events.find(x => x.id === S.insp);
    if (e && $("#mImg")) { $("#mImg").src = src(e, shot.dataset.shot); $("#mCap").textContent = shot.dataset.cap; }
    document.querySelectorAll(".strip button").forEach(b => b.classList.toggle("on", b === shot));
  }
});

/* ---------- actions ---------- */
async function review(id, state) {
  const e = S.events.find(x => x.id === id);
  if (!e) return;
  const next = e.review === state ? "new" : state;          // pressing again undoes it
  const r = await post("/api/review", { id, state: next }).catch(() => ({ error: "Could not save." }));
  if (r.error) return note(r.error, true);
  e.review = next; S.sig = "";
  renderAll();
  if ($("#insp").open) inspect(id);
}
document.addEventListener("click", ev => {
  const el = ev.target.closest("[data-act]");
  if (!el) return;
  const { act, id } = el.dataset;
  if (act === "inspect") inspect(id);
  else if (act === "clip") inspect(id, true);
  else if (act === "confirmed" || act === "dismissed") review(id, act);
  else if (act === "close") $("#insp").close();
  else if (act === "analyse") analyse(el.dataset.file);
});
["#fSource", "#fNow", "#fHide"].forEach(s => $(s).addEventListener("change", renderWatch));

function upload(file) {
  if (!file) return;
  if (S.status.busy) return note("Something is already running. Stop it first.", true);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  xhr.setRequestHeader("X-Requested-With", "dashboard");
  xhr.setRequestHeader("X-Filename", encodeURIComponent(file.name));
  xhr.upload.onprogress = e => { if (e.lengthComputable)
    $("#dropText").textContent = `Uploading ${file.name} … ${Math.round(100 * e.loaded / e.total)}%`; };
  const done = (text, err) => { $("#dropText").textContent = "Drop a video here or click to browse"; note(text, err); loadStatus(); };
  xhr.onload = () => { let r = {}; try { r = JSON.parse(xhr.responseText); } catch (err) {}
    done(r.error || `${file.name} uploaded - analysis started.`, !!r.error); };
  xhr.onerror = () => done("Upload failed.", true);
  note("");
  xhr.send(file);
}
const drop = $("#drop");
drop.onclick = () => { if (!S.status.busy) $("#file").click(); };
drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); drop.click(); } };
$("#file").onchange = e => { upload(e.target.files[0]); e.target.value = ""; };
drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); upload(e.dataTransfer.files[0]); };

$("#startBtn").onclick = async () => {
  const source = $("#camSrc").value.trim();
  if (!source) return note("Enter the camera's RTSP address, or 0 for this PC's camera.", true);
  note("Connecting …");
  const r = await post("/api/start", { source, name: $("#camName").value.trim(), location: $("#camLoc").value.trim() })
    .catch(() => ({ error: "Dashboard not reachable." }));
  note(r.error || "Camera connected - watching for snatches.", !!r.error);
  loadStatus();
};
document.querySelectorAll(".stopBtn").forEach(b => b.onclick = async () => {
  b.disabled = true; await post("/api/stop").catch(() => {}); note("Stopping …"); loadStatus();
});
async function analyse(file) {
  const r = await post("/api/analyse", { file }).catch(() => ({ error: "Dashboard not reachable." }));
  if (r.error) return alert(r.error);
  location.hash = "#live"; loadStatus();
}

/* ---------- polling ---------- */
function toast(e) {
  const t = document.createElement("div");
  t.className = "toast";
  t.innerHTML = `${has(e, "suspect_face.jpg") ? `<img src="${src(e, "suspect_face.jpg")}" alt="">` : ""}
    <div><b>Phone snatching detected</b><div class="dim">${where(e)} · ${esc((e.captured_at || "").slice(11))}</div></div>`;
  t.onclick = () => { t.remove(); location.hash = "#watch"; inspect(e.id); };
  $("#toasts").prepend(t);
  setTimeout(() => t.remove(), 12000);
}
async function loadEvents() {
  let events;
  try { events = await (await fetch("/api/events")).json(); } catch (err) { return; }
  if (S.seen) events.filter(e => !S.seen.has(e.id)).forEach(toast);
  S.seen = new Set(events.map(e => e.id));
  const sig = JSON.stringify(events);
  if (sig === S.sig) return;          // nothing changed: leave the page alone
  S.sig = sig; S.events = events;
  renderAll();
  openPending();
}
function openPending() {
  if (S.pending && S.events.some(e => e.id === S.pending)) inspect(S.pending);
  S.pending = null;
}

function statusText(st) {
  const s = esc(st.source || "");
  switch (st.state) {
    case "starting": return `Starting ${s} (loading models)`;
    case "running": return `${st.live ? "Live" : "Analysing"} · ${s} · ${esc(st.speed)} frames/s · ${esc(st.alerts)} alert(s)`;
    case "finished": return `Finished · ${s} · ${esc(st.alerts)} alert(s)`;
    case "stopped": return `Stopped · ${s} · ${esc(st.alerts)} alert(s)`;
    case "error": return esc(st.message || "Error");
    default: return "Detector idle";
  }
}
function refreshLive(force) {
  const st = S.status, img = $("#liveImg");
  if (!st.has_live) { img.hidden = true; $("#liveIdle").hidden = false; return; }
  img.hidden = false; $("#liveIdle").hidden = true;
  if (force || !img.getAttribute("src") || (st.busy && S.view === "live")) img.src = "/live.jpg?t=" + Date.now();
}
async function loadStatus() {
  let st;
  try { st = await (await fetch("/api/status")).json(); } catch (err) { return; }
  S.status = st;
  const run = st.busy && st.state !== "error", txt = statusText(st);
  const dot = "dot" + (run ? " on" : st.state === "error" ? " err" : "");
  $("#sDot").className = dot; $("#sText").innerHTML = txt;
  $("#lDot").className = dot; $("#lText").innerHTML = st.state ? txt : "Nothing is running";
  $("#job").hidden = !st.busy; $("#jText").innerHTML = txt;
  const prog = st.state === "running" && !st.live && st.total > 0 ? Math.min(100, 100 * st.frame / st.total) : null;
  $("#jBar").hidden = prog == null; $("#lBar").hidden = prog == null;
  if (prog != null) { $("#jBar i").style.width = $("#lBar i").style.width = prog + "%"; }
  document.querySelectorAll(".stopBtn").forEach(b => { b.hidden = !st.busy; b.disabled = false; });
  $("#startBtn").disabled = st.busy;
  drop.classList.toggle("off", !!st.busy);
  $("#oState").textContent = st.state || "idle"; $("#oSource").textContent = st.source || "-";
  $("#oSpeed").textContent = st.speed ? st.speed + " frames/s" : "-";
  $("#oAlerts").textContent = st.alerts ?? "-";
  refreshLive(false);
  if (S.wasBusy && !st.busy && S.view === "videos") loadVideos();
  S.wasBusy = st.busy;
}
async function loadVideos() {
  let vids;
  try { vids = await (await fetch("/api/videos")).json(); } catch (err) { return; }
  const mb = b => b >= 1e9 ? (b / 1e9).toFixed(2) + " GB" : (b / 1e6).toFixed(1) + " MB";
  const runningName = S.status.busy && !S.status.live ? S.status.source : null;
  $("#vRows").innerHTML = vids.length ? vids.map(v => `<tr>
      <td><b>${esc(v.name)}</b></td><td class="num">${mb(v.size)}</td><td class="num">${esc(v.uploaded)}</td>
      <td><span class="pill ${v.detections ? "" : "zero"}">${v.detections}</span></td>
      <td style="text-align:right">${runningName === v.name ? '<span class="dim">analysing …</span>'
        : `<button class="btn" data-act="analyse" data-file="${esc(v.file)}" ${S.status.busy ? "disabled" : ""}>${ic("redo", 14)}Analyse again</button>`}</td></tr>`).join("")
    : '<tr><td colspan="5" class="dim" style="text-align:center;padding:32px">No videos uploaded yet. <a class="link" href="#watch">Upload one &rarr;</a></td></tr>';
}

route(); loadStatus(); loadEvents();
setInterval(loadEvents, 3000);
setInterval(loadStatus, 1000);
setInterval(() => { if (S.view === "videos") loadVideos(); }, 5000);
</script></body></html>
"""


class Jobs:
    """Runs at most one detect.py process at a time."""

    def __init__(self, out: Path):
        self.out = out
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        out.mkdir(parents=True, exist_ok=True)

    def busy(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, source: str, name: str, location: str = "") -> str | None:
        """Returns an error message, or None when the job started."""
        with self.lock:
            if self.busy():
                return "Something is already running. Stop it first."
            for f in ("live.jpg", "status.json", "stop"):
                (self.out / f).unlink(missing_ok=True)
            cmd = [sys.executable, str(ROOT / "detect.py"), "--source", source, "--out", str(self.out)]
            if name:
                cmd += ["--name", name]
            if location:
                cmd += ["--location", location]
            log = open(self.out / "detector.log", "w", encoding="utf-8", errors="replace")
            self.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            return None

    def stop(self):
        with self.lock:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                return
            (self.out / "stop").write_text("stop")   # detect.py sees this and finishes cleanly

        def kill_later():
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.terminate()
        threading.Thread(target=kill_later, daemon=True).start()

    def status(self) -> dict:
        st: dict = {}
        try:
            st = json.loads((self.out / "status.json").read_text())
        except (OSError, ValueError):
            pass
        busy = self.busy()
        # the process died without saying goodbye (bad RTSP address, missing package ...)
        if not busy and self.proc is not None and st.get("state") in ("starting", "running"):
            st = {"state": "error", "source": st.get("source", ""),
                  "message": "Detector stopped unexpectedly. See output/detector.log"}
        st["busy"] = busy
        st["has_live"] = (self.out / "live.jpg").is_file()
        return st


def load_events(events_dir: Path) -> list[dict]:
    events = []
    if not events_dir.is_dir():
        return events
    now = datetime.now()
    for d in events_dir.iterdir():
        j = d / "event.json"
        if not EVENT_ID.fullmatch(d.name) or not j.is_file():
            continue
        try:
            e = json.loads(j.read_text())
            files = sorted(f.name for f in d.iterdir() if f.is_file())
            mtime = int(max(f.stat().st_mtime for f in d.iterdir()))
        except (OSError, ValueError):
            continue  # the folder is being written right now
        try:
            review = json.loads((d / "review.json").read_text()).get("state", "new")
        except (OSError, ValueError, AttributeError):
            review = "new"
        try:
            age = (now - datetime.strptime(e.get("captured_at", ""), "%Y-%m-%d %H:%M:%S")).total_seconds()
        except ValueError:
            age = None
        e.setdefault("live", False)
        e.update(id=d.name, files=files, mtime=mtime, age=age,
                 review=review if review in REVIEW_STATES else "new")
        events.append(e)
    events.sort(key=lambda e: e.get("captured_at", ""), reverse=True)
    return events


def make_handler(out: Path, jobs: Jobs):
    events_dir = out / "events"
    uploads = out / "uploads"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass   # the browser left the page or cancelled an image load: nothing to do

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _local(self) -> bool:
            # only this PC's browser may talk to the dashboard (blocks DNS-rebinding tricks)
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("localhost", "127.0.0.1")

        def do_GET(self):
            if not self._local():
                return self._send(403, b"forbidden", "text/plain")
            path = self.path.split("?")[0]
            if path == "/":
                return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            if path == "/api/status":
                return self._json(jobs.status())
            if path == "/api/events":
                return self._json(load_events(events_dir))
            if path == "/api/videos":
                counts = Counter(e.get("source") for e in load_events(events_dir))
                vids = []
                if uploads.is_dir():
                    for f in uploads.iterdir():
                        if not f.is_file() or f.suffix.lower() not in VIDEO_EXT:
                            continue
                        st = f.stat()
                        name = display_name(f.name)
                        vids.append(dict(file=f.name, name=name, size=st.st_size, mtime=st.st_mtime,
                                         uploaded=datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                                         detections=counts.get(name, 0)))
                vids.sort(key=lambda v: v["mtime"], reverse=True)
                return self._json(vids)
            if path == "/live.jpg":
                try:
                    return self._send(200, (out / "live.jpg").read_bytes(), "image/jpeg")
                except OSError:
                    return self._send(404, b"not found", "text/plain")
            if path.startswith("/files/"):
                parts = [unquote(p) for p in path.split("/")[2:]]
                # exactly <event folder>/<file>, nothing that could escape the events folder
                if (len(parts) == 2 and EVENT_ID.fullmatch(parts[0])
                        and parts[1] not in (".", "..") and re.fullmatch(r"[\w.\-]+", parts[1])):
                    f = events_dir / parts[0] / parts[1]
                    if f.is_file():
                        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                        return self._send(200, f.read_bytes(), ctype)
            self._send(404, b"not found", "text/plain")

        def _body_json(self, length: int) -> dict:
            try:
                data = json.loads(self.rfile.read(min(length, 8192)) or b"{}")
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
            path = self.path.split("?")[0]

            if path == "/api/stop":
                jobs.stop()
                return self._json({"ok": True})

            if path == "/api/start":
                data = self._body_json(length)
                source = str(data.get("source", "")).strip()
                name = str(data.get("name", "")).strip()[:60]
                location = str(data.get("location", "")).strip()[:60]
                # only a camera number or a stream address: never a local file path or an option
                if not (re.fullmatch(r"\d{1,2}", source)
                        or re.fullmatch(r"(rtsp|rtsps|rtmp|http|https)://\S{3,400}", source)):
                    return self._json({"error": "Enter an RTSP address (rtsp://...) or a camera number like 0."})
                return self._json({"error": jobs.start(source, name, location)})

            if path == "/api/review":
                data = self._body_json(length)
                eid, state = str(data.get("id", "")), str(data.get("state", ""))
                folder = events_dir / eid
                if not EVENT_ID.fullmatch(eid) or state not in REVIEW_STATES or not folder.is_dir():
                    return self._json({"error": "Unknown event."})
                review = dict(state=state, at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                (folder / "review.json").write_text(json.dumps(review))
                return self._json({"ok": True})

            if path == "/api/analyse":
                data = self._body_json(length)
                fname = str(data.get("file", ""))
                f = uploads / fname
                if (Path(fname).name != fname or not fname or f.suffix.lower() not in VIDEO_EXT
                        or not f.is_file()):
                    return self._json({"error": "Video not found."})
                return self._json({"error": jobs.start(str(f), display_name(fname))})

            if path == "/api/upload":
                name = Path(unquote(self.headers.get("X-Filename") or "")).name
                name = re.sub(r"[^\w.\- ]", "_", name).strip()
                if Path(name).suffix.lower() not in VIDEO_EXT:
                    return self._json({"error": "Please upload a video file (mp4, avi, mov, mkv, webm)."})
                if not 0 < length <= MAX_UPLOAD:
                    return self._json({"error": "File is empty or larger than 4 GB."})
                if jobs.busy():
                    return self._json({"error": "Something is already running. Stop it first."})
                uploads.mkdir(parents=True, exist_ok=True)
                dest = uploads / f"{time.strftime('%Y%m%d_%H%M%S')}_{name}"
                left = length
                with open(dest, "wb") as f:
                    while left > 0:
                        chunk = self.rfile.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                if left:
                    dest.unlink(missing_ok=True)
                    return self._json({"error": "Upload was interrupted."})
                return self._json({"error": jobs.start(str(dest), name)})

            self._send(404, b"not found", "text/plain")

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Phone snatch detector dashboard")
    ap.add_argument("--out", default="output", help="folder for events, uploads and status")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    jobs = Jobs(out)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(out, jobs))
    print(f"Dashboard: http://localhost:{args.port}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        jobs.stop()


if __name__ == "__main__":
    main()
