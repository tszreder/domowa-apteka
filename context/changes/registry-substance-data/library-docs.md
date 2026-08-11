# F-01 `registry-substance-data` — library docs (recommended options)

Reference material, not a plan. Pulled from the CPython source docs via Context7
(`/python/cpython`) on 2026-08-11, for the two stdlib APIs `options.md` recommends
in §5 (Decision B — XML parsing) and §6 (Decision C — fetching). Both are stdlib,
so "up to date" here means "matches the CPython `main` doc source", not a
version-pinned release note.

---

## `xml.etree.ElementTree.iterparse` — options.md §5, B1 (recommended)

```python
xml.etree.ElementTree.iterparse(source, events=None, parser=None)
```

Parses an XML source incrementally and returns an iterator of `(event, elem)`
pairs, instead of building the whole tree in memory like `ET.parse()` (B4,
rejected — ~1 GB+ resident, would OOM on Railway).

- **`source`** — filename or file object. Use the temp file path from Decision C1.
- **`events`** — sequence of event names to report. Default is `("end",)` only;
  pass `events=("start", "end")` if start-tag data is ever needed. F-01's use
  case (read each `produktLeczniczy` and its `substancjaCzynna` children on
  close, then discard) only needs the default `"end"`.
- **`parser`** — optional parser instance; leave default for a trusted
  government HTTPS source (see options.md §5 XXE note — no external entity
  expansion by default on modern CPython).

**The `elem.clear()` idiom is not part of the API surface** — it's a usage
pattern the docs don't show directly, but it's what keeps memory at the
measured 7 MB instead of ~1 GB: call `elem.clear()` on each product element
right after you've read what you need from it, inside the `for event, elem in
iterparse(...)` loop.

**Version notes relevant to this project** (Python 3.11.9 per options.md):
- 3.6+: `iterparse()` runtime improved ~2x.
- **Fixed in 3.11**: a file-descriptor leak when the iterator isn't fully
  exhausted. Only matters if the import command breaks out of the loop early
  (e.g. on the "assert plausible product count" failure path in options.md
  §12 risk 3) — on 3.11.9 that's already fixed, but don't rely on it if the
  minimum supported version ever drops below 3.11.

---

## `urllib.request` — options.md §6, C1 (recommended: stream to temp file)

Two relevant functions. The docs label one of them **legacy** — worth knowing
before picking which one the import command calls.

### `urlopen` — use this one

```python
urllib.request.urlopen(url, data=None, timeout=..., *, cafile=None, capath=None, cadefault=False, context=None)
```

Opens `url` (string or `Request`) and returns a file-like response object
(`.read()`, `.headers`). This is the primitive for options.md's C1 recommendation
("stream to a temp file, then parse — retryable, inspectable"):

```python
import shutil
import urllib.request

with urllib.request.urlopen(url) as response, open(tmp_path, "wb") as f:
    shutil.copyfileobj(response, f)
```

### `urlretrieve` — legacy, avoid for new code

```python
urllib.request.urlretrieve(url, filename=None, reporthook=None, data=None)
```

Copies a URL straight to a local file in one call, with an optional
`reporthook` progress callback. Convenient, but the CPython docs place it under
**"Legacy interface"** — no indication it's deprecated for removal, just not
the recommended path for new code.

**Recommendation for the import command**: use `urlopen()` + `shutil.copyfileobj()`
rather than `urlretrieve()`. Same zero-dependency stdlib cost, but avoids the
legacy-labeled function and hands you a real file/response handle to control
buffering, timeouts, and retries around — which is exactly the "retryable,
inspectable" property options.md §6 C1 is arguing for.

### HTTP 1.1 note (3.6+)

`urllib.request` (and `http.client.HTTPConnection.request`) use chunked
transfer encoding for file-object request bodies when no `Content-Length` is
given. Not relevant to a GET-only download, noted for completeness.

---

## Sources

- `xml.etree.ElementTree.iterparse`: https://github.com/python/cpython/blob/main/Doc/library/xml.etree.elementtree.md
- `urllib.request.urlopen` / `urlretrieve`: https://github.com/python/cpython/blob/main/Doc/library/urllib.request.md
- Fetched via `npx ctx7@latest docs /python/cpython "<query>"` (Context7 CLI) — see `find-docs` skill.
