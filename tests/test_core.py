from pathlib import Path
from capcut_draft_studio.subtitles import split_sentences, balance_text_lines, srt_ts

def test_split():
    assert split_sentences("Một hai ba bốn năm sáu.",3)==["Một hai ba","bốn năm sáu."]
def test_srt():
    assert srt_ts(61.234)=="00:01:01,234"
def test_balance():
    assert "\n" in balance_text_lines("one two three four five six seven eight nine ten",20)
