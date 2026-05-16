from stb_reader.cli.formatting import print_table


def test_print_table_basic(capsys):
    print_table(["ID", "Name"], [["1", "Alpha"], ["2", "Beta"]])
    out = capsys.readouterr().out
    assert "ID" in out
    assert "Alpha" in out
    assert "Beta" in out


def test_print_table_footer(capsys):
    print_table(["ID", "Name"], [["1", "Alpha"]], footer="Page 1 of 3 (30 total)")
    out = capsys.readouterr().out
    assert "Page 1 of 3 (30 total)" in out


def test_print_table_empty(capsys):
    print_table(["ID", "Name"], [])
    out = capsys.readouterr().out
    assert "ID" in out
    assert "Name" in out


def test_print_table_column_widths(capsys):
    print_table(["Short"], [["A very long value"]])
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert len(lines[0]) == len("A very long value")
