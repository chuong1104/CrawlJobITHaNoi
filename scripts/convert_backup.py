import os
import sys

def convert_to_utf8():
    src = "backup_local.sql"
    dst = "backup_clean.sql"
    
    if not os.path.exists(src):
        print(f"File {src} not found.")
        return

    print(f"Reading {src}...")
    with open(src, "rb") as f:
        bom = f.read(4)

    encoding = "utf-8"
    if bom.startswith(b"\xff\xfe") or bom.startswith(b"\xfe\xff"):
        encoding = "utf-16"
        print(f"Detected UTF-16 encoding with BOM. Converting to UTF-8...")
    else:
        print("Checking encoding...")
        try:
            with open(src, "r", encoding="utf-8") as f:
                f.read(1024)
            print("File is already valid UTF-8.")
            return
        except UnicodeDecodeError:
            encoding = "utf-16"
            print("Detected UTF-16 without BOM. Converting to UTF-8...")

    with open(src, "r", encoding=encoding, errors="replace") as fin:
        with open(dst, "w", encoding="utf-8") as fout:
            for line in fin:
                fout.write(line)

    print(f"Successfully converted to {dst} in UTF-8 encoding!")

if __name__ == "__main__":
    convert_to_utf8()
