"""Audit only the explicit public source set; never print a detected secret."""
import argparse
import hashlib
import re
import subprocess
from pathlib import Path
from public_files import PUBLIC_FILES, public_files

PATTERNS = [r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----',
            r'\b(?:ghp_|gho_|github_pat_)[A-Za-z0-9_]{20,}', r'\bsk-[A-Za-z0-9_-]{30,}',
            r'/Users/[a-zA-Z0-9_-]+/', r'/home/[a-zA-Z0-9_-]+/',
            r'\btail[0-9a-f]{6}\.ts\.net\b']

# README images, reviewed by hand: a demo vault with fictional notes and a simulated Kobo.
# Any change to an image changes its hash and requires a new review.
REVIEWED_IMAGES = {
    'docs/imagenes/apertura-90s.jpg': 'f3317b075a2f15e43ed374aa2518c4f8b74ea94175ab6b02980e42dcb6167e95',
    'docs/imagenes/biblioteca.png': '8380a03028e335d193663fb06f985a44d6014e148d31eab406af30f61d937840',
    'docs/imagenes/estilo.png': '7cb42a5211d1f0e91ba0d9a3e73dba83212c0f128b59bba0b08e055464cc86e5',
    'docs/imagenes/kobo.png': 'afa6822c9328d8b5613a3d9fd9b4735e33dfc48e68fa7202c9aa055bccd271ce',
    'docs/imagenes/portada-90s.jpg': '482a6eaf80466f174a4586599ce1ff1561dc791384eb12bdd83ac5e2cdcd9a16',
    'docs/imagenes/preparar.png': 'fb98ff22f5d4eabbaf8b29d11c6ec142565dc2309987738f1da751bc2a369d43',
    'docs/imagenes/subrayados.png': '7c7d345e93155ce12e97bb0d5b1fe61e5c6d688da8c435be9cc2d18e904ef89b',
}


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
            name = path.relative_to(root).as_posix()
            if REVIEWED_IMAGES.get(name) != hashlib.sha256(path.read_bytes()).hexdigest():
                findings.append((name, 'public images need explicit review'))
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
