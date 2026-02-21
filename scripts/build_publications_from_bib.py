from __future__ import annotations
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

from pybtex.database import parse_file

BIB_PATH = Path("data/publications.bib")
HTML_PATH = Path("publications.html")

START = "<!-- AUTO PUBLICATIONS START -->"
END = "<!-- AUTO PUBLICATIONS END -->"


def norm_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("doi:", "").strip()
    return doi


def norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def first_field(entry, names):
    for n in names:
        if n in entry.fields and entry.fields[n].strip():
            return entry.fields[n].strip()
    return ""


def get_authors(entry) -> str:
    persons = entry.persons.get("author", [])
    if not persons:
        return ""
    # "Last, First" -> "First Last"
    out = []
    for p in persons:
        first = " ".join(p.first_names)
        last = " ".join(p.last_names)
        name = (first + " " + last).strip() if (first or last) else str(p)
        out.append(name)
    return ", ".join(out)


def build_items():
    bib = parse_file(str(BIB_PATH))

    # Deduplicación:
    # 1) DOI
    # 2) PMID
    # 3) (título normalizado + año)
    seen = set()

    items = []
    for _, entry in bib.entries.items():
        title = first_field(entry, ["title"])
        year = first_field(entry, ["year"]) or "Unknown"
        journal = first_field(entry, ["journal", "journaltitle", "booktitle"])
        doi = norm_doi(first_field(entry, ["doi"]))
        pmid = first_field(entry, ["pmid"])

        # URL extra (por si quieres link adicional)
        url = first_field(entry, ["url"])

        # key de dedupe
        if doi:
            dedupe_key = ("doi", doi)
        elif pmid:
            dedupe_key = ("pmid", pmid)
        else:
            dedupe_key = ("titleyear", norm_text(title), year)

        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        authors = get_authors(entry)

        # fecha para ordenar (año y si existe month)
        month = first_field(entry, ["month"])
        month = month.zfill(2) if month.isdigit() else "01"
        sort_key = f"{year}-{month}"

        items.append(
            dict(
                year=year,
                sort_key=sort_key,
                authors=authors,
                title=title,
                journal=journal,
                doi=doi,
                pmid=pmid,
                url=url,
            )
        )

    return items


def render_html(items):
    by_year = defaultdict(list)
    for it in items:
        by_year[it["year"]].append(it)

    # Orden: años numéricos desc, luego "Unknown"
    def year_key(y: str):
        return (0, -int(y)) if y.isdigit() else (1, 0)

    html_parts = []
    for year in sorted(by_year.keys(), key=year_key):
        group = sorted(by_year[year], key=lambda x: x["sort_key"], reverse=True)

        html_parts.append(f'<div class="pub-year-group" id="y{year}">')
        html_parts.append(f'  <h3 class="pub-year">{year}</h3>')
        html_parts.append('  <ol class="list">')

        for p in group:
            links = []
            if p["doi"]:
                links.append(f'<a href="https://doi.org/{p["doi"]}" target="_blank" rel="noopener">DOI</a>')
            if p["pmid"]:
                links.append(f'<a href="https://pubmed.ncbi.nlm.nih.gov/{p["pmid"]}/" target="_blank" rel="noopener">PubMed</a>')
            # Si quieres mostrar URL adicional (eLife reviewed-preprints, etc.)
            if p["url"]:
                links.append(f'<a href="{p["url"]}" target="_blank" rel="noopener">Journal</a>')

            links_html = f'<span class="pub-links">{" ".join(links)}</span>' if links else ""

            html_parts.append("    <li>")
            if p["authors"]:
                html_parts.append(f"      {p['authors']}.")
            if p["title"]:
                html_parts.append(f"      <em>{p['title']}</em>")
            if p["journal"]:
                html_parts.append(f"      {p['journal']}.")
            if links_html:
                html_parts.append(f"      {links_html}")
            html_parts.append("    </li>")

        html_parts.append("  </ol>")
        html_parts.append("</div>")

    return "\n".join(html_parts)


def inject(fragment: str):
    src = HTML_PATH.read_text(encoding="utf-8")
    if START not in src or END not in src:
        raise SystemExit("No encuentro los marcadores AUTO PUBLICATIONS en publications.html")

    before, rest = src.split(START, 1)
    _, after = rest.split(END, 1)
    new = before + START + "\n" + fragment + "\n" + END + after
    HTML_PATH.write_text(new, encoding="utf-8")


def main():
    items = build_items()
    fragment = render_html(items)
    inject(fragment)
    print(f"OK: {len(items)} publicaciones renderizadas (dedupe aplicado).")


if __name__ == "__main__":
    main()