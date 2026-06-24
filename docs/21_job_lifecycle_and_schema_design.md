# 21. Quản Lý Vòng Đời Tin Tuyển Dụng & Thiết Kế Cấu Trúc Dữ Liệu

Tài liệu này mô tả chi tiết cơ chế quản lý vòng đời tin tuyển dụng (Job Lifecycle Management) và kiến trúc dữ liệu ba tầng từ cơ sở dữ liệu nghiệp vụ (Operational DB/3NF) sang kho dữ liệu (Data Warehouse) và các phân vùng dữ liệu phục vụ (Data Marts). Toàn bộ nội dung được diễn giải bằng văn bản mô tả, không sử dụng các khối mã nguồn để đảm bảo tính trực quan và tập trung vào tư duy thiết kế hệ thống.

---

## Chương 1: Định Nghĩa & Quản Lý Vòng Đời Tin Tuyển Dụng

Khác với dữ liệu giao dịch hay bán hàng vốn có tính ổn định và tính toàn vẹn cao, dữ liệu tin tuyển dụng có biến động rất lớn. Một tin tuyển dụng có thể thay đổi tiêu đề, cập nhật mức lương, sửa đổi yêu cầu công việc, bị gỡ bỏ khỏi website, được đăng lại sau một thời gian, hoặc thậm chí hết hạn nhưng đơn vị tuyển dụng không xóa khỏi trang web. Do đó, thiết kế cơ chế quản lý vòng đời tin tuyển dụng là yếu tố sống còn để hệ thống không bị trùng lặp dữ liệu, không hiển thị tin rác, và đảm bảo báo cáo phân tích xu hướng chính xác.

### 1.1 Các Trạng Thái Vòng Đời của Job
Hệ thống quản lý vòng đời tin tuyển dụng thông qua một trường trạng thái duy nhất lưu trong bảng tin tuyển dụng nghiệp vụ, bao gồm chín trạng thái cốt lõi:

* **NEW (Mới phát hiện):** Trạng thái gán cho tin tuyển dụng trong lần đầu tiên hệ thống quét (crawl) thấy và lưu vào cơ sở dữ liệu.
* **ACTIVE (Đang hoạt động):** Trạng thái xác nhận tin tuyển dụng vẫn tiếp tục xuất hiện trên nguồn tuyển dụng trong các lượt quét tiếp theo và không có thay đổi lớn về nội dung.
* **UPDATED (Đã cập nhật):** Trạng thái gán khi tin tuyển dụng được phát hiện có sự thay đổi về nội dung quan trọng (ví dụ: đổi tiêu đề, điều chỉnh lương, thay đổi mô tả) nhưng vẫn thuộc cùng một định danh tin tuyển dụng.
* **EXPIRED (Đã hết hạn):** Trạng thái xác lập khi tin tuyển dụng đã vượt quá hạn nộp hồ sơ được ghi nhận trên bài đăng hoặc khi hệ thống quét thấy bài viết chứa các từ khóa báo hết hạn rõ ràng.
* **NOT_FOUND (Không tìm thấy):** Trạng thái tạm thời khi tin tuyển dụng biến mất khỏi trang danh sách quét nghiệp vụ (listing page) nhưng chưa đủ điều kiện để khẳng định đã đóng.
* **CLOSED (Đã đóng):** Trạng thái xác định tin tuyển dụng đã chính thức ngừng nhận hồ sơ, được chuyển sau khi trạng thái không tìm thấy duy trì quá số lần quy định hoặc khi trang chi tiết phản hồi mã lỗi không tồn tại bài viết.
* **REPOSTED (Đăng lại):** Trạng thái đánh dấu một tin tuyển dụng từng bị đóng hoặc hết hạn nay xuất hiện trở lại trên nguồn với nội dung tương tự hoặc mã định danh cũ.
* **DUPLICATE (Trùng lặp):** Trạng thái gán cho tin tuyển dụng được xác định là bản sao trùng lặp hoàn toàn của một tin tuyển dụng khác trên cùng một nguồn (sẽ được gom cụm thay vì hiển thị riêng lẻ).
* **INVALID (Không hợp lệ):** Trạng thái đánh dấu các tin tuyển dụng parse lỗi nghiêm trọng, thiếu các thông tin cốt lõi bắt buộc, hoặc không thuộc nhóm ngành công nghệ thông tin và dữ liệu theo bộ lọc của hệ thống.

---

### 1.2 Cơ Chế Xử Lý Tin Tuyển Dụng Hết Hạn
Hệ thống xử lý tin hết hạn qua ba kịch bản chính dựa trên các luồng thông tin thu thập được:

#### Trường hợp 1: Website cung cấp thời hạn nộp hồ sơ rõ ràng
Khi quét được ngày hết hạn cụ thể từ bài đăng, hệ thống sẽ lưu thông tin này vào trường ngày hết hạn. Định kỳ mỗi ngày, một tiến trình chạy ngầm sẽ so sánh ngày hiện tại với ngày hết hạn. Nếu ngày hiện tại lớn hơn ngày hết hạn, hệ thống tự động chuyển trạng thái tin tuyển dụng sang Đã hết hạn (EXPIRED), đặt cờ hoạt động thành Sai (false), và ghi nhận lý do ngừng hoạt động là hết hạn do quá hạn nộp hồ sơ.

#### Trường hợp 2: Website không ghi ngày hết hạn nhưng tin biến mất khỏi trang danh sách
Đây là trường hợp phổ biến nhất. Tin tuyển dụng biến mất khỏi trang danh sách có thể do đã đóng tuyển dụng, nhưng cũng có thể do lỗi kỹ thuật như lỗi phân trang, crawler bị chặn, mạng chập chờn, hoặc tin tuyển dụng bị đẩy sâu xuống các trang sau mà crawler chưa quét tới.
Để tránh việc đánh dấu đóng tin sai lệch, hệ thống sử dụng một trường đếm số lần không tìm thấy (not_found_count). 
* Khi quét hằng ngày, nếu một tin tuyển dụng đang hoạt động không xuất hiện trong danh sách mới quét, hệ thống tăng số lần không tìm thấy lên 1 và vẫn giữ trạng thái tin là Đang hoạt động (ACTIVE).
* Nếu số lần không tìm thấy liên tiếp đạt đến ngưỡng quy định (ví dụ là 3 lần quét thành công liên tiếp của nguồn đó), hệ thống mới chính thức chuyển trạng thái tin sang Đã đóng (CLOSED), đặt cờ hoạt động thành Sai (false), ghi nhận ngày đóng là ngày hiện tại, và lưu lý do ngừng hoạt động là không tìm thấy quá 3 lần.
* Nếu tin tuyển dụng xuất hiện trở lại trước khi chạm ngưỡng, trường đếm số lần không tìm thấy sẽ được thiết lập lại về 0 và ngày cập nhật cuối cùng được làm mới.

#### Trường hợp 3: Trang chi tiết báo lỗi hoặc mất nút ứng tuyển
Đây là tín hiệu trực tiếp và mạnh mẽ nhất để đóng tin. Khi hệ thống thực hiện quét kiểm tra trang chi tiết (detail verification crawl):
* Nếu máy chủ phản hồi mã lỗi 404 (Không tìm thấy trang) hoặc 410 (Trang đã bị xóa vĩnh viễn), hệ thống sẽ lập tức chuyển trạng thái tin tuyển dụng sang Đã đóng (CLOSED) và tắt cờ hoạt động.
* Nếu trang chi tiết vẫn tồn tại nhưng nội dung hiển thị các thông báo như "Tin tuyển dụng đã hết hạn", "Ngừng nhận hồ sơ", hoặc nút ứng tuyển bị vô hiệu hóa/biến mất, hệ thống chuyển trạng thái tin sang Đã đóng (CLOSED) hoặc Đã hết hạn (EXPIRED) tùy theo từ khóa nhận diện, kèm theo lý do ngừng hoạt động tương ứng.

---

### 1.3 Các Loại Khóa Định Danh Tin Tuyển Dụng
Để liên kết dữ liệu quét mới với dữ liệu hiện có trong cơ sở dữ liệu, hệ thống sử dụng ba cấp độ khóa định danh:

