# Hướng Dẫn Chi Tiết Thiết Lập Dashboard Phân Tích Tuyển Dụng JobITVN Trên Power BI

Tài liệu này hướng dẫn từng bước chi tiết từ kết nối cơ sở dữ liệu PostgreSQL (Docker), thiết lập mô hình dữ liệu hình sao (Star Schema), viết các công thức đo lường DAX, đến kéo thả thiết kế các biểu đồ phân tích trên **Power BI Desktop**.

---

## 🔌 BƯỚC 1: KẾT NỐI POWER BI TỚI POSTGRESQL (REAL-TIME)

Để báo cáo luôn cập nhật số liệu mới nhất khi hệ thống cào dữ liệu chạy hàng ngày, chúng ta sử dụng phương thức kết nối trực tiếp **DirectQuery** tới PostgreSQL.

### 1.1 Cấu hình cổng kết nối
1. Mở ứng dụng **Power BI Desktop** trên máy tính Windows.
2. Trên thanh công cụ Home, nhấn **Get Data** (Lấy dữ liệu) $\rightarrow$ chọn **More...** $\rightarrow$ Tìm kiếm và chọn **PostgreSQL database** $\rightarrow$ Click **Connect**.
3. Điền thông tin kết nối máy chủ:
   - **Server:** `localhost:5432` (hoặc `localhost` nếu PostgreSQL sử dụng cổng mặc định).
   - **Database:** `job_scraper_db`
   - **Data Connectivity mode:** Chọn **DirectQuery** (để truy vấn trực tiếp theo thời gian thực) hoặc **Import** (tải dữ liệu về RAM để tối ưu hiệu năng vẽ biểu đồ).
4. Nhấn **OK**.
         
### 1.2 Đăng nhập tài khoản Database
1. Trong cửa sổ yêu cầu đăng nhập, chọn tab **Database** ở menu dọc bên trái.
2. Nhập thông tin xác thực CSDL đã được thiết lập sẵn:
   - **User name:** `airflow`
   - **Password:** `airflow`
3. Nhấn **Connect**.
   > [!NOTE]
   > Nếu hệ thống hiển thị cảnh báo **"Encryption Support"** (Không hỗ trợ mã hóa SSL), hãy nhấn **OK** hoặc **Unencrypted** để tiếp tục kết nối (PostgreSQL chạy Docker local không bật bắt buộc SSL).

---

## 📐 BƯỚC 2: CHỌN BẢNG VÀ THIẾT LẬP MÔ HÌNH HÌNH SAO (STAR SCHEMA)

Mô hình hình sao là chuẩn mực thiết kế giúp tối ưu hiệu năng tính toán DAX và liên kết các biểu đồ trong Power BI.

### 2.1 Chọn các bảng trong cửa sổ Navigator
Trong danh sách bảng hiển thị dưới schema **`dwh`**, tích chọn các bảng sau rồi nhấn **Load**:
- **Bảng Fact (Bảng chính):**
  - `dwh.fct_job_posting` (Chứa các thước đo lương, kinh nghiệm, cờ trạng thái hoạt động; và các cột phân loại thẳng như `job_level`, `job_type`, `work_mode`).
- **Các bảng Dimension (Bảng chiều lọc):**
  - `dwh.dim_company` (Tên công ty, quy mô, ngành nghề).
  - `dwh.dim_date` (Thông tin thời gian: ngày, tháng, năm, quý).
  - `dwh.dim_source` (Các trang cào dữ liệu: TopCV, JobsGo, LinkedIn...).
- **Các bảng Bridge (Bảng cầu nối cho quan hệ nhiều-nhiều):**
  - `dwh.bridge_job_skill` (Cầu nối giữa tin tuyển dụng và kỹ năng).
  - `dwh.dim_skill` (Danh mục tên kỹ năng: Python, Java, SQL...).
  - `dwh.bridge_job_location` (Cầu nối giữa tin tuyển dụng và địa điểm).
  - `dwh.dim_location` (Tên tỉnh thành: Hà Nội, TP.HCM, Đà Nẵng).

> [!NOTE]
> Bảng `dim_job_attributes` **không tồn tại** trong Data Warehouse. Các thông tin cấp bậc (`job_level`), loại hình làm việc (`job_type`) và hình thức làm việc (`work_mode`) đã được lưu thẳng vào `fct_job_posting`. **Không import bảng này vào PowerBI.**

### 2.2 Thiết lập mối quan hệ trong Model View
Di chuyển sang tab **Model View** (biểu tượng sơ đồ kết nối ở thanh công cụ bên trái ngoài cùng) và liên kết các khóa ngoại như sau bằng cách kéo thả:

