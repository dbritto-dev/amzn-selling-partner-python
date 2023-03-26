import pathlib

import amzn_selling_partner as sp


def test_write_binary_file_(tmp_path: pathlib.Path):
    file_path = str(tmp_path / "testing.json")
    content = b"{}"

    sp.utils.file.write_binary_file(file_path, content)

    with open(file_path) as f:
        assert content.decode() == f.read()
