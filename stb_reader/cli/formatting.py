def print_table(headers: list[str], rows: list[list[str]], footer: str = "") -> None:
    all_rows = [headers] + rows
    widths = [max(len(str(cell)) for cell in col) for col in zip(*all_rows)] if all_rows else []
    sep = "  ".join("-" * w for w in widths)
    header_line = "  ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    print(header_line)
    print(sep)
    for row in rows:
        print("  ".join(str(cell).ljust(w) for cell, w in zip(row, widths)))
    if footer:
        print(sep)
        print(footer)
