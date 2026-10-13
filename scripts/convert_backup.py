import os
import sys

def restore_mojibake_line(line: str) -> str:
    """
    Khai phá và khôi phục lỗi mojibake do Windows PowerShell redirection.
    Khi chạy `docker exec -t ... > backup.sql` trên Windows, luồng UTF-8 của PostgreSQL
    bị PowerShell hiểu nhầm thành bảng mã OEM CP437 rồi ghi ra file Unicode.
    Hàm này mã hóa ngược chuỗi về bytes CP437 và giải mã lại theo UTF-8 chuẩn.
    """
    try:
        raw_bytes = line.encode("cp437")
        return raw_bytes.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return line

def fix_backup_sql(src_file: str = "backup_clean.sql", dst_file: str = "backup_clean_fixed.sql"):
    if not os.path.exists(src_file):
        print(f"[-] File không tồn tại: {src_file}")
        return

    print(f"[*] Đang xử lý khôi phục lỗi tiếng Việt từ: {src_file} -> {dst_file}...")
    converted_count = 0
    total_lines = 0

    with open(src_file, "r", encoding="utf-8", errors="replace") as fin, \
         open(dst_file, "w", encoding="utf-8") as fout:
        for line in fin:
            total_lines += 1
            restored = restore_mojibake_line(line)
            if restored != line:
                converted_count += 1
            fout.write(restored)

    print(f"[+] Hoàn tất! Tổng số dòng: {total_lines:,}, số dòng đã sửa mojibake: {converted_count:,}")
    print(f"[+] File xuất sạch: {dst_file}")

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "backup_clean.sql"
    dst = sys.argv[2] if len(sys.argv) > 2 else "backup_clean_fixed.sql"
    fix_backup_sql(src, dst)
