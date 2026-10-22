"""Free academic sources (decision D4): arXiv, Crossref, OpenAlex,
Semantic Scholar, PubMed.

Each adapter is split into `fetch` (network, via `HttpClient`) and a pure
`parse_*` function, so parsing is unit-tested on recorded payloads and the
network path is exercised only by `live` tests and real missions.

Every adapter returns *normalized records* (plain dicts):

    provider, external_id, doi, title, authors, year, venue, url,
    source_type, abstract, is_retracted, citation_count, referenced

Nothing here invents data: a field the provider did not return stays None
/ empty. Records without a title are dropped.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import httpx

from ..storage.objects import ObjectStore

USER_AGENT = "AvishkarScientistOS/1.0 (research assistant; mailto:{email})"

# polite per-host spacing (seconds between requests)
HOST_SPACING = {
    "export.arxiv.org": 3.0,
    "api.semanticscholar.org": 1.1,
    "eutils.ncbi.nlm.nih.gov": 0.4,
    "api.crossref.org": 0.2,
    "api.openalex.org": 0.15,
}
CACHE_TTL_S = 7 * 24 * 3600


class HttpClient:
    """GET with an http_cache table (bodies in the object store) and
    per-host spacing. Thread-safe; one instance per process is enough."""

    def __init__(self, db=None, objects: Optional[ObjectStore] = None, email: str = "research@tryvanta.in"):
        self.db = db
        self.objects = objects
        self.ua = USER_AGENT.format(email=email)
        self._last: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _space(self, host: str) -> None:
        gap = HOST_SPACING.get(host, 0.2)
        with self._lock:
            now = time.monotonic()
            wait = self._last.get(host, 0.0) + gap - now
            self._last[host] = max(now, self._last.get(host, 0.0) + gap)
        if wait > 0:
            time.sleep(wait)

    def get(self, url: str, *, timeout_s: float = 30.0, headers: Optional[dict] = None) -> str:
        key = hashlib.sha256(url.encode()).hexdigest()
        if self.db is not None and self.objects is not None:
            row = self.db.one("SELECT status, body_sha256, extract(epoch from now()-fetched_at) AS age "
                              "FROM http_cache WHERE key=%s", (key,))
            if row and row["status"] == 200 and row["age"] < CACHE_TTL_S and self.objects.exists(row["body_sha256"]):
                return self.objects.get_text(row["body_sha256"])
        host = urllib.parse.urlparse(url).hostname or ""
        h = {"User-Agent": self.ua, "Accept": "*/*"}
        h.update(headers or {})
        last_exc = None
        for attempt in range(3):
            self._space(host)
            try:
                r = httpx.get(url, headers=h, timeout=timeout_s, follow_redirects=True)
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                last_exc = RuntimeError(f"HTTP {r.status_code} from {host}")
                time.sleep(min(10.0, float(r.headers.get("Retry-After", 0) or 0) or 2.0 * (attempt + 1)))
                continue
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code} from {host}")
            body = r.text
            if self.db is not None and self.objects is not None:
                digest = self.objects.put(body)
                self.db.run("INSERT INTO http_cache(key, url, status, body_sha256) VALUES (%s,%s,%s,%s) "
                            "ON CONFLICT (key) DO UPDATE SET status=EXCLUDED.status, body_sha256=EXCLUDED.body_sha256, "
                            "fetched_at=now()", (key, url[:2000], 200, digest))
            return body
        raise RuntimeError(f"{host} unavailable after retries: {last_exc}")


# -- helpers ---------------------------------------------------------------
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()


def norm_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    d = doi.strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "https://dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d or None


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def lineage_root(rec: dict) -> str:
    """Cross-provider identity: DOI when known, else the normalized title.
    The same paper found on arXiv and Crossref collapses to one source."""
    d = norm_doi(rec.get("doi"))
    if d and not d.startswith("10.48550/arxiv."):
        return "doi:" + d
    return "t:" + norm_title(rec.get("title", ""))[:200]


def quality_of(rec: dict) -> float:
    """Prior on source reliability. Deliberately coarse; documented in the
    report. Retracted work is near zero regardless of venue."""
    if rec.get("is_retracted"):
        return 0.05
    base = {"journal": 0.75, "conference": 0.70, "book": 0.60, "preprint": 0.55,
            "dataset": 0.60}.get(rec.get("source_type") or "unknown", 0.45)
    c = rec.get("citation_count") or 0
    boost = 0.0
    if c >= 500:
        boost = 0.12
    elif c >= 100:
        boost = 0.08
    elif c >= 20:
        boost = 0.04
    return round(min(0.95, base + boost), 3)


def _rec(**kw) -> dict:
    base = dict(provider=None, external_id=None, doi=None, title="", authors=[], year=None, venue=None,
                url=None, source_type="unknown", abstract="", is_retracted=False, citation_count=None,
                referenced=[])
    base.update(kw)
    base["title"] = clean(base["title"])
    base["abstract"] = clean(base["abstract"])
    base["doi"] = norm_doi(base["doi"])
    return base


# -- arXiv -----------------------------------------------------------------
_ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def parse_arxiv(xml_text: str) -> List[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for e in root.findall("a:entry", _ATOM):
        title = e.findtext("a:title", "", _ATOM)
        if not title.strip() or title.strip().lower() == "error":
            continue
        aid = (e.findtext("a:id", "", _ATOM) or "").rsplit("/abs/", 1)[-1]
        pub = e.findtext("a:published", "", _ATOM)
        doi = e.findtext("arxiv:doi", None, _ATOM)
        jref = e.findtext("arxiv:journal_ref", None, _ATOM)
        out.append(_rec(
            provider="arxiv", external_id=aid, doi=doi or (f"10.48550/arXiv.{aid.split('v')[0]}" if aid else None),
            title=title, authors=[clean(a.findtext("a:name", "", _ATOM)) for a in e.findall("a:author", _ATOM)],
            year=int(pub[:4]) if pub[:4].isdigit() else None, venue=jref or "arXiv",
            url=f"https://arxiv.org/abs/{aid}" if aid else None,
            source_type="journal" if (doi and jref) else "preprint",
            abstract=e.findtext("a:summary", "", _ATOM)))
    return out


def search_arxiv(http: HttpClient, query: str, limit: int = 8, timeout_s: float = 30.0) -> List[dict]:
    q = urllib.parse.quote(f"all:{query}")
    url = f"https://export.arxiv.org/api/query?search_query={q}&start=0&max_results={int(limit)}&sortBy=relevance"
    return parse_arxiv(http.get(url, timeout_s=timeout_s))


# -- Crossref --------------------------------------------------------------
_CR_TYPES = {"journal-article": "journal", "proceedings-article": "conference", "posted-content": "preprint",
             "book-chapter": "book", "book": "book", "monograph": "book", "dataset": "dataset"}


def parse_crossref(payload: str) -> List[dict]:
    data = json.loads(payload)
    out = []
    for it in (data.get("message") or {}).get("items", []):
        title = (it.get("title") or [""])[0]
        if not title:
            continue
        year = None
        for k in ("published-print", "published-online", "issued", "created"):
            parts = ((it.get(k) or {}).get("date-parts") or [[None]])[0]
            if parts and parts[0]:
                year = int(parts[0])
                break
        retracted = title.upper().startswith("RETRACTED") or any(
            (u.get("type") or "").lower() == "retraction" for u in it.get("update-to", []) or [])
        out.append(_rec(
            provider="crossref", external_id=it.get("DOI"), doi=it.get("DOI"), title=title,
            authors=[clean(f"{a.get('given', '')} {a.get('family', '')}") for a in it.get("author", []) or []],
            year=year, venue=(it.get("container-title") or [None])[0], url=it.get("URL"),
            source_type=_CR_TYPES.get(it.get("type", ""), "unknown"), abstract=it.get("abstract") or "",
            is_retracted=retracted, citation_count=it.get("is-referenced-by-count")))
    return out


def search_crossref(http: HttpClient, query: str, limit: int = 8, timeout_s: float = 30.0, email: str = "") -> List[dict]:
    params = {"query.bibliographic": query, "rows": int(limit),
              "select": "DOI,title,author,issued,published-print,published-online,created,container-title,URL,"
                        "type,abstract,is-referenced-by-count,update-to"}
    if email:
        params["mailto"] = email
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    return parse_crossref(http.get(url, timeout_s=timeout_s))


# -- OpenAlex --------------------------------------------------------------
def _uninvert(idx: Optional[dict]) -> str:
    if not idx:
        return ""
    pos = {}
    for word, places in idx.items():
        for p in places:
            pos[p] = word
    return " ".join(pos[i] for i in sorted(pos))


def parse_openalex(payload: str) -> List[dict]:
    data = json.loads(payload)
    out = []
    for w in data.get("results", []):
        title = w.get("title") or w.get("display_name")
        if not title:
            continue
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        wtype = (w.get("type") or "").lower()
        stype = src.get("type") or ""
        if wtype == "preprint" or stype == "repository":
            st = "preprint"
        elif stype == "conference":
            st = "conference"
        elif wtype in ("book", "book-chapter"):
            st = "book"
        elif wtype == "dataset":
            st = "dataset"
        elif stype == "journal" or wtype == "article":
            st = "journal"
        else:
            st = "unknown"
        out.append(_rec(
            provider="openalex", external_id=(w.get("id") or "").rsplit("/", 1)[-1], doi=w.get("doi"),
            title=title, authors=[clean((a.get("author") or {}).get("display_name")) for a in w.get("authorships", [])],
            year=w.get("publication_year"), venue=src.get("display_name"),
            url=w.get("doi") or loc.get("landing_page_url") or w.get("id"), source_type=st,
            abstract=_uninvert(w.get("abstract_inverted_index")), is_retracted=bool(w.get("is_retracted")),
            citation_count=w.get("cited_by_count"),
            referenced=[r.rsplit("/", 1)[-1] for r in (w.get("referenced_works") or [])][:200]))
    return out


def search_openalex(http: HttpClient, query: str, limit: int = 8, timeout_s: float = 30.0, email: str = "") -> List[dict]:
    params = {"search": query, "per-page": int(limit)}
    if email:
        params["mailto"] = email
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    return parse_openalex(http.get(url, timeout_s=timeout_s))


# -- Semantic Scholar --------------------------------------------------------
def parse_semantic_scholar(payload: str) -> List[dict]:
    data = json.loads(payload)
    out = []
    for p in data.get("data", []) or []:
        if not p.get("title"):
            continue
        ext = p.get("externalIds") or {}
        types = [t.lower() for t in (p.get("publicationTypes") or [])]
        if "journalarticle" in types:
            st = "journal"
        elif "conference" in types:
            st = "conference"
        elif "book" in types or "booksection" in types:
            st = "book"
        elif "dataset" in types:
            st = "dataset"
        elif ext.get("ArXiv"):
            st = "preprint"
        else:
            st = "unknown"
        out.append(_rec(
            provider="semantic_scholar", external_id=p.get("paperId"), doi=ext.get("DOI"), title=p["title"],
            authors=[clean(a.get("name")) for a in p.get("authors") or []], year=p.get("year"),
            venue=p.get("venue") or None, url=p.get("url"), source_type=st, abstract=p.get("abstract") or "",
            citation_count=p.get("citationCount")))
    return out


def search_semantic_scholar(http: HttpClient, query: str, limit: int = 8, timeout_s: float = 30.0) -> List[dict]:
    params = {"query": query, "limit": int(limit),
              "fields": "title,abstract,year,venue,externalIds,authors,citationCount,publicationTypes,url"}
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
    return parse_semantic_scholar(http.get(url, timeout_s=timeout_s))


# -- PubMed ------------------------------------------------------------------
def parse_pubmed(xml_text: str) -> List[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for art in root.findall(".//PubmedArticle"):
        mc = art.find("MedlineCitation")
        if mc is None:
            continue
        a = mc.find("Article")
        if a is None:
            continue
        title = "".join(a.find("ArticleTitle").itertext()) if a.find("ArticleTitle") is not None else ""
        if not title:
            continue
        abstract = " ".join("".join(x.itertext()) for x in a.findall("Abstract/AbstractText"))
        year = a.findtext("Journal/JournalIssue/PubDate/Year") or (a.findtext("Journal/JournalIssue/PubDate/MedlineDate") or "")[:4]
        doi = None
        for el in a.findall("ELocationID"):
            if el.get("EIdType") == "doi":
                doi = el.text
        if not doi:
            for el in art.findall("PubmedData/ArticleIdList/ArticleId"):
                if el.get("IdType") == "doi":
                    doi = el.text
        ptypes = [(p.text or "").lower() for p in a.findall("PublicationTypeList/PublicationType")]
        pmid = mc.findtext("PMID")
        authors = []
        for au in a.findall("AuthorList/Author"):
            nm = clean(f"{au.findtext('ForeName') or ''} {au.findtext('LastName') or ''}") or clean(au.findtext("CollectiveName"))
            if nm:
                authors.append(nm)
        out.append(_rec(
            provider="pubmed", external_id=pmid, doi=doi, title=title, authors=authors,
            year=int(year) if str(year).isdigit() else None, venue=a.findtext("Journal/Title"),
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
            source_type="preprint" if "preprint" in ptypes else "journal", abstract=abstract,
            is_retracted=("retracted publication" in ptypes)))
    return out


def search_pubmed(http: HttpClient, query: str, limit: int = 8, timeout_s: float = 30.0, email: str = "") -> List[dict]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    extra = {"tool": "avishkar-scientist"}
    if email:
        extra["email"] = email
    es = json.loads(http.get(base + "esearch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "term": query, "retmax": int(limit), "retmode": "json", "sort": "relevance", **extra}),
        timeout_s=timeout_s))
    ids = (es.get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return []
    xml_text = http.get(base + "efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "id": ",".join(ids), "retmode": "xml", **extra}), timeout_s=timeout_s)
    return parse_pubmed(xml_text)


PROVIDERS = ("openalex", "arxiv", "crossref", "semantic_scholar", "pubmed")

# question words that make PubMed worth asking (it is biomedical-only)
_BIO = re.compile(r"\b(cell|gene|protein|clinical|patient|disease|drug|cancer|virus|bacteri|neuro|brain|"
                  r"medic|health|biolog|enzyme|dna|rna|tissue|immune|therapy|vaccine|metabol)", re.I)


def providers_for(question: str) -> tuple:
    """PubMed only for biomedical questions -- it would add noise otherwise."""
    return PROVIDERS if _BIO.search(question or "") else tuple(p for p in PROVIDERS if p != "pubmed")
