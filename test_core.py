import unittest
from core import validate_source, plan_chunks, select_candidates, subtitles, make_candidates


class CoreTests(unittest.TestCase):
    def test_source_access_boundary(self):
        self.assertEqual(validate_source('https://www.youtube.com/live/qSyo5d-dVzA'),
                         'https://www.youtube.com/live/qSyo5d-dVzA')
        for url in ['http://youtube.com/watch?v=qSyo5d-dVzA', 'https://youtube.com.evil.org/watch?v=qSyo5d-dVzA',
                    'https://localhost/video', 'https://youtube.com:443/watch?v=qSyo5d-dVzA',
                    'https://user@youtube.com/watch?v=qSyo5d-dVzA', 'https://youtube.com/playlist?list=abc',
                    'https://twitch.tv/creator']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_source(url)

    def test_full_day_is_bounded_and_last_chunk_clamped(self):
        chunks = plan_chunks(85542, 0, 1440, 8)
        self.assertEqual(len(chunks), 48)
        self.assertEqual(chunks[-1]['end'], 85542)
        self.assertEqual(chunks[0]['core_end'], 1800)
        self.assertEqual(chunks[0]['end'], 1840)
        for start, minutes in [(float('nan'), 60), (0, 1441), (-1, 60), (85540, 60)]:
            with self.assertRaises(ValueError):
                plan_chunks(85542, start, minutes, 8)

    def test_no_overlapping_or_near_duplicate_clips(self):
        candidates = [dict(start=0, end=35, score=1, transcript='a unique funny reaction'),
                      dict(start=10, end=45, score=.8, transcript='different dialogue'),
                      dict(start=60, end=95, score=.7, transcript='a unique funny reaction'),
                      dict(start=120, end=155, score=.6, transcript='another completely separate moment')]
        self.assertEqual([c['start'] for c in select_candidates(candidates, 8)], [0, 120])

    def test_subtitles_are_relative_clamped_and_plain_text(self):
        words = [dict(start=99.8, end=100.5, word='<b>Hey</b>'), dict(start=100.6, end=102, word='there'),
                 dict(start=102.1, end=105, word='friend')]
        srt = subtitles(words, 100, 103)
        self.assertIn('00:00:00,000 --> 00:00:00,500', srt)
        self.assertIn('00:00:02,100 --> 00:00:03,000', srt)
        self.assertNotIn('<b>', srt)

    def test_silent_audio_yields_no_fabricated_candidates(self):
        self.assertEqual(make_candidates([], [0]*60, 0, 60, 60), [])


if __name__ == '__main__':
    unittest.main()