* **Mã định danh nguồn tin (source_job_id):** Khóa mạnh nhất, là ID nội bộ mà website tuyển dụng cấp cho tin đó. Ví dụ, mã số tin tuyển dụng trên TopCV hay ITviec. Sự kết hợp giữa mã nguồn tuyển dụng và mã định danh nguồn tin là khóa duy nhất giúp xác định chính xác một tin tuyển dụng dù tiêu đề hay nội dung có thay đổi.
* **Đường dẫn chuẩn hóa (canonical_url):** Khóa mạnh thứ hai. Hệ thống thực hiện loại bỏ tất cả các tham số theo dõi chiến dịch quảng cáo, tham số định danh phiên làm việc khỏi URL để giữ lại đường dẫn gốc ổn định nhất. Nếu trang web tuyển dụng không có mã định danh số rõ ràng, đường dẫn chuẩn hóa này sẽ được dùng làm khóa định danh duy nhất.
* **Mã vân tay dữ liệu (fingerprint hashes):** Khi tin tuyển dụng không có ID ổn định và URL bị thay đổi liên tục khi đổi tiêu đề, hệ thống áp dụng kỹ thuật tính toán mã băm vân tay dựa trên các trường thông tin đặc trưng để nhận diện tin tuyển dụng.

---

### 1.4 Thiết Kế Mã Vân Tay Tin Tuyển Dụng
Hệ thống sử dụng song song hai loại mã băm SHA-256 để phân biệt giữa việc thay đổi định tính tin tuyển dụng và thay đổi nội dung chi tiết:

#### Mã vân tay định danh (identity_hash)
Mã băm này dùng để xác định "đây có phải là cùng một tin tuyển dụng logic hay không". Nó được tính toán dựa trên các trường thông tin cốt lõi, có tính ổn định cao và rất ít khi thay đổi trong suốt vòng đời tin:
* Tên nguồn tuyển dụng.
* Tên công ty đã được chuẩn hóa.
* Địa điểm làm việc đã được chuẩn hóa.
* Nhóm ngành nghề chuẩn hóa (job family).
* Nhóm mức lương (salary bucket).
* Nhóm yêu cầu kinh nghiệm (experience bucket).
* Danh sách các kỹ năng cốt lõi được sắp xếp theo thứ tự bảng chữ cái.

Tiêu đề đầy đủ không được đưa vào mã băm định danh này, vì chỉ cần một thay đổi nhỏ về tiêu đề (ví dụ thêm chữ "Tuyển gấp" hay ký tự đặc biệt) sẽ tạo ra một mã băm mới hoàn toàn, làm hệ thống hiểu nhầm là tin tuyển dụng mới.

#### Mã vân tay nội dung (content_hash)
Mã băm này dùng để kiểm tra xem nội dung chi tiết của tin tuyển dụng có bị thay đổi hay không. Nó được tính toán dựa trên toàn bộ các thông tin hiển thị có thể biến động:
* Tiêu đề công việc đã chuẩn hóa.
* Mô tả công việc đã chuẩn hóa.
* Yêu cầu công việc đã chuẩn hóa.
* Mức lương hiển thị dạng chữ.
* Yêu cầu kinh nghiệm dạng chữ.
* Hạn nộp hồ sơ.

Nếu trong một lần quét mới, hệ thống khớp được tin tuyển dụng qua mã vân tay định danh nhưng mã vân tay nội dung khác với bản ghi hiện tại, hệ thống xác định đây là một hành vi cập nhật nội dung (UPDATED) của cùng một tin tuyển dụng cũ chứ không tạo bài đăng mới.

---

### 1.5 Cơ Chế Tính Độ Tương Đồng (Similarity) Phát Hiện Thay Đổi Tiêu Đề
Trong trường hợp các trang web không cung cấp ID tin tuyển dụng và URL thay đổi liên tục, hệ thống sử dụng các tầng so sánh độ tương đồng để kiểm tra xem một tin tuyển dụng mới quét có phải là bản cập nhật tiêu đề của tin cũ hay không:

* **Tầng 1 - So sánh dựa trên quy tắc (Rule-based):** Hệ thống lọc ra các ứng viên có cùng công ty, cùng địa điểm, cùng nguồn tuyển dụng, cùng nhóm lương và kinh nghiệm. Sau đó tính tỷ lệ trùng lặp kỹ năng và tỷ lệ tương đồng Jaccard giữa hai chuỗi mô tả công việc. Nếu tỷ lệ trùng lặp kỹ năng lớn hơn 70% và độ tương đồng mô tả lớn hơn 80%, hệ thống coi là cùng một công việc.
* **Tầng 2 - Độ tương đồng Cosine của TF-IDF:** Chuyển đổi toàn bộ mô tả công việc của tin mới và các tin cũ của công ty đó thành các vector đặc trưng dựa trên trọng số TF-IDF, sau đó tính khoảng cách góc Cosine giữa các vector. Nếu điểm tương đồng lớn hơn 85%, tin tuyển dụng được xác định là cùng một vị trí tuyển dụng nhưng đã sửa tiêu đề.
* **Tầng 3 - Nhúng từ và câu (Sentence Embedding):** Sử dụng các mô hình ngôn ngữ nhẹ để tạo vector biểu diễn ngữ nghĩa cho tiêu đề và mô tả công việc, sau đó tính độ tương đồng vector. Đây là giải pháp nâng cao khi các giải pháp trên gặp sai số lớn, giúp hiểu được ngữ nghĩa tương đồng giữa "Data Engineer Intern" và "Thực tập sinh kỹ sư dữ liệu".

---

### 1.6 Quy Tắc Quyết Định Tin Mới hay Cập Nhật
Khi một tin tuyển dụng mới đi vào pipeline xử lý, hệ thống áp dụng bảng logic quyết định sau:

1. **Khớp mã định danh nguồn (source_job_id):** Nếu trùng mã định danh nguồn, đây chắc chắn là cùng một tin tuyển dụng. Tiến hành so sánh mã băm nội dung để quyết định có cập nhật lịch sử hay giữ nguyên.
2. **Khớp đường dẫn chuẩn hóa (canonical_url):** Nếu trùng đường dẫn chuẩn hóa, xác định là cùng một tin tuyển dụng. Tiến hành so sánh mã băm nội dung để cập nhật.
3. **Khớp mã vân tay định danh (identity_hash):** Nếu trùng mã vân tay định danh, hệ thống xem xét đây là tin tuyển dụng cũ. Kiểm tra xem mã băm nội dung có đổi không để cập nhật.
4. **Trùng công ty và có độ tương đồng cao:** Nếu không khớp các khóa trên nhưng có cùng công ty, cùng địa điểm và điểm tương đồng mô tả công việc qua TF-IDF lớn hơn 85%, xác định đây là cùng một tin tuyển dụng nhưng đã đổi tiêu đề hoặc đổi URL slug.
5. **Trùng tiêu đề nhưng khác công ty:** Xác định là hai tin tuyển dụng hoàn toàn khác nhau.
6. **Xuất hiện lại sau khi đã đóng:** Nếu tin tuyển dụng khớp định danh với một tin đã chuyển sang trạng thái CLOSED hoặc EXPIRED trước đó:
   * Nếu khoảng thời gian từ lúc đóng đến lúc xuất hiện lại dưới 14 ngày: Xác định tin tuyển dụng được mở lại (REOPENED), đặt cờ hoạt động về Đúng (true).
   * Nếu khoảng thời gian cách biệt lớn hơn 30 ngày: Xác định đây là một đợt tuyển dụng mới hoàn toàn (REPOSTED hoặc đợt tuyển mới), tạo một thực thể tin tuyển dụng mới để không làm sai lệch thời gian đo lường hiệu quả tuyển dụng của đợt cũ.

---

### 1.7 Cơ Chế Snapshot và Lưu Lịch Sử Thay Đổi
Hệ thống tuyệt đối không thực hiện ghi đè trực tiếp lên dữ liệu cũ khi phát hiện tin tuyển dụng có thay đổi nội dung (như đổi tiêu đề, đổi lương, đổi yêu cầu). Thay vào đó, hệ thống áp dụng kỹ thuật lưu trữ lịch sử thay đổi theo thời gian hiệu lực (SCD Type 2) thông qua bảng lịch sử phiên bản tin tuyển dụng (job_snapshots):

* Bảng tin tuyển dụng chính (`jobs`) chỉ lưu trữ thông tin định danh tĩnh (như ID nguồn, URL gốc, ID công ty, mã băm định danh) và trạng thái hiện tại cùng các mốc thời gian lần đầu nhìn thấy, lần cuối nhìn thấy.
* Mọi thông tin động như tiêu đề, mô tả công việc, mức lương, yêu cầu kinh nghiệm, hạn nộp hồ sơ và cờ hiệu lực hiện tại được tách riêng ra bảng phiên bản tin tuyển dụng (`job_snapshots`).
* Khi phát hiện có thay đổi nội dung (mã băm nội dung mới khác mã băm nội dung cũ của bản ghi đang hoạt động):
  1. Tiến hành cập nhật bản ghi phiên bản hiện tại trong bảng phiên bản: đặt cờ hoạt động hiện tại thành Sai (false) và thiết lập ngày hết hiệu lực là thời điểm hiện tại.
  2. Chèn một bản ghi phiên bản mới vào bảng phiên bản tin tuyển dụng: đặt cờ hoạt động hiện tại thành Đúng (true), thiết lập ngày bắt đầu hiệu lực là thời điểm hiện tại, ngày hết hiệu lực là rỗng, và lưu trữ các giá trị nội dung mới cùng mã băm nội dung mới.
  3. Cập nhật ngày nhìn thấy cuối cùng và trạng thái tin chính sang Đang hoạt động (ACTIVE) hoặc Đã cập nhật (UPDATED).