1. **Liên kết Công ty:** Kéo trường `dim_company[company_key]` thả vào `fct_job_posting[company_key]`.
   - *Relationship:* 1-to-Many (`1` ở dim_company, `*` ở fct_job_posting).
2. **Liên kết Thời gian:** Kéo trường `dim_date[date_key]` thả vào `fct_job_posting[posted_date_key]`.
   - *Relationship:* 1-to-Many.
3. **Liên kết Nguồn tuyển dụng:** Kéo trường `dim_source[source_key]` thả vào `fct_job_posting[source_key]`.
   - *Relationship:* 1-to-Many.

> [!IMPORTANT]
> **Không cần liên kết `dim_job_attributes`** — bảng này không tồn tại trong database. Các cột phân loại `job_level`, `job_type`, `work_mode` đã có sẵn trong `fct_job_posting` và dùng trực tiếp làm bộ lọc/trục biểu đồ mà không cần bảng dimension riêng.
5. **Liên kết Kỹ năng (Quan hệ Nhiều - Nhiều):**
   - Kéo `fct_job_posting[job_posting_fact_id]` nối tới `bridge_job_skill[job_posting_fact_id]` (1-to-Many).
   - Kéo `dim_skill[skill_key]` nối tới `bridge_job_skill[skill_key]` (1-to-Many).
   - *Lưu ý:* Bật chiều lọc chéo (Cross filter direction) của quan hệ giữa `bridge_job_skill` và `fct_job_posting` thành **Both** (Cả hai) để khi chọn kỹ năng, danh sách job sẽ được lọc theo.
6. **Liên kết Địa điểm (Quan hệ Nhiều - Nhiều):**
   - Kéo `fct_job_posting[job_posting_fact_id]` nối tới `bridge_job_location[job_posting_fact_id]` (1-to-Many).
   - Kéo `dim_location[location_key]` nối tới `bridge_job_location[location_key]` (1-to-Many).
   - *Lưu ý:* Bật chiều lọc chéo thành **Both** tương tự như kỹ năng.

---

## 🧮 BƯỚC 3: VIẾT CÔNG THỨC ĐO LƯỜNG DAX (MEASURES)

> [!IMPORTANT]
> **Lưu ý về tên bảng trong Power BI:** Khi import từ PostgreSQL, Power BI sẽ tự động đặt tên bảng là `'dwh fct_job_posting'` (chứa cả tên schema `dwh` và dấu cách). Do đó, trong công thức DAX bạn phải bọc tên bảng trong dấu nháy đơn: `'dwh fct_job_posting'`.
>
> *Mẹo:* Bạn có thể click đúp vào tên các bảng ở khung **Data/Fields** bên phải Power BI để đổi tên chúng thành ngắn gọn hơn (ví dụ: đổi `'dwh fct_job_posting'` thành `fct_job_posting`), khi đó viết công thức DAX sẽ dễ dàng hơn.

Nếu giữ nguyên tên mặc định của Power BI, các công thức DAX sẽ được viết như sau:

### 3.1 Chỉ số Tổng Số Việc Làm Đang Tuyển
Đếm số lượng tin đăng tuyển dụng duy nhất đang hoạt động:
```dax
Total Jobs = 
CALCULATE(
    DISTINCTCOUNT('dwh fct_job_posting'[job_posting_fact_id]),
    'dwh fct_job_posting'[is_active] = TRUE()
)
```

### 3.2 Chỉ số Mức Lương Trung Bình (Triệu VNĐ)
Tính mức lương trung bình giữa mức lương tối thiểu và tối đa:
```dax
Avg Salary (M.VND) = 
CALCULATE(
    DIVIDE(AVERAGE('dwh fct_job_posting'[salary_midpoint_vnd]), 1000000),
    'dwh fct_job_posting'[has_salary] = TRUE()
)
```

### 3.3 Tổng Số Nhà Tuyển Dụng Hoạt Động
Đếm số lượng công ty duy nhất đang đăng tin tuyển dụng:
```dax
Hiring Companies = 
CALCULATE(
    DISTINCTCOUNT('dwh fct_job_posting'[company_key]),
    'dwh fct_job_posting'[is_active] = TRUE()
)
```

### 3.4 Tỷ Lệ Tin Tuyển Thực Tập Sinh / Fresher
Tính tỷ trọng tin đăng dành cho các bạn trẻ mới ra trường:
```dax
Fresher Rate = 
DIVIDE(
    CALCULATE([Total Jobs], 'dwh fct_job_posting'[is_fresher] = TRUE() || 'dwh fct_job_posting'[is_intern] = TRUE()),
    [Total Jobs],
    0
)
```

