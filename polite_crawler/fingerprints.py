"""Exact and near-duplicate page detection (pure Python, no numpy).

Exact: sha256 of the normalised main text. Near: a 64-bit SimHash over 3-word shingles
(Manku et al. 2007); two pages are near-duplicates when their fingerprints differ in at most
3 bits. Such a pair always shares one of four 16-bit bands, so only pages sharing a band
are compared, never all pairs.
"""
import hashlib

MIN_WORDS = 50  # shorter pages differ too little to judge
MAX_DISTANCE = 3
BANDS = 4


def words(text):
    return text.lower().split()


def content_hash(text):
    """sha256 of the text, ignoring case and spacing; None for pages under MIN_WORDS words."""
    tokens = words(text)
    if len(tokens) < MIN_WORDS:
        return None
    return hashlib.sha256(" ".join(tokens).encode("utf-8")).hexdigest()


def simhash(text):
    """64-bit SimHash of the text's 3-word shingles; None for pages under MIN_WORDS words."""
    tokens = words(text)
    if len(tokens) < MIN_WORDS:
        return None
    shingles = {" ".join(tokens[i:i + 3]) for i in range(len(tokens) - 2)}
    hashes = [int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big") for s in shingles]
    half = len(hashes) / 2
    fingerprint = 0
    for bit in range(64):
        if sum((h >> bit) & 1 for h in hashes) > half:
            fingerprint |= 1 << bit
    return fingerprint


class NearDuplicates:
    """The first page seen for each fingerprint, found again through its 16-bit bands."""

    def __init__(self):
        self.bands = [{} for _ in range(BANDS)]

    def band_keys(self, fingerprint):
        return [(fingerprint >> (16 * i)) & 0xFFFF for i in range(BANDS)]

    def find(self, fingerprint):
        """URL of an earlier page within MAX_DISTANCE bits of this fingerprint, or None."""
        for band, key in zip(self.bands, self.band_keys(fingerprint)):
            for other, url in band.get(key, ()):
                if (fingerprint ^ other).bit_count() <= MAX_DISTANCE:
                    return url
        return None

    def add(self, fingerprint, url):
        for band, key in zip(self.bands, self.band_keys(fingerprint)):
            band.setdefault(key, []).append((fingerprint, url))
