import pathlib

def read_file(path: pathlib.Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        return handle.read()
    
def read_1_raw_file(path: pathlib.Path) -> str:
    with path.open ("r", encoding="utf-8") as handle:
        return handle.read()
def main():
    test_path = pathlib.Path(__file__).parent/ "sample.txt"
    content = read_file(test_path)
    print(content)

if __name__ == "__main__":
    main()