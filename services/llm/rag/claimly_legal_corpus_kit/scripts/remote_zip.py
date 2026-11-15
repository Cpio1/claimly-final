# -*- coding: utf-8 -*-
"""Read single members of a very large ZIP on a web server without downloading the whole file
(HTTP Range requests). Used for California's official bulk file pubinfo_2025.zip (1.3 GB)."""
import io, urllib.request, zipfile, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_common import USER_AGENT, _ssl_context

BLOCK = 4 * 1024 * 1024


class HttpRangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos, self.blocks, self.ctx, self.block = url, 0, {}, _ssl_context(), BLOCK
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120, context=self.ctx) as r:
            self.size = int(r.headers["Content-Length"])
        self.bytes_fetched = 0

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def _block(self, n):
        if n not in self.blocks:
            a, b = n * self.block, min(self.size, (n + 1) * self.block) - 1
            req = urllib.request.Request(self.url, headers={"User-Agent": USER_AGENT, "Range": f"bytes={a}-{b}"})
            with urllib.request.urlopen(req, timeout=300, context=self.ctx) as r:
                if r.status != 206:
                    raise RuntimeError("server ignored the Range header")
                data = r.read()
            self.bytes_fetched += len(data)
            if len(self.blocks) > 24:
                self.blocks.pop(next(iter(self.blocks)))
            self.blocks[n] = data
        return self.blocks[n]

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        out = bytearray()
        while n > 0 and self.pos < self.size:
            blk = self._block(self.pos // self.block)
            off = self.pos % self.block
            part = blk[off:off + n]
            out += part
            self.pos += len(part)
            n -= len(part)
        return bytes(out)

    def set_block(self, size):
        """Smaller blocks for picking many small members scattered over the archive."""
        self.block, self.blocks = size, {}

    def readinto(self, b):
        d = self.read(len(b)); b[:len(d)] = d; return len(d)


def open_remote_zip(url):
    f = HttpRangeFile(url)
    return zipfile.ZipFile(f), f          # no extra buffering: the block cache above is the buffer
