"""Per-title episode bookmarks in the local profile, without playback grants."""
import json
import math
import re
import threading
import time
from pathlib import Path


class Progress:
    def __init__(self, root):
        self.file = Path(root) / 'work/library/progress.json'
        self.lock = threading.RLock()

    def read(self):
        if not self.file.exists():
            return {}
        if self.file.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('Progress file exceeds limit')
        data = json.loads(self.file.read_text(encoding='utf8'))
        if data.get('version') != 1 or not isinstance(data.get('items'), dict):
            raise ValueError('Unsupported progress file')
        return data['items']

    def get(self, identifier):
        if not re.fullmatch(r'[a-f0-9]{20}', identifier):
            raise ValueError('Invalid title')
        with self.lock:
            return {'progress': self.read().get(identifier), 'storage': 'local_profile'}

    def save(self, data):
        identifier = data.get('id', '')
        episode = data.get('episode')
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{20}', identifier):
            raise ValueError('Invalid title')
        if not isinstance(episode, str) or not re.fullmatch(r'[0-9]{1,6}', episode):
            raise ValueError('Invalid episode')
        position, duration = data.get('position'), data.get('duration')
        for number in (position, duration):
            if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 604800:
                raise ValueError('Invalid timestamp')
        if duration and position > duration + 1:
            raise ValueError('Position exceeds duration')
        with self.lock:
            items = self.read()
            entry = items.setdefault(identifier, {'last_episode': episode, 'episodes': {}})
            entry['last_episode'] = episode
            entry['updated_unix'] = time.time()
            entry['episodes'][episode] = {'position': position, 'duration': duration,
                                         'completed': data.get('completed') is True}
            # Bound storage while retaining the most recently used titles/episodes.
            while len(entry['episodes']) > 500:
                del entry['episodes'][next(iter(entry['episodes']))]
            items = dict(sorted(items.items(), key=lambda row: row[1]['updated_unix'], reverse=True)[:1000])
            self.file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.file.with_suffix('.tmp')
            temporary.write_text(json.dumps({'version': 1, 'items': items}), encoding='utf8')
            temporary.replace(self.file)
            return {'progress': entry, 'storage': 'local_profile'}
