
import pytest
import os
from spotify_playlist_converter import parse_text_playlist_file

def test_hierarchical_parsing(tmp_path):
    """Test parsing of hierarchical artist/song lists."""
    content = """Elori Saxl
• "Wave I"
• "Wave II"
• "Memory of Water"

Trevor Dunn's Trio-Convulsant
• "Sister Beatrice"
• "Secours Meurtriers"
• "Restore All Things"

Indented Artist
    Indented Song 1
    Indented Song 2

Standard Artist - Standard Song
"""
    d = tmp_path / "test_playlists"
    d.mkdir()
    p = d / "hierarchical.txt"
    p.write_text(content, encoding='utf-8')
    
    tracks = parse_text_playlist_file(str(p))
    
    assert len(tracks) == 9
    
    # Check hierarchical with bullets
    assert tracks[0]['artist'] == "Elori Saxl"
    assert tracks[0]['title'] == "Wave I"
    assert tracks[1]['artist'] == "Elori Saxl"
    assert tracks[2]['artist'] == "Elori Saxl"
    
    assert tracks[3]['artist'] == "Trevor Dunn's Trio-Convulsant"
    assert tracks[3]['title'] == "Sister Beatrice"
    
    # Check indentation
    assert tracks[6]['artist'] == "Indented Artist"
    assert tracks[6]['title'] == "Indented Song 1"
    assert tracks[7]['artist'] == "Indented Artist"
    assert tracks[7]['title'] == "Indented Song 2"
    
    # Check standard format still works
    assert tracks[8]['artist'] == "Standard Artist"
    assert tracks[8]['title'] == "Standard Song"

def test_mixed_format_parsing(tmp_path):
    """Test parsing of mixed hierarchical and standard formats."""
    content = """Artist One
* Song A
* Song B
Artist Two - Song C
Artist Two
* Song D
"""
    p = tmp_path / "mixed.txt"
    p.write_text(content, encoding='utf-8')
    
    tracks = parse_text_playlist_file(str(p))
    
    assert len(tracks) == 4
    assert tracks[0]['artist'] == "Artist One"
    assert tracks[0]['title'] == "Song A"
    assert tracks[1]['artist'] == "Artist One"
    assert tracks[1]['title'] == "Song B"
    assert tracks[2]['artist'] == "Artist Two"
    assert tracks[2]['title'] == "Song C"
    assert tracks[3]['artist'] == "Artist Two"
    assert tracks[3]['title'] == "Song D"
