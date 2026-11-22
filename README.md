# StreamCut Cloud

Paste a completed livestream link in GitHub Actions. Get captioned vertical MP4 drafts back as a downloadable artifact. Processing happens on GitHub's runners, not your laptop. No paid AI API key, subscription, local editor or automatic posting is required.

This is an independent, small implementation inspired by the workflow of [PeakCut](https://github.com/haziqahmedqasmi/PeakCut), not a fork or a hosted PeakCut instance.

## Use it entirely in your browser

1. Open this repository's **Actions** tab.
2. Select **Create vertical clips → Run workflow**.
3. Paste an authorized **YouTube video/completed livestream** or **Twitch VOD** link.
4. Leave the start at `0`, scan minutes at `60`, and requested clips at `8` for the first run.
5. Confirm you have download, editing and reuse permission, then click **Run workflow**.
6. Wait for all jobs to finish. Open the run and download **streamcut-clips** under **Artifacts**.
7. Extract the ZIP and open **review.html** to play and compare the results.

The first run also downloads the speech model. It can take tens of minutes or longer depending on footage access, speech density and runner performance. This is a batch workflow, not an always-on website.

**Artifacts expire after one day. Download them promptly.** In a private repository, the artifact and source URL are visible to people with repository access. Do not paste credentials, cookies, private tokens or signed confidential links into workflow inputs.

## What you get

| Output | Purpose |
| --- | --- |
| `clip-01.mp4`, etc. | 1080×1920 H.264/AAC draft cuts, usually about 35 seconds |
| Matching `.srt` files | Editable English subtitles, also burned into the MP4 |
| Matching `.jpg` files | Actual frames for preview thumbnails |
| `manifest.json` | Original timestamps, transcript, title excerpts and ranking scores |
| `review.html` | Offline video review gallery |

The layout retains the entire source picture and facecam, fitted over a blurred copy of the original footage. It does not track faces or independently crop a separate streamer panel. No generated footage, generated voice, logos, promotional hashtags or publication integrations are included.

## How moment selection works

1. Validate the source, completed broadcast status, scan limits and rights confirmation.
2. Split the requested scan into 30-minute windows, with a small overlap for boundaries.
3. Fetch window audio with yt-dlp and FFmpeg. Transcribe using faster-whisper `small.en` on CPU.
4. Rank speech-rich windows by relative audio energy, reaction phrases and speech density.
5. Globally remove overlapping and nearly identical transcript candidates.
6. Fetch just the selected video sections and render captions, audio normalization and the vertical layout.
7. Check dimensions, audio presence and whether FFmpeg can decode every output.

**Speech recognition uses an AI model. Highlight ranking is a transparent heuristic, not an LLM, visual scene analysis or a prediction of virality.** It can miss quiet jokes or choose loud but uninteresting speech. Captions may contain transcription errors. You must review meaning, timing, framing, rights and background music before posting. Sparse footage can produce fewer clips than requested. A clip count is a target, not a quality guarantee.

## Long streams and the ₹0 budget

You can set `scan_minutes` up to `1440` (24 hours). `start_seconds` skips an initial waiting screen or selects a later scan window. You do not have to find individual moments yourself. Each scan job handles approximately 30 minutes, at most two jobs run concurrently, and rendering runs afterward. A full-day stream needs up to 48 transcription jobs and may take hours.

**No paid API is used, but GitHub compute and artifact storage are not universally free.** Private repositories consume the owner's included Actions allowance; usage and storage beyond included allowances can incur charges depending on the account's billing settings. Check **Settings → Billing and licensing** and set a blocking spending budget before processing long streams. This code cannot enforce your account-level spending policy or guarantee a ₹0 bill.

Standard hosted runner compute for public repositories is free under GitHub's current rules, but artifact storage has its own allowance and publishing a repo exposes its workflow inputs, logs and results. Choose visibility deliberately; this workflow does not change it. Reference: [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

No cache is created, raw media is not uploaded as an artifact, and intermediate candidate/plan artifacts expire after one day.

## Source access and limitations

- Clip only content you own or have permission to download, edit and reuse, consistent with source-platform terms.
- Public playback does not establish reuse permission.
- An active stream must end and finish processing into a VOD before this workflow can run.
- YouTube sometimes blocks data-centre runner downloads, requires login or changes supported formats. Such runs can fail even when playback works in your browser. This is a real limitation; the repository cannot promise every link will work.
- The workflow does not use account cookies, proxies, DRM bypasses, geo-unblocking or access-control workarounds. If access is denied, use an authorized accessible VOD; do not try to bypass the restriction.
- English transcription only. No live rolling recorder, upload service, persistent dashboard or auto-publishing.
- This generic entertainment tool does not determine campaign eligibility, audience geography, content rights or payout eligibility.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| No **Run workflow** button | Ensure `clip.yml` is on the default branch and Actions is enabled |
| Repository unavailable through a GitHub connection | Grant that connection access to this private repo |
| Plan job fails | Check URL, completed VOD availability, rights checkbox and numeric limits |
| Download returns login/bot/region/access error | Stop; use a permitted, accessible source. No bypass is provided |
| Scan times out | Reduce scan range or try a later window; runner performance varies |
| No candidates | Try a range containing English dialogue rather than music or waiting screens |
| Some captions are wrong | Edit the SRT and rerender in an editor before posting |
| Fewer than eight clips | Not enough distinct speech-rich candidates were found in this scan |
| Artifact missing/expired | Download within a day; failed jobs may only have partial output |

The code intentionally fails on unexpectedly mismatched section durations rather than silently producing misaligned captions. Some providers' seek behavior can still introduce subsecond offsets that need review.

## Development

Python 3.12, FFmpeg (including libass/subtitles support) and ffprobe are required on the processing host. GitHub installs these in the workflow. No installation on your computer is needed for normal use.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s . -v
```

Tests cover URL boundaries, bounded long-stream planning, duplicate suppression, subtitle timestamps, silent input and a real FFmpeg render smoke test when FFmpeg/ffprobe are available. The tests do not download a real creator's video or post anything.

Dependencies are constrained to compatible major versions but are not a hash-locked supply-chain snapshot; provider support and model downloads depend on third-party availability.

## License

MIT for this repository's code. Third-party dependencies and models retain their own licenses. This license does not grant rights to source videos, voices, music or brands.