---

## 🎨 BƯỚC 4: THIẾT KẾ CÁC BIỂU ĐỒ TRỰC QUAN (VISUALS)

Chuyển sang tab **Report View** (Thanh công cụ bên trái trên cùng) để kéo thả thiết kế giao diện Dashboard phân tích.

### 4.1 Khối Chỉ Số KPIs Đầu Trang (Card Visuals)
1. Chọn biểu tượng **Card** (Thẻ hiển thị một chỉ số) trong khung Visualizations.
2. Kéo measure `[Total Jobs]` thả vào ô Field. Định dạng lại cỡ chữ to, đậm.
3. Tạo thêm 3 thẻ tương ứng cho `[Avg Salary (M.VND)]` (thêm hậu tố "Tr. VND"), `[Hiring Companies]`, và `[Fresher Rate]` (định dạng %).
4. Đặt xếp hàng ngang ở phía trên cùng của Dashboard.

### 4.2 Biểu Đồ Top Kỹ Năng Đăng Tuyển Nhiều Nhất (Clustered Bar Chart)
1. Chọn biểu tượng **Clustered Bar Chart** (Biểu đồ thanh ngang).
2. Kéo trường `dim_skill[skill_name]` vào phần **Y-axis** (Trục tung).
3. Kéo measure `[Total Jobs]` vào phần **X-axis** (Trục hoành).
4. *Bộ lọc:* Định dạng biểu đồ $\rightarrow$ chọn bộ lọc Top N của `skill_name` là **Top 10** theo giá trị `[Total Jobs]` để chỉ hiển thị 10 kỹ năng phổ biến nhất (ví dụ: JAVA, DEVOPS, PYTHON...).

### 4.3 Biểu Đồ Phân Bổ Việc Làm Theo Địa Điểm (Donut Chart)
1. Chọn biểu tượng **Donut Chart** (Biểu đồ tròn/bánh donut).
2. Kéo trường `dim_location[location_name]` vào phần **Legend** (Chú giải).
3. Kéo measure `[Total Jobs]` vào phần **Values** (Giá trị).
4. Biểu đồ sẽ hiển thị tỷ lệ phần trăm phân bố tin tuyển dụng giữa Hà Nội, TP.HCM và Đà Nẵng.

### 4.4 Biểu Đồ Xu Hướng Tuyển Dụng Theo Thời Gian (Line Chart)
1. Chọn biểu tượng **Line Chart** (Biểu đồ đường).
2. Kéo trường `dim_date[month_name]` (hoặc `date_value`) vào phần **X-axis** (Trục hoành).
3. Kéo measure `[Total Jobs]` vào phần **Y-axis** (Trục tung).
4. Kéo trường `dim_source[source_name]` vào phần **Legend** để so sánh xem nguồn nào (TopCV, JobsGo) có lượng tin đăng tăng trưởng mạnh nhất qua các tuần/tháng.

### 4.5 Bản Đồ Phân Phối Lương Trung Bình Theo Ngành/Cấp Bậc (Matrix)
1. Chọn biểu tượng **Matrix** (Bảng ma trận).
2. Kéo trường `dim_company[industry]` vào phần **Rows** (Dòng).
3. Kéo trường `fct_job_posting[job_level]` hoặc `fct_job_posting[job_type]` vào phần **Columns** (Cột).
   - Các cột phân loại này nằm **thẳng trong `fct_job_posting`**, không cần qua bảng dim riêng.
4. Kéo measure `[Avg Salary (M.VND)]` vào phần **Values**.
5. Định dạng bảng với tính năng **Conditional Formatting** (Tô màu nền theo dải màu từ thấp đến cao) để làm nổi bật những ô có mức lương cao đột biến.

---

## 🔄 BƯỚC 5: THIẾT LẬP TỰ ĐỘNG LÀM MỚI BÁO CÁO (PAGE REFRESH)

Vì chúng ta sử dụng cổng PostgreSQL qua docker local ở chế độ DirectQuery, bạn có thể thiết lập cho Power BI tự động cập nhật biểu đồ liên tục:
1. Nhấp chuột vào một khoảng trống bất kỳ trên trang báo cáo để bỏ chọn các biểu đồ.
2. Tại khung **Format** bên phải (biểu tượng Cây cọ sơn), mở rộng mục **Page refresh**.
3. Chuyển trạng thái sang **On**.
4. Thiết lập **Refresh interval** là `1 minute` hoặc `10 seconds`. Báo cáo sẽ tự động gửi câu lệnh SQL xuống PostgreSQL để làm mới số liệu hiển thị mà không cần click nút Refresh thủ công.
