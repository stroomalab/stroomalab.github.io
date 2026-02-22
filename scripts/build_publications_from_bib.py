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
    out = out.replace("{", "").replace("}", "")
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


def _render_year_details(year: str, group_items: list[dict], open_by_default: bool) -> str:
    year_str = html.escape(str(year))
    open_attr = " open" if open_by_default else ""
    out = []
    out.append(f'<details class="pub-year-group" id="y{year_str}"{open_attr}>')
    out.append(f'  <summary class="pub-year">{year_str}</summary>')
    out.append('  <ol class="list">')

    for p in group_items:
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

        out.append("    <li>")
        if authors:
            out.append(f"      {authors}.")
        if title:
            out.append(f"      <em>{title}</em>")
        if journal:
            out.append(f"      {journal}.")
        if links_html:
            out.append(f"      {links_html}")
        out.append("    </li>")

    out.append("  </ol>")
    out.append("</details>")
    return "\n".join(out)


def render_html(
    items: list[dict],
    open_last_n_years: int = 5,
    next_n_years_collapsed: int = 5,
    older_bucket_size: int = 10,  # decade buckets
) -> str:
    by_year = defaultdict(list)
    for it in items:
        by_year[it["year"]].append(it)

    # Sort: numeric years desc, then non-numeric at end
    def year_key(y: str):
        return (0, -int(y)) if str(y).isdigit() else (1, 0)

    sorted_years = sorted(by_year.keys(), key=year_key)
    numeric_years_desc = [y for y in sorted_years if str(y).isdigit()]

    # Split numeric years into:
    recent = numeric_years_desc[:open_last_n_years]
    next_block = numeric_years_desc[open_last_n_years : open_last_n_years + next_n_years_collapsed]
    older = numeric_years_desc[open_last_n_years + next_n_years_collapsed :]

    # Bucket older years by decades (or bucket_size)
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for y in older:
        yi = int(y)
        start = (yi // older_bucket_size) * older_bucket_size
        end = start + older_bucket_size - 1
        buckets[(start, end)].append(yi)

    # Buckets in descending order (e.g., 2010-2019, 2000-2009, ...)
    bucket_ranges = sorted(buckets.keys(), key=lambda r: r[0], reverse=True)

    parts = []

    # Controls
    parts.append(
        """
<div class="pub-controls" aria-label="Publication list controls">
  <button type="button" class="btn btn-small" id="pub-expand-all">Expand all</button>
  <button type="button" class="btn btn-small" id="pub-collapse-all">Collapse all</button>
</div>
""".strip()
    )

    # Recent years (open by default)
    for year in recent:
        group = sorted(by_year[year], key=lambda x: x["sort_key"], reverse=True)
        parts.append(_render_year_details(year, group, open_by_default=True))

    # Next block years (collapsed)
    for year in next_block:
        group = sorted(by_year[year], key=lambda x: x["sort_key"], reverse=True)
        parts.append(_render_year_details(year, group, open_by_default=False))

    # Older buckets (each bucket is a parent <details>, containing per-year <details>)
    for (start, end) in bucket_ranges:
        label = f"{start}–{end}"
        bucket_id = f"r{start}-{end}"
        parts.append(f'<details class="pub-range-group" id="{html.escape(bucket_id)}">')
        parts.append(f'  <summary class="pub-range">{html.escape(label)}</summary>')
        parts.append('  <div class="pub-range-inner">')

        # years inside bucket, desc
        for yi in sorted(buckets[(start, end)], reverse=True):
            y = str(yi)
            group = sorted(by_year[y], key=lambda x: x["sort_key"], reverse=True)
            # inside buckets, years are collapsed by default
            parts.append(_render_year_details(y, group, open_by_default=False))

        parts.append("  </div>")
        parts.append("</details>")

    # Non-numeric years (Unknown, In press, etc.) at end (collapsed)
    non_numeric_years = [y for y in sorted_years if not str(y).isdigit()]
    for year in non_numeric_years:
        group = sorted(by_year[year], key=lambda x: x["sort_key"], reverse=True)
        parts.append(_render_year_details(year, group, open_by_default=False))

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
    fragment = render_html(
        items,
        open_last_n_years=5,
        next_n_years_collapsed=5,
        older_bucket_size=10,
    )
    inject(fragment)
    print(f"OK: {len(items)} publicaciones renderizadas (LaTeX→Unicode + dedupe).")


if __name__ == "__main__":
    main()