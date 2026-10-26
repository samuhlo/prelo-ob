"""Fetch the pinned EPUBCheck distribution into the ignored validation directory."""
import hashlib
import io
import time
import urllib.request
import zipfile
from pathlib import Path

URL = 'https://github.com/w3c/epubcheck/releases/download/v5.4.0/epubcheck-5.4.0.zip'
SHA256 = '33350c61038e71dfb3d45a76aed04bf5481e6d5500cb780f6e98db8bbd15a28c'


def main():
    data=bytearray();deadline=time.monotonic()+90
    with urllib.request.urlopen(URL,timeout=30) as response:
        while chunk:=response.read(1024*1024):
            data.extend(chunk)
            if len(data)>100_000_000 or time.monotonic()>deadline:raise ValueError('EPUBCheck download exceeded its limit.')
    if hashlib.sha256(data).hexdigest()!=SHA256:raise ValueError('EPUBCheck checksum mismatch.')
    target=Path(__file__).resolve().parents[1]/'data/validation';target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:archive.extractall(target)
    if not (target/'epubcheck-5.4.0/epubcheck.jar').is_file():raise ValueError('Unexpected EPUBCheck distribution.')
    print('Pinned EPUBCheck distribution verified.')


if __name__=='__main__':main()
