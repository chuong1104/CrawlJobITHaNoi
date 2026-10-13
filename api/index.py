import os
import sys

# Đảm bảo thư mục gốc dự án luôn nằm trong sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from src.api.main import app
