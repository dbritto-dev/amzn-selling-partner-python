import amzn_selling_partner as sp


def test_write_binary_file_(tmp_path):
    file_path = tmp_path / "testing.json"
    content = b"{}"

    sp.utils.file.write_binary_file(file_path, content)

    with open(file_path) as f:
        assert content.decode() == f.read()