---

### 1.8 Quản Lý Tin Trùng Lặp Khác Nguồn (Cross-Source Duplicates)
Khi cùng một công ty đăng tuyển một vị trí công việc giống nhau lên nhiều trang web khác nhau (ví dụ: đăng cùng một tin lên cả TopCV, VietnamWorks và ITviec), hệ thống thực hiện gom cụm thay vì xóa bỏ:

* Mỗi tin tuyển dụng trên từng nguồn vẫn được giữ riêng biệt như một bản ghi độc lập trong bảng tin tuyển dụng chính để theo dõi vòng đời riêng (vì tin trên TopCV có thể hết hạn trước tin trên ITviec).
* Hệ thống thiết lập một bảng nhóm trùng lặp (`job_duplicate_groups`) lưu trữ mã nhóm và liên kết một tin tuyển dụng đại diện làm tin chuẩn (canonical job).
* Bảng thành viên nhóm trùng lặp (`job_duplicate_group_members`) sẽ liên kết tất cả các tin tuyển dụng trùng lặp khác nguồn vào mã nhóm này kèm theo điểm số tương đồng tương ứng.
* Khi hiển thị thông tin cho người dùng tìm kiếm, hệ thống chỉ truy vấn tin chuẩn đại diện và hiển thị kèm danh sách các nguồn tham chiếu khác.
* Khi phân tích báo cáo:
  * Nếu đếm số lượng tin đăng tuyển trên thị trường: thực hiện đếm trên toàn bộ các tin tuyển dụng nguồn.
  * Nếu đếm nhu cầu việc làm thực tế: thực hiện đếm theo mã nhóm trùng lặp để tránh số liệu bị thổi phồng.

---

## Chương 2: Xử Lý 30 Tình Huống Phát Sinh Thường Gặp

Dưới đây là cơ chế xử lý chi tiết đối với 30 tình huống thực tế phát sinh trong quá trình thu thập và đồng bộ dữ liệu tin tuyển dụng:

* **Tình huống 1: Tin tuyển dụng thay đổi tiêu đề (ví dụ từ "Data Engineer Intern" sang "Data Pipeline Intern")**
  * *Cách xử lý:* Hệ thống khớp tin qua mã định danh nguồn hoặc đường dẫn chuẩn hóa. Nhận diện thay đổi qua mã băm nội dung. Thực hiện đóng phiên bản lịch sử cũ trong bảng phiên bản và chèn phiên bản mới với tiêu đề mới, cờ hiệu lực hiện tại hoạt động. Ghi nhận sự kiện đổi tiêu đề vào bảng sự kiện.
* **Tình huống 2: Tin tuyển dụng thay đổi mức lương (ví dụ từ "3-5 triệu" sang "4-6 triệu")**
  * *Cách xử lý:* Khớp tin qua định danh tĩnh. Xác định mã băm nội dung thay đổi. Tạo phiên bản lịch sử mới lưu mức lương mới để phục vụ phân tích biến động lương thị trường theo thời gian.
* **Tình huống 3: Tin tuyển dụng gia hạn hoặc thay đổi hạn nộp hồ sơ**
  * *Cách xử lý:* Tạo phiên bản lịch sử mới chứa ngày hết hạn mới. Nếu trước đó tin tuyển dụng đang ở trạng thái Đã hết hạn (EXPIRED), hệ thống chuyển trạng thái tin chính về Đang hoạt động (ACTIVE) và xóa lý do hết hạn cũ.
* **Tình huống 4: Tin tuyển dụng thay đổi địa điểm làm việc (ví dụ từ "Hà Nội" thành "Hà Nội, Remote")**
  * *Cách xử lý:* Tạo phiên bản lịch sử mới. Cập nhật các liên kết địa điểm trong bảng liên kết nhiều-nhiều tương ứng với phiên bản mới này.
* **Tình huống 5: Tin tuyển dụng chứa nhiều địa điểm làm việc ngay từ đầu**
  * *Cách xử lý:* Hệ thống không lưu trữ dưới dạng một chuỗi văn bản gộp. Thay vào đó, phân tách địa điểm thành danh sách các mã địa điểm chuẩn hóa và lưu thành nhiều dòng liên kết trong bảng liên kết địa điểm tương ứng với phiên bản tin đó.
* **Tình huống 6: Tin tuyển dụng thay đổi yêu cầu kỹ năng (ví dụ yêu cầu thêm kỹ năng Airflow)**
  * *Cách xử lý:* Trích xuất lại danh sách kỹ năng từ mô tả mới. Tạo phiên bản lịch sử mới và ghi nhận các liên kết kỹ năng mới vào bảng liên kết kỹ năng theo mã phiên bản mới.
* **Tình huống 7: Tin tuyển dụng thay đổi mô tả chi tiết công việc nhưng giữ nguyên tiêu đề**
  * *Cách xử lý:* Khớp tin qua định danh tĩnh. Phát hiện mã băm nội dung khác biệt. Tạo phiên bản lịch sử mới lưu mô tả công việc mới.
* **Tình huống 8: Tin tuyển dụng hết hạn trên thực tế nhưng trang web nguồn vẫn hiển thị chi tiết bài đăng**
  * *Cách xử lý:* Khi quét trang chi tiết, bộ quét kiểm tra sự xuất hiện của các từ khóa báo hết hạn trong nội dung (ví dụ: "ngừng nhận hồ sơ", "hết hạn ứng tuyển"). Nếu phát hiện, chuyển trạng thái tin sang Đã hết hạn (EXPIRED) và tắt cờ hoạt động, bất kể trang web vẫn phản hồi mã trạng thái bình thường.
* **Tình huống 9: Tin tuyển dụng không còn xuất hiện trong trang danh sách quét nhưng đường dẫn chi tiết vẫn truy cập được bình thường và cho phép ứng tuyển**
  * *Cách xử lý:* Hệ thống vẫn duy trì trạng thái Đang hoạt động (ACTIVE) cho tin này, vì có thể trang danh sách đã ẩn tin do hết hạn đẩy tin hoặc thay đổi bộ lọc tìm kiếm của website nguồn.
* **Tình huống 10: Trang chi tiết tin tuyển dụng phản hồi mã lỗi 404 hoặc 410**
  * *Cách xử lý:* Nếu gặp lỗi này lần đầu, tăng trường đếm số lần không tìm thấy. Nếu gặp liên tiếp từ 2 đến 3 lần quét, chuyển trạng thái tin sang Đã đóng (CLOSED) và ghi nhận lý do đóng là lỗi trang chi tiết không tồn tại.
* **Tình huống 11: Đường dẫn tin tuyển dụng cũ thực hiện chuyển hướng (redirect) sang đường dẫn mới**
  * *Cách xử lý:* Cập nhật trường đường dẫn chuẩn hóa của tin tuyển dụng thành đường dẫn mới nhất. Ghi nhận lịch sử thay đổi đường dẫn vào bảng lịch sử URL để phục vụ đối chiếu nếu crawler sau này quét trúng URL cũ.
* **Tình huống 12: Trang web tái sử dụng đường dẫn cũ nhưng thay thế hoàn toàn bằng nội dung của công việc khác**
  * *Cách xử lý:* Nếu cùng một đường dẫn nhưng hệ thống tính toán độ tương đồng mô tả công việc mới so với phiên bản cũ dưới 40% và công ty tuyển dụng khác nhau, hệ thống xác định đây là hành vi tái sử dụng URL bất thường. Hệ thống sẽ giữ nguyên tin cũ ở trạng thái Đã đóng (CLOSED) và tạo một tin tuyển dụng mới hoàn toàn với URL này.
* **Tình huống 13: Tin tuyển dụng có cùng tiêu đề, cùng công ty nhưng khác cấp bậc tuyển dụng (ví dụ tuyển cùng lúc Intern và Junior)**
  * *Cách xử lý:* Nếu trích xuất được cấp bậc công việc rõ ràng khác nhau, hệ thống xác định đây là hai công việc độc lập và cấp hai mã định danh tin khác nhau trong cơ sở dữ liệu nghiệp vụ.
