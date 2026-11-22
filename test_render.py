import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import pipeline


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and ffprobe required')
class RenderTests(unittest.TestCase):
    def test_real_captioned_mp4_and_review_gallery(self):
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp)
                media = Path('fixture/source.mp4')
                media.parent.mkdir()
                # Test fixture only, never a user-facing deliverable or source clip.
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                                'testsrc2=size=640x360:rate=30', '-f', 'lavfi', '-i',
                                'sine=frequency=440:sample_rate=48000', '-t', '2',
                                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(media)], check=True)
                pipeline.write_json('candidates/candidates-0.json', [dict(start=100, end=102,
                    score=.9, transcript='Wait what happened', words=[
                        dict(start=100, end=100.6, word='Wait'),
                        dict(start=100.7, end=101.2, word='what'),
                        dict(start=101.3, end=102, word='happened')])])
                with patch.object(pipeline, 'checked_url', return_value='https://youtu.be/qSyo5d-dVzA'), \
                     patch.object(pipeline, 'download', return_value=media):
                    pipeline.render(argparse.Namespace(count=1))
                self.assertTrue(Path('output/clip-01.mp4').is_file())
                self.assertTrue(Path('output/clip-01.jpg').is_file())
                self.assertIn('clip-01.mp4', Path('output/review.html').read_text())
                manifest = pipeline.read_json('output/manifest.json')
                self.assertEqual(manifest['produced'], 1)
                self.assertIn('00:00:00,000', Path('output/clip-01.srt').read_text())
            finally:
                os.chdir(old)

