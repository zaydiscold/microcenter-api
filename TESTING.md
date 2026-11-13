# Testing

Run `pytest` from the repository root after `pip install -e '.[api,dev]'`.
The test suite performs no live network operations and needs no browser installation.
Build validation: `python -m build`.

Live scans must be explicitly requested, sequential and paced. Use `--checkpoint` so a block or interruption preserves completed pages. Do not mark an incomplete or duplicate-truncated scan complete. Full catalog scans capture changing inventory over time; include count drift warnings and observation windows.