* **Tình huống 14: Tin tuyển dụng có cùng tiêu đề, cùng công ty nhưng đăng riêng lẻ cho các chi nhánh khác nhau**
  * *Cách xử lý:* Nếu các tin này có mã định danh nguồn hoặc đường dẫn khác nhau, hệ thống tạo các bản ghi riêng biệt nhưng gắn chúng vào cùng một nhóm trùng lặp để hiển thị tối ưu trên giao diện.
* **Tình huống 15: Tin tuyển dụng bị xuất hiện trùng lặp nhiều lần trên cùng một nguồn tin**
  * *Cách xử lý:* Sử dụng mã định danh nguồn duy nhất để loại bỏ trùng lặp ngay tại tầng staging trước khi nạp vào bảng nghiệp vụ.
* **Tình huống 16: Tên công ty xuất hiện dưới nhiều định dạng khác nhau (ví dụ: Công ty TNHH ABC, ABC Co., Ltd)**
  * *Cách xử lý:* Chuyển qua bộ lọc chuẩn hóa tên công ty (loại bỏ các từ khóa pháp lý như TNHH, Công ty, Cổ phần, Co Ltd). Sử dụng bảng bí danh công ty (company aliases) để quy đổi tất cả các tên viết khác nhau về một mã định danh công ty duy nhất.
* **Tình huống 17: Mức lương hiển thị không rõ ràng hoặc chứa ký tự đặc biệt (Thỏa thuận, Up to 15M, $500 - $800)**
  * *Cách xử lý:* Giữ nguyên văn bản thô để hiển thị. Đồng thời phân tích bằng biểu thức chính quy để tách thành mức lương tối thiểu, tối đa quy đổi về đơn vị tiền tệ chuẩn (VND) và phân loại kiểu lương (lương thỏa thuận, lương khoảng, lương tối đa). Nếu không thể phân tích, lưu giá trị rỗng cho các trường số và đặt cờ lương thỏa thuận.
* **Tình huống 18: Yêu cầu kinh nghiệm không ghi số năm cụ thể (Không yêu cầu, Ưu tiên có kinh nghiệm, Dưới 1 năm)**
  * *Cách xử lý:* Lưu văn bản thô và phân tích ra số năm tối thiểu, tối đa. Các cụm từ như "Không yêu cầu" hoặc "Dưới 1 năm" được quy đổi thành số năm tối thiểu là 0. Thiết lập các cờ tương ứng như cờ không yêu cầu kinh nghiệm, cờ ưu tiên kinh nghiệm.
* **Tình huống 19: Tiêu đề ghi tuyển dụng Fresher/Intern nhưng mô tả công việc yêu cầu từ 2 năm kinh nghiệm trở lên**
  * *Cách xử lý:* Hệ thống gắn cờ xung đột yêu cầu (conflict flag) và giảm mạnh điểm số thân thiện với sinh viên (student-friendly score) của tin này để không gợi ý sai cho đối tượng sinh viên thực tập.
* **Tình huống 20: Các tin tuyển dụng không thuộc lĩnh vực Công nghệ thông tin hoặc Dữ liệu lọt vào hệ thống do chứa từ khóa gây nhiễu (ví dụ tuyển nhân viên nhập liệu - Data Entry)**
  * *Cách xử lý:* Bộ phân loại ngành nghề kiểm tra tiêu đề và nội dung. Nếu tiêu đề chứa các từ khóa loại trừ (như nhập liệu, sale admin, lễ tân) và nội dung không chứa bất kỳ từ khóa kỹ thuật nào (như SQL, Python, database), tin tuyển dụng sẽ bị chuyển trạng thái không hợp lệ (INVALID) hoặc không đưa vào tầng phân tích.
* **Tình huống 21: Tin tuyển dụng sử dụng ngôn ngữ hỗn hợp Anh - Việt trong tiêu đề hoặc yêu cầu cấp bậc**
  * *Cách xử lý:* Sử dụng bộ từ điển đối chiếu song ngữ để chuẩn hóa các thuật ngữ cấp bậc (ví dụ: thực tập sinh, thực tập, intern, internship đều quy về nhóm cấp bậc thực tập sinh).
* **Tình huống 22: Bài đăng tích hợp tuyển dụng nhiều vị trí khác nhau trong cùng một nội dung mô tả**
  * *Cách xử lý:* Đối với phiên bản thử nghiệm đầu tiên (MVP), hệ thống giữ nguyên bài đăng dưới dạng một tin tuyển dụng duy nhất, gắn nhiều nhóm ngành nghề và nhiều kỹ năng tương ứng thay vì thực hiện phân tách tự động phức tạp dễ gây sai sót.
* **Tình huống 23: Tiêu đề tin tuyển dụng chứa nhiều từ khóa rác quảng cáo (Tuyển gấp, Lương cao đi làm ngay, Hấp dẫn)**
  * *Cách xử lý:* Bộ làm sạch tiêu đề sử dụng danh sách các từ khóa tiếp thị cần loại bỏ để cắt bỏ phần quảng cáo, trả lại tiêu đề công việc thực tế sạch sẽ trước khi lưu trữ và tính mã băm.
* **Tình huống 24: Bài đăng thiếu thông tin tên công ty tuyển dụng**
  * *Cách xử lý:* Nếu dữ liệu thô có tên công ty nhưng parser phân tích lỗi, hệ thống đánh dấu lỗi phân tích dữ liệu. Nếu nguồn tin thực sự ẩn tên công ty, hệ thống liên kết tin tuyển dụng với một bản ghi công ty ẩn danh đặc biệt trong cơ sở dữ liệu nghiệp vụ và gắn cờ cảnh báo chất lượng dữ liệu.
* **Tình huống 25: Tin tuyển dụng thiếu hoàn toàn mô tả công việc**
  * *Cách xử lý:* Tin tuyển dụng vẫn được lưu ở tầng staging để kiểm tra, nhưng sẽ không được đẩy lên tầng kho dữ liệu phân tích và các tầng phục vụ tìm kiếm nếu thiếu các trường thông tin tối thiểu bắt buộc như mô tả công việc.
* **Tình huống 26: Tin tuyển dụng bị trùng lặp URL do chứa các tham số theo dõi chiến dịch quảng cáo**
  * *Cách xử lý:* Trước khi tính toán đường dẫn chuẩn hóa, hệ thống thực hiện cắt bỏ toàn bộ các tham số bắt đầu bằng các tiếp đầu ngữ phổ biến như utm, ref, fbclid, gclid.
* **Tình huống 27: Website tuyển dụng đăng lại tin cũ nhưng cấp một mã định danh tin nguồn mới hoàn toàn**
  * *Cách xử lý:* Hệ thống kiểm tra trùng lặp thông qua mã băm định danh và điểm tương đồng mô tả công việc. Nếu trùng mã băm định danh và độ tương đồng mô tả trên 90%, hệ thống liên kết tin này thành phiên bản đăng lại của tin cũ thay vì coi là cơ hội việc làm mới độc lập.
* **Tình huống 28: Tin tuyển dụng bị gỡ bỏ ở nguồn này nhưng vẫn đang tuyển dụng ở nguồn khác**
  * *Cách xử lý:* Mỗi tin tuyển dụng theo nguồn có trạng thái vòng đời độc lập. Tin chuẩn đại diện của nhóm trùng lặp sẽ được duy trì hoạt động chừng nào còn ít nhất một tin tuyển dụng thành viên trong nhóm đang ở trạng thái hoạt động.
* **Tình huống 29: Giao diện website nguồn thay đổi đột ngột làm bộ phân tích parse sai thông tin (ví dụ tiêu đề bị parse thành rỗng)**
  * *Cách xử lý:* Bộ kiểm soát chất lượng dữ liệu theo dõi tỷ lệ phân tích lỗi theo thời gian thực. Nếu tỷ lệ tin thiếu tiêu đề hoặc thiếu công ty của một nguồn tăng đột biến vượt quá 30% trong ngày, hệ thống lập tức dừng nạp dữ liệu của nguồn đó lên tầng nghiệp vụ, phát cảnh báo hệ thống và giữ nguyên trạng thái cũ của các tin thuộc nguồn này trong cơ sở dữ liệu để tránh cập nhật sai hàng loạt.
* **Tình huống 30: Số lượng tin thu thập được giảm mạnh bất thường do lỗi phân trang của crawler**
  * *Cách xử lý:* Hệ thống so sánh số lượng tin quét được hôm nay với trung bình trượt 7 ngày gần nhất. Nếu lượng tin giảm bất thường, hệ thống khóa chức năng tự động tăng số lần không tìm thấy của ngày hôm đó để bảo vệ dữ liệu, tránh việc chuyển nhầm hàng loạt tin đang hoạt động sang trạng thái đóng.

