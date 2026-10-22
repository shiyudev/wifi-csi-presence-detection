"""Cloud/local Python reader for the exported JSONL. No training or upload occurs."""
import json
from pathlib import Path

def load_session(filename):
    metadata = None
    frames, events = [], []
    summary = None
    with Path(filename).open(encoding='utf-8') as source:
        for line in source:
            row = json.loads(line)
            if row['type'] == 'metadata': metadata = row
            elif row['type'] == 'csi': frames.append(row)
            elif row['type'] == 'event': events.append(row)
            elif row['type'] == 'summary': summary = row
    if metadata is None or summary is None:
        raise ValueError('Incomplete file: missing metadata or summary')
    if summary['saved_records'] != len(frames):
        raise ValueError('Record count mismatch')
    return metadata, frames, events, summary

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python load_for_training.py CSI_file.jsonl')
    metadata, frames, events, summary = load_session(sys.argv[1])
    print('Session:', metadata['session_id'])
    print('Frames:', len(frames), 'Events:', len(events), 'Status:', summary['status'])
    print('Labels verified:', metadata.get('label_verified', False))
