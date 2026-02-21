from __future__ import annotations

import html
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from pybtex.database import parse_file
from pylatexenc.latex2text import LatexNodes2Text

BIB_PATH = Path("data/publications.bib")
HTML_PATH = Path("publications.html")

START = "<!-- AUTO PUBLICATIONS START -->"
END = "<!-- AUTO PUBLICATIONS END -->"

_l2t = LatexNodes2Text()


def latex_to_unicode(s: str) -> str:
    """Convert LaTeX-escaped strings from .bib into Unicode text."""
    if not s:
        return ""
    out = _l2t.latex_to_text(s)
    # Remove braces used for capitalization protection (e.g., {{TIMP-1}})
    out = out.replace("{", "").replace("}", "")
    # Normalize spacing
    out = re.sub(r"\s+", " ", out).strip()
    return out


def norm_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("doi:", "").strip()
    doi = re.sub(r"\s+", "", doi)
    return doi


def norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def first_field(entry, names) -> str:
    for n in names:
        if n in entry.fields and entry.fields[n].strip():
            return entry.fields[n].strip()
    return ""


def get_authors(entry) -> str:
    persons = entry.persons.get("author", [])
    if not persons:
        return ""
    out = []
    for p in persons:
        first = " ".join(p.first_names)
        last = " ".join(p.last_names)
        name = (first + " " + last).strip() if (first or last) else str(p)
        out.append(name)
    return latex_to_unicode(", ".join(out))


def build_items():
    bib = parse_file(str(BIB_PATH))

    # Dedup priority:
    # 1) DOI
    # 2) PMID
    # 3) (title normalized + year)
    seen = set()
    items = []

    for _, entry in bib.entries.items():
        title_raw = first_field(entry, ["title"])
        year_raw = first_field(entry, ["year"]) or "Unknown"
        journal_raw = first_field(entry, ["journal", "journaltitle", "booktitle"])
        doi_raw = first_field(entry, ["doi"])
        pmid = first_field(entry, ["pmid"])
        url = first_field(entry, ["url"])

        title = latex_to_unicode(title_raw)
        journal = latex_to_unicode(journal_raw)
        year = latex_to_unicode(year_raw) or "Unknown"
        doi = norm_doi(latex_to_unicode(doi_raw))
        authors = get_authors(entry)

        # Sort key (year-month if present)
        month = first_field(entry, ["month"])
        month = month.zfill(2) if month.isdigit() else "01"
        sort_key = f"{year}-{month}"

        # Dedupe key
        if doi:
            dedupe_key = ("doi", doi)
        elif pmid:
            dedupe_key = ("pmid", pmid)
        else:
            dedupe_key = ("titleyear", norm_text(title), year)

        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

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

    # Order: numeric years desc, then everything else
    def year_key(y: str):
        return (0, -int(y)) if str(y).isdigit() else (1, 0)

    parts = []
    for year in sorted(by_year.keys(), key=year_key):
        group = sorted(by_year[year], key=lambda x: x["sort_key"], reverse=True)

        parts.append(f'<div class="pub-year-group" id="y{html.escape(str(year))}">')
        parts.append(f'  <h3 class="pub-year">{html.escape(str(year))}</h3>')
        parts.append('  <ol class="list">')

        for p in group:
            # Escape for safe HTML
            authors = html.escape(p["authors"]) if p["authors"] else ""
            title = html.escape(p["title"]) if p["title"] else ""
            journal = html.escape(p["journal"]) if p["journal"] else ""

            links = []
            if p["doi"]:
                links.append(
                    f'<a href="https://doi.org/{html.escape(p["doi"])}" target="_blank" rel="noopener">DOI</a>'
                )
            if p["pmid"]:
                links.append(
                    f'<a href="https://pubmed.ncbi.nlm.nih.gov/{html.escape(p["pmid"])}/" target="_blank" rel="noopener">PubMed</a>'
                )
            if p["url"]:
                links.append(
                    f'<a href="{html.escape(p["url"])}" target="_blank" rel="noopener">Journal</a>'
                )

            links_html = f'<span class="pub-links">{" ".join(links)}</span>' if links else ""

            parts.append("    <li>")
            if authors:
                parts.append(f"      {authors}.")
            if title:
                parts.append(f"      <em>{title}</em>")
            if journal:
                parts.append(f"      {journal}.")
            if links_html:
                parts.append(f"      {links_html}")
            parts.append("    </li>")

        parts.append("  </ol>")
        parts.append("</div>")

    return "\n".join(parts)


def inject(fragment: str):
    src = HTML_PATH.read_text(encoding="utf-8")
    if START not in src or END not in src:
        raise SystemExit(
            "No encuentro los marcadores AUTO PUBLICATIONS en publications.html.\n"
            f"Asegúrate de tener:\n{START}\n...\n{END}"
        )

    before, rest = src.split(START, 1)
    _, after = rest.split(END, 1)
    new = before + START + "\n" + fragment + "\n" + END + after
    HTML_PATH.write_text(new, encoding="utf-8")


def main():
    if not BIB_PATH.exists():
        raise SystemExit(f"No existe {BIB_PATH}. ¿Está en data/publications.bib?")

    items = build_items()
    fragment = render_html(items)
    inject(fragment)
    print(f"OK: {len(items)} publicaciones renderizadas (LaTeX→Unicode + dedupe).")


if __name__ == "__main__":
    main()