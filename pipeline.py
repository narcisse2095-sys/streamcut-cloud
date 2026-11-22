"""Cloud batch runner. No account cookies, proxies, publication or paid APIs."""
import argparse
import array
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave

from core import (validate_source, reject_private_dns, plan_chunks,
                   make_candidates, select_candidates, subtitles)


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, timeout=3600, **kwargs)


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def checked_url():
    url = validate_source(os.environ.get('SOURCE_URL', '').strip())
    reject_private_dns(url)
    if os.environ.get('RIGHTS_CONFIRMED', '').lower() != 'true':
        raise ValueError('Confirm you have download and editing permission before running.')
    return url


def plan(args):
    url = checked_url()
    import yt_dlp
    with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': True, 'socket_timeout': 30,
                          'cachedir': False, 'retries': 1}) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming', 'post_live'):
        raise ValueError('Wait for the broadcast to end and the VOD to finish processing. Active streams are not supported.')
    chunks = plan_chunks(float(info.get('duration') or 0), args.start, args.minutes, args.count)
    data = dict(title=info.get('title', 'Livestream'), source_url=url,
                duration=info.get('duration'), requested_clips=args.count, chunks=chunks)
    write_json('work/plan.json', data)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as f:
            f.write('matrix=' + json.dumps({'include': chunks}, separators=(',', ':')) + '\n')
    print(f'Planned {len(chunks)} scan windows. No videos are committed to the repository.')


def download(url, start, end, directory, audio=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'source.%(ext)s'
    cmd = [sys.executable, '-m', 'yt_dlp', '--no-playlist', '--no-progress',
           '--no-cache-dir', '--socket-timeout', '30', '--retries', '1',
           '--fragment-retries', '1', '--abort-on-unavailable-fragments',
           '--download-sections', f'*{start:.3f}-{end:.3f}',
           '--force-keyframes-at-cuts', '--max-filesize', '3G', '-o', target]
    if audio:
        cmd += ['-f', 'bestaudio/best', '-x', '--audio-format', 'wav']
    else:
        cmd += ['-f', 'bv*[height<=1080]+ba/b[height<=1080]',
                '--merge-output-format', 'mp4', '--recode-video', 'mp4']
    # The URL is one argument, never shell code. No cookies or bypass flags.
    run(cmd + ['--', url])
    files = list(directory.glob('source.wav' if audio else 'source.mp4'))
    if len(files) != 1:
        raise RuntimeError('Download did not produce the expected media file. Source may block cloud downloads.')
    return files[0]


def probe(path):
    result = run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                  '-of', 'json', path], capture_output=True, text=True)
    return json.loads(result.stdout)


def energies(path):
    with wave.open(str(path), 'rb') as f:
        rate = f.getframerate()
        values = []
        while True:
            samples = array.array('h', f.readframes(rate))
            if not samples:
                break
            values.append(math.sqrt(sum(float(x)*x for x in samples) / len(samples)))
    ordered = sorted(values)
    baseline = ordered[len(ordered)//2] if ordered else 0
    ceiling = ordered[min(len(ordered)-1, int(len(ordered)*.95))] if ordered else 1
    return [max(0, min(1, (x - baseline) / max(1, ceiling - baseline))) for x in values]


def scan(args):
    url = checked_url()
    root = Path(f'work/scan-{args.index}')
    source = download(url, args.start, args.end, root, audio=True)
    wav = root / 'mono.wav'
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', source,
         '-vn', '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', wav])
    duration = float(probe(wav)['format']['duration'])
    if abs(duration - (args.end - args.start)) > 3:
        raise RuntimeError('Downloaded section timing differs from requested range; refusing misaligned captions.')
    from faster_whisper import WhisperModel
    model = WhisperModel('small.en', device='cpu', compute_type='int8', cpu_threads=2)
    segments, _ = model.transcribe(str(wav), language='en', word_timestamps=True,
                                   vad_filter=True, condition_on_previous_text=False)
    words = []
    for segment in segments:
        if segment.no_speech_prob > .7:
            continue
        for word in segment.words or []:
            words.append(dict(start=float(word.start), end=float(word.end), word=word.word.strip()))
    candidates = make_candidates(words, energies(wav), args.start, duration, args.core_end)
    write_json(f'output/candidates-{args.index}.json', candidates)
    print(f'Window {args.index}: {len(words)} words; {len(candidates)} distinct candidate moments.')


