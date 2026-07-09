from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from src.api.database import db
from src.api.routers import jobs
import uvicorn

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kết nối DB khi ứng dụng khởi chạy
    await db.connect()
    yield
    # Ngắt kết nối khi ứng dụng dừng
    await db.disconnect()

app = FastAPI(
    title="JobITVN Data Serving API",
    description="API cung cấp thông tin tuyển dụng IT tại Việt Nam",
    version="1.0.0",
    lifespan=lifespan
)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký router
app.include_router(jobs.router)

# Mount thư mục Static phục vụ giao diện Web Frontend
app.mount("/", StaticFiles(directory="src/api/static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)