---

## Chương 3: Thiết Kế Bảng Sự Kiện & Schema Cơ Sở Dữ Liệu Nghiệp Vụ (Silver/3NF)

Để vận hành trơn tru và hỗ trợ khả năng kiểm toán dòng chảy dữ liệu, hệ thống thiết kế cơ sở dữ liệu nghiệp vụ (Operational DB) theo chuẩn hóa 3NF chặt chẽ, kết hợp bảng ghi nhận sự kiện vòng đời.

### 3.1 Thiết Kế Bảng Sự Kiện Tin Tuyển Dụng (job_events)
Bảng này đóng vai trò nhật ký ghi lại mọi biến động trạng thái và nội dung của một tin tuyển dụng trong suốt vòng đời của nó. Bảng bao gồm các thông tin chính:
* **Mã sự kiện:** Khóa chính tăng tự động.
* **Mã tin tuyển dụng:** Khóa ngoại liên kết tới bảng tin chính.
* **Loại sự kiện:** Xác định loại biến động, bao gồm các sự kiện như: Phát hiện tin mới, Cập nhật tin, Thay đổi tiêu đề, Thay đổi mức lương, Thay đổi yêu cầu kinh nghiệm, Thay đổi địa điểm, Thay đổi kỹ năng, Tin hết hạn theo deadline, Tin bị đóng do không tìm thấy, Tin được mở lại, Phát hiện trùng lặp, Đánh dấu không hợp lệ, Thay đổi đường dẫn URL, Phát hiện phân tích bất thường.
* **Thời gian sự kiện:** Thời điểm ghi nhận biến động.
* **Mã nguồn tuyển dụng:** Tham chiếu nguồn phát sinh biến động.
* **Giá trị cũ:** Trường lưu trữ dạng tài liệu cấu trúc (JSONB) chứa các giá trị trước khi thay đổi.
* **Giá trị mới:** Trường lưu trữ dạng tài liệu cấu trúc (JSONB) chứa các giá trị sau khi thay đổi.
* **Lý do thay đổi:** Chuỗi văn bản mô tả nguyên nhân hệ thống đưa ra quyết định thay đổi trạng thái hoặc nội dung.

---

### 2.2 Schema Cơ Bản của Bảng Tin Tuyển Dụng (jobs)
Bảng này lưu trữ thực thể tin tuyển dụng ở mức logic độc lập với sự thay đổi nội dung:
* **Mã tin tuyển dụng (job_id):** Khóa chính tăng tự động.
* **Mã nguồn tuyển dụng (source_id):** Khóa ngoại liên kết bảng danh mục nguồn.
* **Mã định danh nguồn tin (source_job_id):** Mã ID do website gốc cung cấp (cho phép rỗng nhưng bắt buộc duy nhất kèm theo mã nguồn).
* **Đường dẫn chuẩn hóa (canonical_url):** Đường dẫn duy nhất của tin tuyển dụng sau khi làm sạch tham số theo dõi.
* **Mã công ty (company_id):** Khóa ngoại liên kết bảng danh mục công ty.
* **Mã vân tay định danh (identity_hash):** Chuỗi ký tự biểu diễn vân tay định danh của tin tuyển dụng.
* **Mã vân tay nội dung hiện tại (latest_content_hash):** Chuỗi ký tự biểu diễn vân tay nội dung phiên bản mới nhất.
* **Trạng thái tin tuyển dụng (job_status):** Trạng thái hiện tại của tin (ACTIVE, CLOSED, EXPIRED, v.v.).
* **Cờ hoạt động (is_active):** Giá trị logic thể hiện tin có đang hiển thị ứng tuyển hay không.
* **Thời điểm phát hiện đầu tiên (first_seen_at):** Thời gian lần đầu hệ thống quét thấy tin.
* **Thời điểm nhìn thấy cuối cùng (last_seen_at):** Thời gian gần nhất hệ thống xác nhận tin vẫn tồn tại trên nguồn.
* **Thời điểm đóng tin (closed_at):** Thời gian tin bị chuyển sang trạng thái CLOSED.
* **Thời điểm hết hạn (expired_at):** Thời gian tin hết hạn theo hạn nộp hồ sơ.
* **Số lần không tìm thấy (not_found_count):** Số lần quét thành công liên tiếp không thấy tin này.
* **Lý do ngừng hoạt động (inactive_reason):** Ghi chú nguyên nhân tin bị đóng hoặc hết hạn.
* **Mã nhóm trùng lặp (duplicate_group_id):** Khóa ngoại liên kết bảng nhóm trùng lặp nếu có.
* **Thời điểm tạo bản ghi (created_at) & Thời điểm cập nhật bản ghi (updated_at).**

---

## Chương 4: Quy Trình Xử Lý Pipeline Hằng Ngày

Luồng xử lý dữ liệu được thiết kế chạy tự động định kỳ mỗi ngày qua 16 bước nghiêm ngặt:

1. **Quét dữ liệu danh sách tin (Crawl listing):** Thu thập danh sách các tin tuyển dụng mới và đường dẫn từ các trang danh mục của các nguồn tin.
2. **Quét kiểm tra trang chi tiết (Crawl details):** Tải nội dung chi tiết của các tin tuyển dụng mới phát hiện và các tin tuyển dụng đang ở trạng thái hoạt động cần đối soát.
3. **Nạp dữ liệu thô vào vùng đệm (Parse raw to staging):** Phân tích cú pháp HTML/JSON thô chuyển đổi thành cấu trúc dữ liệu chung của vùng đệm staging.
4. **Chuẩn hóa trường dữ liệu (Normalize fields):** Làm sạch văn bản, chuẩn hóa địa điểm, phân tích lương và số năm kinh nghiệm về dạng số chuẩn.
5. **Tạo các mã định danh và mã băm (Generate hashes):** Tính toán đường dẫn chuẩn hóa, mã vân tay định danh và mã vân tay nội dung cho từng tin tuyển dụng mới quét.
6. **Khớp nối dữ liệu lịch sử (Match existing jobs):** Đối chiếu tin mới quét với cơ sở dữ liệu nghiệp vụ bằng mã định danh nguồn, đường dẫn chuẩn hóa hoặc mã vân tay định danh.
7. **Phân loại hành động xử lý (Classify incoming jobs):** Xác định tin tuyển dụng thuộc nhóm tin mới hoàn toàn, tin trùng lặp, tin cập nhật nội dung hay tin được mở lại.
8. **Cập nhật thông tin thực thể tin chính (Update jobs table):** Thực hiện ghi nhận thông tin trạng thái mới và làm mới thời điểm nhìn thấy cuối cùng cho các tin được xác nhận vẫn tồn tại.
9. **Quản lý lịch sử phiên bản (Insert snapshots):** Nếu tin có thay đổi mã băm nội dung, đóng phiên bản cũ và ghi nhận phiên bản mới vào bảng phiên bản tin tuyển dụng.
10. **Cập nhật nhật ký biến động (Log events):** Chèn các bản ghi mô tả biến động tương ứng vào bảng sự kiện tin tuyển dụng.
11. **Ghi nhận số lần không tìm thấy (Track missing jobs):** Đối với các tin tuyển dụng đang hoạt động nhưng không xuất hiện trong lượt quét hôm nay của nguồn tin đó, thực hiện tăng số lần không tìm thấy lên 1.
12. **Xử lý đóng tin tự động (Auto-close jobs):** Chuyển trạng thái sang CLOSED đối với các tin tuyển dụng có số lần không tìm thấy vượt ngưỡng quy định.
13. **Xử lý hết hạn tự động (Auto-expire jobs):** Chuyển trạng thái sang EXPIRED đối với các tin tuyển dụng có ngày hết hạn nhỏ hơn ngày hiện tại.
14. **Gom cụm tin trùng lặp khác nguồn (Group cross-source duplicates):** Thực hiện tính toán độ tương đồng giữa các tin hoạt động của các nguồn khác nhau để liên kết vào nhóm trùng lặp.
15. **Nạp dữ liệu vào kho phân tích (Load Warehouse):** Thực hiện chuyển đổi và nạp dữ liệu sạch từ tầng nghiệp vụ sang các bảng Fact và Dimension của kho dữ liệu.
16. **Kiểm tra chất lượng dữ liệu cuối cùng (Run quality checks):** Đánh giá các chỉ số bất thường về số lượng tin, tỷ lệ lỗi phân tích để xác nhận độ tin cậy của lượt chạy.

