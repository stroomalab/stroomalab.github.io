import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path

ORCID = "0000-0001-7898-1599"  # <-- cámbialo si quieres el del PI/lab
OUT_FRAGMENT = Path("generated/publications_journal.html")
PUBS_HTML = Path("publications.html")

START = "<!-- AUTO-PUBS:START -->"
END = "<!-- AUTO-PUBS:END -->"

def http_get(url: str, headers=None) -> bytes:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def orcid_works(orcid: str):
    # ORCID public API v3 (sin token, para datos públicos)
    url = f"https://pub.orcid.org/v3.0/{orcid}/works"
    data = http_get(url, headers={"Accept": "application/json"})
    j = json.loads(data.decode("utf-8"))
    groups = j.get("group", [])
    put_codes = []
    for g in groups:
        summaries = g.get("work-summary", [])
        for s in summaries:
            pc = s.get("put-code")
            if pc is not None:
                put_codes.append(pc)
    return put_codes

def orcid_work_detail(orcid: str, put_code: int):
    url = f"https://pub.orcid.org/v3.0/{orcid}/work/{put_code}"
    data = http_get(url, headers={"Accept": "application/json"})
    return json.loads(data.decode("utf-8"))

def pick_best_doi(ext_ids):
    if not ext_ids:
        return None
    for eid in ext_ids.get("external-id", []):
        if (eid.get("external-id-type") or "").lower() == "doi":
            return clean((eid.get("external-id-value") or ""))
    return None

def pick_best_pmid(ext_ids):
    if not ext_ids:
        return None
    for eid in ext_ids.get("external-id", []):
        if (eid.get("external-id-type") or "").lower() == "pmid":
            return clean((eid.get("external-id-value") or ""))
    return None

def format_authors(contributors):
    if not contributors:
        return ""
    names = []
    for c in contributors.get("contributor", []):
        credit = c.get("credit-name", {}) or {}
        nm = clean(credit.get("value", ""))
        if nm:
            names.append(nm)
    # ORCID a veces no trae lista completa; si está vacío, lo dejamos sin autores
    return ", ".join(names)

def build_html(items):
    # items: list of dict with year, title, journal, doi, pmid, url
    by_year = {}
    for it in items:
        by_year.setdefault(it["year"], []).append(it)

    years = sorted(by_year.keys(), reverse=True)

    parts = []
    for y in years:
        parts.append(f'<div class="pub-year-group" id="y{y}">')
        parts.append(f'  <h3 class="pub-year">{y}</h3>')
        parts.append('  <ol class="list">')
        for it in sorted(by_year[y], key=lambda x: x.get("date", ""), reverse=True):
            authors = it.get("authors", "")
            title = it.get("title", "")
            journal = it.get("journal", "")
            doi = it.get("doi")
            pmid = it.get("pmid")

            links = []
            if doi:
                links.append(f'<a href="https://doi.org/{doi}" target="_blank" rel="noopener">DOI</a>')
            if pmid:
                links.append(f'<a href="https://pubmed.ncbi.nlm.nih.gov/{pmid}/" target="_blank" rel="noopener">PubMed</a>')

            links_html = f'<span class="pub-links">{" ".join(links)}</span>' if links else ""

            # Mantiene tu estilo: autores + título en italic + journal
            parts.append("    <li>")
            if authors:
                parts.append(f"      {authors}.")
            parts.append(f"      <em>{title}</em>")
            if journal:
                parts.append(f"      {journal}.")
            parts.append(f"      {links_html}")
            parts.append("    </li>")
        parts.append("  </ol>")
        parts.append("</div>")

    return "\n".join(parts)

def main():
    put_codes = orcid_works(ORCID)

    items = []
    for pc in put_codes:
        w = orcid_work_detail(ORCID, pc)

        work_type = (w.get("type") or "").lower()
        # Filtramos para "journal-article" y similares (puedes ajustar)
        if work_type not in ("journal-article", "journal_article", "journal-article "):
            # Mucha gente prefiere incluir "conference-paper"; ajusta si quieres
            pass

        title = clean(((w.get("title") or {}).get("title") or {}).get("value", ""))
        journal = clean((w.get("journal-title") or {}).get("value", ""))
        pub_date = w.get("publication-date") or {}
        year = (pub_date.get("year") or {}).get("value")
        month = (pub_date.get("month") or {}).get("value") or "01"
        day = (pub_date.get("day") or {}).get("value") or "01"

        if not year:
            # Si falta año, lo mandamos a "Undated"
            year = "Undated"

        ext_ids = w.get("external-ids") or {}
        doi = pick_best_doi(ext_ids)
        pmid = pick_best_pmid(ext_ids)

        authors = format_authors(w.get("contributors") or {})

        date_key = f"{year}-{month}-{day}" if year != "Undated" else "0000-01-01"

        items.append({
            "year": year,
            "title": title,
            "journal": journal,
            "doi": doi,
            "pmid": pmid,
            "authors": authors,
            "date": date_key,
        })

    # Solo años numéricos arriba, "Undated" al final
    def year_sort_key(y):
        return -int(y) if str(y).isdigit() else 999999

    # Generar HTML fragment
    html = build_html(items)

    OUT_FRAGMENT.parent.mkdir(parents=True, exist_ok=True)
    OUT_FRAGMENT.write_text(html, encoding="utf-8")

    # Insertar en publications.html
    src = PUBS_HTML.read_text(encoding="utf-8")
    if START not in src or END not in src:
        raise SystemExit("No encuentro los marcadores AUTO-PUBS en publications.html")

    before, rest = src.split(START, 1)
    _, after = rest.split(END, 1)

    merged = before + START + "\n" + html + "\n" + END + after
    PUBS_HTML.write_text(merged, encoding="utf-8")

    print("OK: publications.html actualizado desde ORCID")

if __name__ == "__main__":
    main()