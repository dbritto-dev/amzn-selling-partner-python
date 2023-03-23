def write_binary_file(file_path: str, content: bytes) -> None:
    with open(file_path, "bw") as f:
        f.write(content)