*Lưu ý quan trọng:* Các bước xử lý đóng tin và tăng số lần không tìm thấy (bước 11 - 13) chỉ được phép kích hoạt nếu lượt quét của nguồn tin đó được hệ thống ghi nhận là thành công và vượt qua vòng kiểm tra chất lượng dữ liệu. Nếu lượt quét bị lỗi hệ thống hoặc bị chặn giữa chừng, toàn bộ tiến trình cập nhật tin biến mất của nguồn đó sẽ được tạm dừng để bảo vệ tính toàn vẹn dữ liệu.

---

## Chương 5: Phân Biệt 3 Lớp Dữ Liệu (3NF DB → DWH → Data Mart)

Để tối ưu hóa hiệu năng lưu trữ và đáp ứng các mục đích sử dụng khác nhau từ vận hành hệ thống đến báo cáo phân tích, hệ thống phân chia rõ ràng thành ba lớp dữ liệu riêng biệt trên nền tảng PostgreSQL:

```
[Operational DB / 3NF DB] (Silver Schema)
          ↓
  [Data Warehouse] (DWH Schema - Star Schema)
          ↓
     [Data Marts] (Mart Schema - Optimized Views/Tables)
```

### 5.1 Vai Trò của Từng Lớp Dữ Liệu

* **Operational DB / 3NF DB (Lớp Nghiệp Vụ - Silver Schema):**
  * *Mục tiêu:* Phục vụ vận hành trực tiếp cho pipeline dữ liệu, đảm bảo dữ liệu ghi nhanh, không trùng lặp thông tin nhờ cấu trúc chuẩn hóa cao độ (3NF).
  * *Đặc điểm:* Dữ liệu phân rã thành nhiều bảng chuyên biệt liên kết với nhau bằng khóa ngoại. Lưu trữ chi tiết lịch sử thay đổi thông qua snapshot và sự kiện. Không tối ưu cho các truy vấn tính toán tổng hợp lớn.
* **Data Warehouse (Kho Dữ Liệu - DWH Schema):**
  * *Mục tiêu:* Phục vụ lưu trữ dữ liệu phân tích tập trung, hỗ trợ truy vấn lịch sử lâu dài và đa chiều.
  * *Đặc điểm:* Tổ chức theo mô hình hình sao (Star Schema) với một bảng Fact chính ở trung tâm liên kết với các bảng Dimension xung quanh. Dữ liệu tại đây đã được làm sạch hoàn toàn, chuyển đổi thành các khóa số để tăng tốc độ quét dữ liệu lớn và hạn chế tối đa các phép toán join phức tạp.
* **Data Marts (Phân Vùng Phục Vụ - Mart Schema):**
  * *Mục tiêu:* Cung cấp dữ liệu đã được tính toán sẵn, tinh gọn, tối ưu riêng cho từng ứng dụng downstream cụ thể như báo cáo PowerBI, dịch vụ tìm kiếm nhanh (Search API), hệ thống khuyến nghị (Recommendation), hoặc ứng dụng Web hiển thị tin hoạt động.
  * *Đặc điểm:* Dữ liệu thường được denormalize (khử chuẩn hóa) thành các bảng phẳng đơn giản hoặc materialized view để các ứng dụng đọc trực tiếp với hiệu năng cực cao mà không cần join hay tính toán lại từ đầu.

### 5.2 Lựa Chọn PostgreSQL Làm Kho Dữ Liệu và Phân Vùng schemas
Trong phạm vi dự án này, hệ thống sử dụng PostgreSQL làm hệ quản trị cơ sở dữ liệu chung cho cả ba lớp nhờ tính linh hoạt, khả năng hỗ trợ lập chỉ mục tìm kiếm văn bản đầy đủ (Full-Text Search) mạnh mẽ, và khả năng kết nối trực tiếp mượt mà với PowerBI và các API. Các lớp dữ liệu được phân chia vật lý thông qua các schema riêng biệt trong cùng một database:
* Schema `raw`: Lưu trữ siêu dữ liệu quét và lịch sử trạng thái chạy của crawler.
* Schema `staging`: Vùng đệm để chuyển đổi cấu trúc dữ liệu thô sang cấu trúc chung.
* Schema `silver` (hoặc `operational`): Chứa cơ sở dữ liệu nghiệp vụ chuẩn hóa 3NF có quản lý vòng đời và lịch sử thay đổi.
* Schema `dwh`: Chứa kho dữ liệu mô hình hình sao phục vụ phân tích đa chiều.
* Schema `mart`: Chứa các bảng dữ liệu tinh gọn phục vụ trực tiếp cho các consumer cuối.

---

## Chương 6: Thiết Kế Data Warehouse (dwh)

Kho dữ liệu tại schema `dwh` được thiết kế theo mô hình hình sao để tối ưu hóa việc phân tích xu hướng tuyển dụng, nhu cầu kỹ năng và biến động lương.

### 6.1 Bảng Fact Trung Tâm: fact_job_posting
Mỗi dòng trong bảng Fact đại diện cho trạng thái hiện hành hoặc một phiên bản nội dung của một tin tuyển dụng tại thời điểm nạp dữ liệu vào kho. Bảng Fact chứa các trường thông tin chính:
* **Mã khóa bảng Fact (job_posting_fact_id):** Khóa chính tăng tự động.
* **Mã tin tuyển dụng nghiệp vụ (job_id):** Khóa tham chiếu ngược về lớp nghiệp vụ.
* **Mã phiên bản tin tuyển dụng (job_snapshot_id):** Khóa tham chiếu ngược về phiên bản nội dung cụ thể.
* **Khóa ngày (date_key):** Khóa ngoại liên kết bảng chiều thời gian.
* **Khóa công ty (company_key):** Khóa ngoại liên kết bảng chiều công ty (hỗ trợ lưu lịch sử công ty theo SCD Type 2).
* **Khóa nguồn tuyển dụng (source_key):** Khóa ngoại liên kết bảng chiều nguồn tin.
* **Khóa cấp bậc công việc (job_level_key):** Khóa ngoại liên kết bảng chiều cấp bậc (Intern, Fresher, Junior...).
* **Khóa loại hình làm việc (job_type_key):** Khóa ngoại liên kết bảng chiều loại hình (Full-time, Part-time...).
* **Khóa hình thức làm việc (work_mode_key):** Khóa ngoại liên kết bảng chiều hình thức (Onsite, Hybrid, Remote).
* **Các trường đo lường số lượng (Measures):**
  * Mức lương tối thiểu quy đổi (salary_min).
  * Mức lương tối đa quy đổi (salary_max).
  * Mức lương trung bình quy đổi (salary_avg).
  * Số năm kinh nghiệm yêu cầu tối thiểu (experience_min_years).
  * Số năm kinh nghiệm yêu cầu tối đa (experience_max_years).
  * Số lượng kỹ năng yêu cầu trong bài đăng (skill_count).
  * Số ngày tin tuyển dụng duy trì trạng thái hoạt động (active_days).
* **Các cờ logic phân tích nhanh:** Cờ tin thực tập (is_intern), cờ tin mới tốt nghiệp (is_fresher), cờ không yêu cầu kinh nghiệm (is_no_experience), cờ tin thân thiện với sinh viên (is_student_friendly), cờ tin đang hoạt động (is_active).
* **Thời điểm nạp dữ liệu vào kho (loaded_at).**

---

### 6.2 Các Bảng Chiều (Dimensions)

* **Chiều Ngày (dim_date):** Khóa ngày dạng số nguyên biểu diễn năm tháng ngày. Lưu trữ các thuộc tính ngày đầy đủ, năm, quý, tháng, tuần, ngày trong tháng, ngày trong tuần, và cờ xác định ngày cuối tuần để phân tích xu hướng tuyển dụng theo mùa hoặc theo các ngày trong tuần.
* **Chiều Công Ty (dim_company):** Lưu trữ thông tin công ty phục vụ phân tích xu hướng tuyển dụng theo ngành nghề doanh nghiệp, quy mô công ty. Bảng này áp dụng cơ chế lưu trữ lịch sử SCD Type 2 để theo dõi sự thay đổi quy mô hoặc ngành nghề của công ty theo thời gian.
* **Chiều Nguồn Tuyển Dụng (dim_source):** Lưu trữ danh mục các nguồn tuyển dụng (TopCV, ITviec...) để phân tích chất lượng và số lượng tin của từng nguồn.
* **Chiều Địa Điểm (dim_location):** Danh mục các tỉnh thành, quận huyện được chuẩn hóa để phân tích bản đồ địa lý việc làm.
* **Chiều Kỹ Năng (dim_skill):** Danh mục các kỹ năng kỹ thuật được phân nhóm theo các nhóm công nghệ lớn (như nhóm Lập trình, Cơ sở dữ liệu, Điện toán đám mây, Công cụ điều phối).
* **Chiều Cấp Bậc (dim_job_level):** Danh mục cấp bậc chuẩn hóa (Intern, Fresher, Junior, Senior, Lead...).
* **Chiều Loại Hình (dim_type):** Phân loại loại hình hợp đồng làm việc.
* **Chiều Hình Thức Làm Việc (dim_work_mode):** Phân loại các hình thức làm việc thực tế.

