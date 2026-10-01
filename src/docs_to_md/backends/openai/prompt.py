"""The transcription prompt: what the model is asked to do with each page.

``instructions_for`` fills in the page count, output format, and figure rules.
Keep changes measurable: run ``benchmarks/scanned_books/run.py`` before and after.
"""

from __future__ import annotations

_FORMAT_RULES = {
    "markdown": """\
- Write Markdown: `#` headings that follow the document's hierarchy, lists, `>`
  block quotes, and `*italic*` / `**bold**` where the page uses them.
- Write tables as GitHub-flavored Markdown tables with every row and cell. If a
  header spans several columns, repeat it in each column it covers.
- Write mathematics as LaTeX: `$...$` inline and `$$...$$` for display equations.""",
    "html": """\
- Write each page as an HTML fragment (no <html>, <head>, or <body>) using
  semantic tags: <h1>-<h6>, <p>, <ul>/<ol>, <blockquote>, <em>, <strong>, <sup>.
- Write tables as <table> with every row and cell; use colspan and rowspan for
  spanning headers.
- Write mathematics as LaTeX inside <math> elements, with display="block" for
  display equations.""",
}

_FIGURE_RULES = {
    True: "- Replace each illustration, photo, chart, or diagram with a one-sentence description"
    " in italics, in square brackets. Keep any printed caption as text.",
    False: "- Leave out illustrations, photos, charts, and diagrams, but keep their printed captions.",
}

INSTRUCTIONS = """\
You transcribe document pages into {format_name}. Return JSON whose "pages" array
has exactly one string per input page, in order: {page_count} page{plural}. Never
merge, split, skip, or reorder pages. A blank page is an empty string. One input
page may show two facing book pages; it is still ONE page: transcribe the left
page completely, ending with its footnotes, before any text of the right page.

Transcribe faithfully:
- Copy every word exactly as printed, letter by letter, in its original
  language, script, spelling, accents, and punctuation. Keep historical
  spellings and misprints: a misspelled word stays misspelled. Never modernize
  words, make them look older, or correct them. Do not translate, summarize, or
  add commentary.
- Keep editorial marks such as [1v], [sic], [...] and \\word/ exactly as printed.
- Follow the reading order: columns in order, and vertical text (as in Chinese
  or Japanese) written out as horizontal lines in its reading order.
- Leave out running headers, running footers, page numbers, library stamps, and
  scanning artifacts.
- Write each paragraph as one line of text. Rejoin words hyphenated across line
  breaks, and keep line breaks only where they matter, as in verse.
- Put footnotes at the end of the page they appear on, with their markers.
- Outside mathematics, write superscript text, such as footnote markers and
  abbreviations like Ex.<sup>mo</sup> or M<sup>lle</sup>, as <sup>...</sup>.
{format_rules}
{figure_rules}"""


def instructions_for(output_format: str, page_count: int, describe_figures: bool) -> str:
    return INSTRUCTIONS.format(
        format_name="Markdown" if output_format == "markdown" else "HTML",
        page_count=page_count,
        plural="s" * (page_count != 1),
        format_rules=_FORMAT_RULES[output_format],
        figure_rules=_FIGURE_RULES[describe_figures],
    )
