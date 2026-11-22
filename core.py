"""Dependency-free selection, validation and subtitle helpers."""
import ipaddress
import math
import re
import socket
from urllib.parse import urlparse, parse_qs

HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be',
         'twitch.tv', 'www.twitch.tv'}


def validate_source(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password or p.port:
        raise ValueError('Use an HTTPS YouTube video/live or Twitch VOD URL, without credentials or a port.')
    if p.fragment:
        raise ValueError('Remove the URL fragment.')
    if p.hostname == 'youtu.be':
        valid = bool(re.fullmatch(r'/[A-Za-z0-9_-]{11}', p.path))
    elif 'youtube' in p.hostname:
        valid = bool(re.fullmatch(r'/(live|shorts)/[A-Za-z0-9_-]{11}/?', p.path))
        valid = valid or (p.path == '/watch' and
                         bool(re.fullmatch(r'[A-Za-z0-9_-]{11}', parse_qs(p.query).get('v', [''])[0])))
    else:
        valid = bool(re.fullmatch(r'/videos/[0-9]+/?', p.path))
    if not valid:
        raise ValueError('Use a single video/VOD link, not a channel, playlist or active Twitch channel.')
    return url


def reject_private_dns(url):
    for result in socket.getaddrinfo(urlparse(url).hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(result[4][0]).is_global:
            raise ValueError('Source hostname must resolve to public addresses.')


def plan_chunks(duration, start, minutes, count):
    if not all(math.isfinite(x) for x in (duration, start, minutes)):
        raise ValueError('Time values must be finite.')
    if duration <= 0 or start < 0 or not 1 <= minutes <= 1440 or not 1 <= count <= 10:
        raise ValueError('Use 1–1440 scan minutes, 1–10 clips and a nonnegative start.')
    end = min(duration, start + minutes * 60)
    if end - start < 20:
        raise ValueError('There must be at least 20 seconds after the scan start.')
    # Each worker owns its core interval and reads 40 seconds beyond it.
    return [dict(index=i, start=round(s, 3), end=round(min(end, s + 1840), 3),
                 core_end=round(min(end, s + 1800), 3))
            for i, s in enumerate(_steps(start, end, 1800))]


def _steps(start, end, step):
    while start < end:
        yield start
        start += step


def timecode(seconds):
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def clean_text(text):
    # Text only: prevent subtitle markup injection and unsafe control characters.
    return re.sub(r'\s+', ' ', re.sub(r'[<>\x00-\x1f]', ' ', text)).strip()


REACTIONS = re.compile(r'\b(what|wait|no way|oh my|bro|help|run|crazy|scared|look|stop|why|how|wow)\b', re.I)


def make_candidates(words, energy, offset, duration, core_end):
    """Use speech and relative loudness; this is a heuristic, not a viral score."""
    candidates = []
    if duration < 20:
        return []
    for anchor in range(0, max(1, int(duration) - 19), 5):
        if offset + anchor >= core_end:
            break
        start = max(0, anchor - 4)
        end = min(duration, start + 35)
        selected = [w for w in words if w['end'] > start and w['start'] < end]
        if len(selected) < 5 or end - start < 20:
            continue
        text = ' '.join(w['word'] for w in selected)
        local_energy = energy[int(start):math.ceil(end)]
        loudness = max(local_energy, default=0)
        reaction = min(8, len(REACTIONS.findall(text))) / 8
        density = min(1, len(selected) / (end - start) / 2.5)
        score = round(0.6 * loudness + 0.3 * reaction + 0.1 * density, 4)
        candidates.append(dict(start=round(offset + start, 3), end=round(offset + end, 3),
                               score=score, transcript=clean_text(text),
                               words=[dict(start=round(offset + w['start'], 3),
                                           end=round(offset + w['end'], 3), word=clean_text(w['word']))
                                      for w in selected]))
    return select_candidates(candidates, 12)


def select_candidates(candidates, count):
    chosen = []
    for c in sorted(candidates, key=lambda x: (-x['score'], x['start'])):
        if any(min(c['end'], old['end']) - max(c['start'], old['start']) > -5 for old in chosen):
            continue
        # Avoid repeated transcript content from repeated dialogue or model hallucinations.
        tokens = set(c['transcript'].lower().split())
        if any(len(tokens & set(x['transcript'].lower().split())) /
               max(1, len(tokens | set(x['transcript'].lower().split()))) > .8 for x in chosen):
            continue
        chosen.append(c)
        if len(chosen) >= count:
            break
    return chosen


def subtitles(words, start, end):
    rows = []
    group = []
    def flush():
        if not group:
            return
        a, b = max(0, group[0]['start'] - start), min(end - start, group[-1]['end'] - start)
        if b > a:
            rows.append(f'{len(rows)+1}\n{timecode(a)} --> {timecode(b)}\n' +
                        ' '.join(clean_text(w['word']) for w in group) + '\n')
        group.clear()
    for w in words:
        if w['end'] <= start or w['start'] >= end:
            continue
        if group and (w['end'] - group[0]['start'] > 2 or len(group) >= 6):
            flush()
        group.append(w)
    flush()
    return '\n'.join(rows)