---

### 6.3 Bảng Cầu Nối (Bridge Tables)
Do một tin tuyển dụng có thể yêu cầu nhiều kỹ năng khác nhau và có thể làm việc tại nhiều địa điểm khác nhau, hệ thống sử dụng các bảng cầu nối để giải quyết mối quan hệ nhiều-nhiều mà không làm phình to bảng Fact chính:

* **Bảng cầu nối kỹ năng (bridge_job_skill):** Liên kết mã khóa bảng Fact với khóa bảng chiều kỹ năng. Ghi nhận thêm độ tự tin của thuật toán trích xuất kỹ năng và phương pháp trích xuất (trích xuất dựa trên quy tắc hay trích xuất bằng mô hình ngôn ngữ).
* **Bảng cầu nối địa điểm (bridge_job_location):** Liên kết mã khóa bảng Fact với khóa bảng chiều địa điểm đối với các công việc tuyển dụng làm việc tại nhiều chi nhánh thành phố khác nhau.

---

## Chương 7: Thiết Kế Các Data Marts (mart)

Tầng Data Mart tại schema `mart` chứa các bảng phẳng đã được tính toán sẵn số liệu tổng hợp hoặc tổ chức dữ liệu theo cấu trúc đặc thù để cung cấp dữ liệu tức thì cho các ứng dụng đầu cuối.

### 7.1 Mart Tổng Quan Thị Trường (mart.bi_job_overview_daily)
Bảng này tính toán sẵn các chỉ số tổng hợp theo từng ngày, nguồn tin, địa điểm và cấp bậc để phục vụ hiển thị các biểu đồ tổng quan trên PowerBI mà không cần PowerBI thực hiện tính toán trên bảng Fact lớn:
* **Thuộc tính phân nhóm:** Khóa ngày, ngày đầy đủ, tên nguồn tin, tên thành phố chuẩn hóa, cấp bậc chuẩn hóa, loại hình công việc chuẩn hóa.
* **Các chỉ số tính sẵn:** Tổng số tin tuyển dụng tích lũy, số lượng tin đang hoạt động, số lượng tin mới phát hiện trong ngày, số lượng tin hết hạn trong ngày, số lượng tin bị đóng trong ngày, số lượng tin thân thiện với sinh viên.

---

### 7.2 Mart Nhu Cầu Kỹ Năng (mart.bi_skill_demand_daily)
Bảng chuyên biệt phục vụ phân tích xu hướng kỹ năng công nghệ nào đang được thị trường săn đón:
* **Thuộc tính phân nhóm:** Khóa ngày, ngày đầy đủ, tên kỹ năng, nhóm kỹ năng công nghệ, cấp bậc công việc, thành phố làm việc.
* **Các chỉ số tính sẵn:** Số lượng bài đăng yêu cầu kỹ năng này, số lượng tin yêu cầu kỹ năng này đang hoạt động, mức lương tối thiểu trung bình của các tin yêu cầu kỹ năng này, mức lương tối đa trung bình tương ứng.

---

### 7.3 Mart Phân Tích Mức Lương (mart.bi_salary_analysis)
Bảng tổng hợp phục vụ xây dựng các biểu đồ phân bố lương, so sánh lương giữa các khu vực và kỹ năng:
* **Thuộc tính phân nhóm:** Khóa ngày, nhóm ngành nghề chuẩn hóa, cấp bậc công việc, thành phố làm việc, nhóm mức lương phân khoảng (ví dụ: từ 3-5 triệu, từ 5-8 triệu, lương thỏa thuận).
* **Các chỉ số tính sẵn:** Mức lương tối thiểu thấp nhất và trung bình, mức lương tối đa cao nhất và trung bình, mức lương trung bình của nhóm công việc, tổng số lượng tin tuyển dụng nằm trong khoảng lương này.

---

### 7.4 Mart Chất Lượng Nguồn Tin (mart.bi_source_quality_daily)
Bảng phục vụ riêng cho đội ngũ kỹ sư dữ liệu theo dõi sức khỏe của pipeline quét dữ liệu và chất lượng dữ liệu thô thu thập được từ các nguồn:
* **Thuộc tính phân nhóm:** Khóa ngày, tên nguồn tuyển dụng.
* **Các chỉ số vận hành:** Số lượng lượt chạy crawl thành công trong ngày, tổng số trang đã quét, tổng số tin tuyển dụng tìm thấy, số lượng tin mới được nạp vào hệ thống, số lượng tin bị lỗi phân tích cú pháp, tỷ lệ tin thiếu tiêu đề, tỷ lệ tin thiếu tên công ty, tỷ lệ tin thiếu thông tin lương, tỷ lệ tin trùng lặp nội dung, thời gian chạy trung bình của bộ quét.

---

### 7.5 Mart Tìm Kiếm Việc Làm (mart.search_job_documents)
Bảng phẳng được thiết kế đặc thù cho công cụ tìm kiếm toàn văn (Full-Text Search) trên ứng dụng Web API. Bảng này loại bỏ hoàn toàn các liên kết join phức tạp và tích hợp chỉ mục vector tìm kiếm:
* **Thông tin văn bản hiển thị:** Mã tin tuyển dụng, mã phiên bản hiện tại, tiêu đề công việc, tên công ty, tên nguồn tuyển dụng, danh sách các thành phố làm việc dạng chuỗi phân tách bởi dấu phẩy, văn bản lương hiển thị, mức lương tối thiểu và tối đa dạng số, văn bản kinh nghiệm hiển thị, số năm kinh nghiệm tối thiểu và tối đa dạng số, chuỗi danh sách kỹ năng yêu cầu phân tách bởi khoảng trắng, cấp bậc công việc, loại hình công việc, hình thức làm việc, nội dung mô tả công việc thô đã loại bỏ mã HTML.
* **Cờ lọc nhanh:** Cờ tin hoạt động (is_active), cờ tin thân thiện sinh viên (is_student_friendly).
* **Thông tin thời gian:** Ngày đăng tin, ngày hết hạn tin, thời điểm cập nhật bản ghi tìm kiếm.
* **Trường chỉ mục tìm kiếm (search_vector):** Kiểu dữ liệu chỉ mục tìm kiếm toàn văn của PostgreSQL (TSVECTOR) được gộp và tính toán trọng số từ tiêu đề công việc (trọng số cao nhất), tên công ty, kỹ năng và mô tả công việc. Chỉ mục này được tăng tốc bằng chỉ mục ngược GIN (Generalized Inverted Index) để phản hồi kết quả tìm kiếm từ khóa trong mili giây.

---

### 7.6 Mart Đặc Trưng Khuyến Nghị (mart.recommendation_job_features)
Bảng chuyên biệt cung cấp các thuộc tính đầu vào được tính toán sẵn cho hệ thống khuyến nghị việc làm sử dụng thuật toán máy học hoặc so khớp độ tương đồng:
* **Định danh:** Mã tin tuyển dụng, mã phiên bản hiện tại.
* **Các thuộc tính phân loại:** Nhóm ngành nghề chuẩn hóa, cấp bậc công việc, thành phố làm việc, cờ làm việc từ xa (is_remote), cờ thân thiện với sinh viên.
* **Các thuộc tính số học:** Số năm kinh nghiệm tối thiểu và tối đa, mức lương tối thiểu và tối đa quy đổi.
* **Mảng đặc trưng:** Mảng danh sách mã kỹ năng (skills array), mảng danh sách mã nhóm kỹ năng (skill groups array).
* **Điểm số chất lượng tính sẵn:** Điểm độ tươi mới của tin tuyển dụng (freshness score - giảm dần theo thời gian kể từ ngày đăng), điểm độ thân thiện với sinh viên (student-friendly score - tính dựa trên cấp bậc thực tập/fresher và yêu cầu kinh nghiệm thực tế).
* **Văn bản tổng hợp phục vụ nhúng vector:** Chuỗi văn bản gộp chứa tiêu đề, kỹ năng và các yêu cầu cốt lõi phục vụ mô hình nhúng câu (embedding models) để tính toán vector đặc trưng.

---