def render(args):
    url = checked_url()
    candidates = []
    for path in sorted(Path('candidates').rglob('candidates-*.json')):
        candidates.extend(read_json(path))
    selected = select_candidates(candidates, args.count)
    if not selected:
        raise RuntimeError('No speech-rich candidates found. Try another scan range; no empty clips will be fabricated.')
    output = Path('output')
    output.mkdir(exist_ok=True)
    manifest = dict(source_url=url, requested=args.count, produced=len(selected),
                    selection='Relative audio energy + English reaction terms + speech density; heuristic ranking.',
                    review_required=True, clips=[])
    for i, candidate in enumerate(selected, 1):
        stem = f'clip-{i:02}'
        source = download(url, candidate['start'], candidate['end'], f'work/render-{i}')
        duration = candidate['end'] - candidate['start']
        actual = float(probe(source)['format']['duration'])
        if abs(actual - duration) > 1.5:
            raise RuntimeError('Downloaded clip timing is inaccurate. Refusing to create misaligned captions.')
        srt = output / f'{stem}.srt'
        srt.write_text(subtitles(candidate['words'], candidate['start'], candidate['end']), encoding='utf-8')
        # Fit retains gameplay and any facecam. Background uses only the original footage.
        layout = ('[0:v]split=2[bg][fg];'
                  '[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,'
                  'boxblur=30:2,setsar=1[b];'
                  '[fg]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[f];'
                  '[b][f]overlay=(W-w)/2:(H-h)/2[base];')
        style = 'FontName=DejaVu Sans,FontSize=17,Bold=1,Outline=2,Shadow=1,Alignment=2,MarginV=38'
        # Controlled relative filenames avoid filter-path escaping and source text interpolation.
        filters = layout + f"[base]subtitles={stem}.srt:force_style='{style}',fps=30,format=yuv420p[v]"
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', source.resolve(),
             '-filter_complex', filters, '-map', '[v]', '-map', '0:a:0', '-t', duration,
             '-c:v', 'libx264', '-preset', 'fast', '-crf', '21', '-threads', '2',
             '-c:a', 'aac', '-b:a', '160k', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
             '-movflags', '+faststart', f'{stem}.mp4'], cwd=output)
        result = probe(output / f'{stem}.mp4')
        video = next(s for s in result['streams'] if s['codec_type'] == 'video')
        if (video['width'], video['height']) != (1080, 1920):
            raise RuntimeError('Output dimensions failed validation.')
        if not any(s['codec_type'] == 'audio' for s in result['streams']):
            raise RuntimeError('Output is missing audio.')
        run(['ffmpeg', '-v', 'error', '-i', output / f'{stem}.mp4', '-f', 'null', '-'])
        run(['ffmpeg', '-v', 'error', '-y', '-ss', '1', '-i', output / f'{stem}.mp4',
             '-frames:v', '1', output / f'{stem}.jpg'])
        manifest['clips'].append(dict(file=f'{stem}.mp4', thumbnail=f'{stem}.jpg',
              start=candidate['start'], end=candidate['end'], score=candidate['score'],
              suggested_title=' '.join(candidate['transcript'].split()[:12]),
              transcript=candidate['transcript'], technical_qc='1080x1920, audio present, full decode passed'))
        shutil.rmtree(source.parent)
        write_json(output / 'manifest.json', manifest)
    gallery = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
               '<title>StreamCut review</title><style>body{background:#101218;color:#eee;font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px}section{display:inline-block;width:300px;vertical-align:top;margin:16px}video{width:280px}p{line-height:1.6}</style>',
               '<h1>StreamCut · Review your clips</h1><p>Draft cuts. Check the captions, meaning, rights and framing before posting. No automatic publication.</p>']
    import html
    for clip in manifest['clips']:
        gallery.append(f'<section><h2>{html.escape(clip["file"])}</h2><video controls preload="none" poster="{clip["thumbnail"]}" src="{clip["file"]}"></video><p>{html.escape(clip["suggested_title"])}</p><p>Source: {clip["start"]:.1f}–{clip["end"]:.1f}s</p></section>')
    (output / 'review.html').write_text('\n'.join(gallery) + '</html>', encoding='utf-8')
    (output / 'REVIEW.txt').write_text('Review each MP4 against its original footage. Correct transcription errors and check meaning, timing, framing, music rights and permission to reuse. Automated checks do not establish content quality or eligibility. Nothing is posted automatically.\n', encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write(f'## Clips ready for review\nProduced {len(selected)} of {args.count} requested clips.\nDownload the **streamcut-clips** artifact and open review.html.\n')


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--start', type=float, default=0)
    p.add_argument('--minutes', type=float, default=60)
    p.add_argument('--count', type=int, default=8)
    p = sub.add_parser('scan')
    for key in ('start', 'end', 'core-end'):
        p.add_argument('--' + key, type=float, required=True)
    p.add_argument('--index', type=int, required=True)
    p = sub.add_parser('render')
    p.add_argument('--count', type=int, default=8)
    args = parser.parse_args()
    try:
        {'plan': plan, 'scan': scan, 'render': render}[args.command](args)
    except Exception:
        # Suppress underlying signed media URLs and verbose provider internals in Actions logs.
        print('Job failed: source access, timing, dependency or rendering error. No access restrictions were bypassed. Try an accessible, authorized completed VOD; see README troubleshooting.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()

