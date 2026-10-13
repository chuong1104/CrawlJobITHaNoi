import os
import sys
import traceback

# Đảm bảo thư mục gốc dự án luôn nằm trong sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from src.api.main import app
except Exception as e:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    err_msg = str(e)
    tb_str = traceback.format_exc()
    print(f"CRITICAL ERROR LOADING APP: {err_msg}\n{tb_str}", file=sys.stderr)

    app = FastAPI(title="JobITVN - Error Diagnostic")

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def diagnostic_endpoint(full_path: str):
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Application failed to initialize",
                "details": err_msg,
                "traceback": tb_str.splitlines(),
                "root_dir": root_dir,
                "sys_path": sys.path,
            }
        )
