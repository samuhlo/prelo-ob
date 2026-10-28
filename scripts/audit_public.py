"""Audit only the explicit public source set; never print a detected secret."""
import argparse
import re
import subprocess
from pathlib import Path
from public_files import PUBLIC_FILES, public_files

PATTERNS = [r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----',
            r'\b(?:ghp_|gho_|github_pat_)[A-Za-z0-9_]{20,}', r'\bsk-[A-Za-z0-9_-]{30,}',
            r'/Users/[a-zA-Z0-9_-]+/', r'/home/[a-zA-Z0-9_-]+/',
            r'\btail[0-9a-f]{6}\.ts\.net\b']


def audit(root):
    root = Path(root)
    secrets = []
    env = root / '.env'
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition('=')
            if sep and re.search('TOKEN|KEY|PASSWORD|SECRET', key) and len(value) >= 24:
                secrets.append(value)
    findings = []
    if (root / ".git").exists():
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True,
                                 capture_output=True, text=True, timeout=10).stdout.split("\0")
        findings.extend((name, "tracked file is outside the reviewed publication manifest")
                        for name in tracked if name and name not in PUBLIC_FILES)
    for path in public_files(root):
        if path.suffix in {'.png', '.jpg', '.webp'}:
            findings.append((path.relative_to(root).as_posix(), 'public images need explicit review'))
            continue
        text = path.read_text(encoding="utf-8-sig")
        # The audit's own rules deliberately mention prohibited patterns.
        patterns = [] if path.name == 'audit_public.py' else PATTERNS
        if any(re.search(pattern, text) for pattern in patterns) or any(value in text for value in secrets):
            findings.append((path.relative_to(root).as_posix(), 'private material detected'))
    return findings


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    findings = audit(args.root)
    for path, reason in findings:
        print(path + ': ' + reason)
    if findings:
        raise SystemExit(1)
    print('Public source audit passed; local files and history are excluded.')