### 7.7 Mart Tin Tuyển Dụng Đang Hoạt Động (mart.web_active_jobs)
Bảng phẳng tinh gọn nhất phục vụ trực tiếp cho trang chủ website tuyển dụng, chỉ chứa các tin tuyển dụng đang mở ứng tuyển và thân thiện với đối tượng người dùng đích. Bảng này giúp API truy vấn cực nhanh không cần thực hiện bất kỳ phép lọc trạng thái hay join bảng nào trên cơ sở dữ liệu:
* **Các trường lưu trữ:** Mã tin tuyển dụng, tiêu đề công việc, tên công ty, tên thành phố, văn bản lương hiển thị, cấp bậc chuẩn hóa, tên nguồn tuyển dụng, ngày đăng tin, ngày hết hạn tin, đường dẫn ứng tuyển trực tiếp.
* Toàn bộ các bản ghi trong bảng này luôn được đảm bảo có cờ hoạt động là Đúng (true) và cờ thân thiện với sinh viên là Đúng (true).

---

## Chương 8: Lỗi Thường Gặp & Bộ Quy Tắc MVP

Để triển khai hệ thống quản lý vòng đời tin tuyển dụng thành công ngay từ phiên bản đầu tiên, nhóm phát triển cần nhận diện các sai lầm kinh điển và áp dụng bộ quy tắc tinh gọn.

### 8.1 Các Lỗi Thiết Kế Hệ Thống Cần Tránh
* **Ghi đè trực tiếp dữ liệu (Update-in-place):** Sai lầm lớn nhất là cập nhật đè tiêu đề hoặc mức lương mới lên bản ghi cũ của bảng tin tuyển dụng. Điều này làm mất hoàn toàn lịch sử biến động thị trường và làm sai lệch các báo cáo phân tích xu hướng lương của Data Warehouse.
* **Đóng tin tuyển dụng hàng loạt do lỗi crawler:** Khi crawler bị chặn hoặc gặp lỗi mạng và chỉ thu thập được một lượng tin rất nhỏ, hệ thống hiểu nhầm các tin không thấy là đã đóng và chuyển hàng loạt tin sang CLOSED. Điều này gây tàn phá dữ liệu nghiêm trọng. Luôn phải kiểm tra tính toàn vẹn của lượt chạy trước khi chạy logic đóng tin.
* **Khử trùng lặp quá mức (Over-deduplication):** Việc tự ý gộp hoặc xóa các tin tuyển dụng giống nhau ở các nguồn khác nhau làm mất đi thông tin đặc thù của từng nguồn (như thông tin lương chỉ có trên TopCV, thông tin hạn nộp chỉ có trên VietnamWorks). Phải giữ nguyên dữ liệu gốc của từng nguồn và quản lý qua cơ chế gom nhóm trùng lặp.
* **Tin tưởng tuyệt đối vào tiêu đề bài đăng:** Nhiều tin tuyển dụng ghi tiêu đề tuyển "Fresher Data Engineer" nhưng trong nội dung mô tả lại yêu cầu từ 2 đến 3 năm kinh nghiệm thực tế. Nếu hệ thống chỉ phân loại dựa trên tiêu đề, các gợi ý việc làm cho đối tượng mới ra trường sẽ chứa rất nhiều tin rác không phù hợp.

---

### 8.2 Bộ Quy Tắc Tinh Gọn Cho Phiên Bản MVP
Đối với giai đoạn khởi đầu của dự án, để hệ thống không bị quá phức tạp nhưng vẫn đảm bảo độ tin cậy nền tảng, nhóm phát triển cần tuân thủ bộ quy tắc cốt lõi sau:
1. Thực hiện so khớp tin tuyển dụng mới bằng cặp khóa mã nguồn tuyển dụng và mã định danh nguồn tin (`source_id` + `source_job_id`) nếu website có cung cấp ID.
2. Nếu trang web không cung cấp ID, thực hiện so khớp bằng đường dẫn chuẩn hóa đã loại bỏ tham số theo dõi (`canonical_url`).
3. Nếu đường dẫn khác biệt, thực hiện so khớp mềm bằng tổ hợp thông tin: cùng nguồn, cùng tên công ty chuẩn hóa, cùng tiêu đề chuẩn hóa và cùng địa điểm chuẩn hóa.
4. Khi khớp được tin cũ và phát hiện mã băm nội dung mới khác mã băm nội dung cũ, tiến hành đóng hiệu lực phiên bản cũ và chèn một dòng phiên bản mới vào bảng phiên bản tin tuyển dụng.
5. Khi một tin tuyển dụng đang hoạt động không xuất hiện trong lượt quét thành công của nguồn tin đó, tăng chỉ số không tìm thấy thêm 1.
6. Khi chỉ số không tìm thấy liên tiếp đạt từ 3 lần trở lên, chính thức chuyển trạng thái tin sang Đã đóng (CLOSED) và tắt cờ hoạt động.
7. Khi ngày hiện tại vượt quá ngày hạn nộp hồ sơ được ghi nhận, chuyển trạng thái tin sang Đã hết hạn (EXPIRED).
8. Nếu một tin tuyển dụng đã đóng xuất hiện trở lại trong vòng 14 ngày kể từ ngày đóng, chuyển trạng thái tin về Đang hoạt động (ACTIVE) và ghi nhận sự kiện mở lại (REOPENED).
9. Nếu các tin tuyển dụng hoạt động của các nguồn khác nhau có cùng công ty và độ tương đồng mô tả công việc lớn hơn 85%, tiến hành liên kết chúng vào cùng một nhóm trùng lặp (`duplicate_group`).
10. Trên giao diện người dùng và dịch vụ tìm kiếm thông thường, chỉ truy xuất các tin tuyển dụng có cờ hoạt động là Đúng (true) và cờ thân thiện với sinh viên là Đúng (true).

---

## Chương 9: Lượng Tử Hóa & Đo Lường Hiệu Suất Vận Hành

Để đảm bảo các kỹ thuật tối ưu hóa cơ sở dữ liệu và pipeline thực sự mang lại hiệu quả, hệ thống triển khai bộ chỉ số theo dõi hiệu năng (telemetry) tại mỗi tầng vận hành:

### 9.1 Các Chỉ Số Telemetry Theo Dõi Từng Tầng
* **Tầng Thu Thập (Extract/Ingestion):** Theo dõi thời gian chạy của từng scraper (phút), lượng bộ nhớ RAM tiêu thụ tối đa (MB), tỷ lệ request thành công/thất bại (%), và kích thước tệp tin thô được ghi lên storage (MB).
* **Tầng Nghiệp Vụ (Silver/3NF DB):** Theo dõi thời gian thực thi các thủ tục so khớp tin tuyển dụng (giây), tỷ lệ cache hit của bộ normalize tên công ty, số lượng bản ghi được xử lý trên giây (throughput), và số lượng tin tuyển dụng mới/cũ/cập nhật được phân loại trong mỗi lượt chạy.
* **Tầng Kho Dữ Liệu (Data Warehouse):** Theo dõi thời gian thực thi của tiến trình ETL/ELT nạp dữ liệu vào bảng Fact và Dimension (giây), lượng dữ liệu scan trong DuckDB/PostgreSQL khi thực hiện incremental load (MB), và tỷ lệ nén của các phân vùng lưu trữ Parquet.
* **Tầng Phục Vụ (Data Marts & APIs):** Theo dõi thời gian làm mới các materialized view hoặc nạp các bảng phẳng (phút), thời gian phản hồi trung bình của API tìm kiếm việc làm (mili giây), tỷ lệ sử dụng chỉ mục GIN trên trường tìm kiếm toàn văn (`search_vector`), và số lượng kết nối đồng thời mà cơ sở dữ liệu có thể đáp ứng ổn định.

### 9.2 Các Chỉ Số Đánh Giá Tối Ưu Hóa Database
Hệ thống thực hiện giám sát định kỳ các chỉ số hiệu năng PostgreSQL thông qua các báo cáo thống kê nội bộ:
* **Index Usage Rate (Tỷ lệ sử dụng chỉ mục):** Tỷ lệ các câu lệnh SELECT sử dụng index quét dữ liệu thay vì quét tuần tự toàn bộ bảng (Sequential Scan). Mục tiêu đạt trên 95% đối với các bảng lớn như `job_snapshots` và `fact_job_posting`.
* **Cache Hit Ratio (Tỷ lệ trúng bộ nhớ đệm):** Tỷ lệ dữ liệu được đọc trực tiếp từ bộ nhớ đệm RAM (Shared Buffers) của PostgreSQL thay vì phải đọc từ ổ đĩa cứng. Mục tiêu duy trì ổn định trên 99% để đảm bảo tốc độ truy xuất tối đa.
* **Slow Query Log (Nhật ký truy vấn chậm):** Ghi lại toàn bộ các câu lệnh SQL có thời gian thực thi vượt quá 100 mili giây để tiến hành phân tích kế hoạch thực thi (EXPLAIN ANALYZE) và bổ sung chỉ mục hoặc viết lại câu lệnh tối ưu hơn.
