"""10-K text and section tests, on a tiny hand-written filing."""
from due_diligent.filings import extraction_text, filing_text, find_sections

FILING_HTML = """<html><body>
<div style="display:none"><ix:header><ix:hidden>secret dei facts</ix:hidden></ix:header></div>
<p>Table of Contents</p>
<table>
<tr><td>Item 1.</td><td>Business</td><td>1</td></tr>
<tr><td>Item 1A.</td><td>Risk Factors</td><td>5</td></tr>
<tr><td>Item 7.</td><td>Management's Discussion and Analysis</td><td>20</td></tr>
<tr><td>Item 8.</td><td>Financial Statements</td><td>30</td></tr>
</table>
<div><span>Item</span><span>&#160;1.</span> <span>Business</span></div>
<p>We sell phones in two segments, Americas and Europe, and we describe them at length here.</p>
<div>Item 1A. Risk Factors</div>
<p>Competition is intense and could reduce our margins over the coming years.</p>
<p>Item 1A of this report also mentions other things in a sentence long enough to be a paragraph and not a heading at all, so it is skipped by the length rule we use.</p>
<div>Item 7. Management's Discussion and Analysis</div>
<p>Net sales were $ 416,161 million, and we expect growth next year.</p>
<div>Item 8. Financial Statements</div>
<table><tr><td>Total net sales</td><td>$</td><td>416,161</td></tr></table>
<div>Item 9. Changes in and Disagreements with Accountants</div>
<p>None.</p>
</body></html>"""

def test_text_drops_hidden_xbrl_and_joins_inline_spans():
    text = filing_text(FILING_HTML)
    assert "secret" not in text
    assert "Item 1. Business" in text.splitlines()  # three spans, one line, no-break space gone

def test_table_cells_share_a_line():
    assert "Total net sales $ 416,161" in filing_text(FILING_HTML).splitlines()

def test_sections_pick_the_body_not_the_table_of_contents():
    sections = find_sections(filing_text(FILING_HTML))
    assert "two segments" in sections["1"]
    assert "Competition is intense" in sections["1a"]
    assert sections["8"].startswith("Item 8. Financial Statements")
    assert "None." in sections["9"]

def test_long_sentence_starting_with_item_is_not_a_heading():
    assert "skipped by the length rule" in find_sections(filing_text(FILING_HTML))["1a"]

def test_extraction_text_keeps_only_needed_sections():
    text, found = extraction_text(filing_text(FILING_HTML))
    assert found
    assert "Competition is intense" in text
    assert "None." not in text  # Item 9 isn't sent

def test_falls_back_to_full_text_when_a_section_is_missing():
    text = "Item 1. Business\nWe make things.\nItem 7. MD&A\nSales grew."
    assert extraction_text(text) == (text, False)

def test_page_headers_repeating_an_item_do_not_split_it():
    text = ("Item 1. Business\nPage one about phones.\nItem 1\nPage two about tablets.\n"
            "Item 1A. Risk Factors\nPage one risks.\nItem 1A\nPage two risks.\n"
            "Item 7. MD&A\nSales grew.\nItem 8. Financial Statements\nNumbers.")
    sections = find_sections(text)
    assert "phones" in sections["1"] and "tablets" in sections["1"]
    assert "Page one risks" in sections["1a"] and "Page two risks" in sections["1a"]

def test_item_15_is_sent_when_item_8_only_points_to_it():
    text = ("Item 1. Business\nWe make chips.\nItem 1A. Risk Factors\nSupply is tight.\n"
            "Item 7. MD&A\nSales grew.\nItem 8. Financial Statements\nSee Item 15.\n"
            "Item 9. Changes in Accountants\nNone.\n"
            "Item 15. Exhibits and Financial Statement Schedules\nRevenue 130,497")
    sent, found = extraction_text(text)
    assert found
    assert "Revenue 130,497" in sent
    assert "None." not in sent