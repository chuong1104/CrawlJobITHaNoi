# Hướng dẫn Thiết lập Power BI Real-time Dashboard với PostgreSQL

Hệ thống Data Platform của chúng ta lưu trữ tầng Gold (Data Marts) trên PostgreSQL. Để xây dựng một Dashboard Real-time (Thời gian thực) trên Power BI, bạn cần cấu hình chế độ **DirectQuery** thay vì chế độ Import thông thường.

## 1. Cài đặt Power BI Desktop

Power BI Desktop **chỉ hỗ trợ hệ điều hành Windows**. Vì bạn đang code trên môi trường WSL (Ubuntu trên Windows), bạn sẽ cài đặt Power BI trực tiếp trên máy chủ Windows của mình.

### Cách cài đặt:
1. Mở **Microsoft Store** trên Windows.
2. Tìm kiếm **Power BI Desktop**.
3. Nhấn **Install** (Cài đặt).
*(Cài qua Microsoft Store giúp ứng dụng tự động cập nhật phiên bản mới nhất hàng tháng).*

---

## 2. Chuẩn bị Kết nối PostgreSQL từ Windows vào WSL

Power BI trên Windows cần có khả năng "nhìn thấy" database PostgreSQL đang chạy bên trong WSL/Docker.

1. Nếu bạn chạy PostgreSQL bằng Docker trong WSL, hãy đảm bảo đã map port ra ngoài: `ports: - "5432:5432"`.
2. Theo mặc định, Windows có thể truy cập các service chạy trên WSL thông qua địa chỉ `localhost`.
3. **Cài đặt Npgsql (Tùy chọn nhưng thường cần thiết):** 
   Đôi khi Power BI yêu cầu driver Npgsql để kết nối với PostgreSQL. Nếu khi kết nối gặp lỗi thiếu driver, bạn tải bản cài đặt `.msi` từ [trang chủ Npgsql](https://github.com/npgsql/npgsql/releases) (chọn bản 4.0.10 hoặc mới hơn có file msi, tick chọn tùy chọn *Npgsql GAC Installation* khi cài). Tuy nhiên, các phiên bản Power BI mới nhất thường đã tích hợp sẵn.

---

## 3. Kết nối Power BI tới PostgreSQL (Real-time / DirectQuery)

Đây là bước quan trọng nhất để Dashboard của bạn là Real-time:

1. Mở Power BI Desktop.
2. Trên tab Home, chọn **Get Data** -> **More...** -> Tìm kiếm **PostgreSQL database**.
3. Nhấn **Connect**. Bảng thông số hiện ra:
   - **Server**: `localhost` (hoặc IP của WSL nếu `localhost` không hoạt động).
   - **Database**: `jobitvn` (hoặc tên database của bạn).
   - **Data Connectivity mode**: BẮT BUỘC chọn **DirectQuery** (Đừng chọn Import).
     *DirectQuery không copy dữ liệu vào Power BI mà sẽ bắn thẳng câu lệnh SQL xuống PostgreSQL mỗi khi bạn thao tác trên Dashboard. Nhờ vậy, dữ liệu luôn là mới nhất.*
4. Nhấn **OK**.
5. Nhập **User name** và **Password** (ví dụ: `postgres` / `postgres`).
6. **Lưu ý về SSL**: Nếu báo lỗi "Encryption Support", nhấn **OK** để thử kết nối không mã hóa (Unencrypted), hoặc bỏ tick "Encrypt connections" trong phần cấu hình.
7. Khi bảng Navigator hiện ra, bạn hãy chọn các view trong schema `mart_bi` mà chúng ta vừa tạo:
   - `agg_demand_trend`
   - `kpi_daily_summary`
   - `agg_salary_by_skill`
8. Nhấn **Load**.

---

## 4. Cấu hình Tự động Refresh (Page Refresh) trong Power BI

Dù dùng DirectQuery, màn hình Power BI Desktop mặc định chỉ cập nhật khi bạn click vào nó. Để màn hình tự động chớp và load data mới (ví dụ hiển thị lên màn hình Tivi):

1. Click vào khoảng trống trên màn hình Report (không chọn visual nào).
2. Mở tab **Format your report page** (biểu tượng cây cọ sơn).
3. Cuộn xuống dưới cùng, tìm mục **Page refresh**.
4. Bật chế độ **On**.
5. Thiết lập thời gian refresh (ví dụ: **5 seconds** hoặc **1 minute** tùy độ chịu tải của server database).
6. Từ lúc này, cứ mỗi 5 giây, Power BI sẽ tự động query xuống PostgreSQL để lấy số liệu mới nhất mà không cần bạn làm gì cả.

> **Mẹo Tối Ưu Cho Real-time:**  
> Đừng lôi các bảng chi tiết (như `fct_job_posting` với hàng trăm ngàn dòng) ra làm Dashboard realtime bằng DirectQuery. Hãy dùng các View đã được tính toán sẵn như `kpi_daily_summary` ở `mart_bi` (đã được dbt tính toán sẵn trên PostgreSQL). Nó sẽ làm Dashboard chạy nhanh như chớp.
