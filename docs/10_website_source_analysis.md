# Website Source Analysis Log

Tai lieu nay dung de phan tich nguon tung website (portal) theo tung dot cap nhat. Moi khi ban gui thong tin moi, minh se bo sung vao file nay de giu lich su tap trung.

---

## Template cap nhat cho moi portal

| Truong | Noi dung |
|---|---|
| Portal | |
| Domain | |
| Endpoint list/detail | |
| Thu vien / cong cu fetch | |
| Muc do anti-bot | |
| Trang thai implementation | |
| Nguon thong tin | |
| Ghi chu ky thuat | |

### Checklist phan tich

- Da xac dinh URL list va quy luat pagination.
- Da xac dinh selector lay danh sach job URL.
- Da xac dinh selector cho cac truong detail chinh.
- Da co quy tac chuan hoa URL (neu co relative URL).
- Da co danh gia rui ro anti-bot va giai phap fallback.
- Da xac dinh strategy retry/rate-limit.

---

## 1. CareerViet

| Truong | Noi dung |
|---|---|
| Portal | CareerViet |
| Domain | `careerviet.vn` |
| Endpoint list/detail | List: `https://careerviet.vn/viec-lam/cntt-phan-mem-tai-ha-noi-c1l4-vi.html`; Detail pattern: `https://careerviet.vn/vi/tim-viec-lam/<slug>.<id>.html` |
| Thu vien / cong cu fetch | Scrapling |
| Muc do anti-bot | Trung binh |
| Trang thai implementation | File `src/extract/careerviet.py` moi co comment metadata, chua co logic parse |
| Nguon thong tin | `src/extract/careerviet.py` + thong tin HTML thuc te user cung cap (2026-03-07) |
| Ghi chu ky thuat | Da co URL list, selector job link, pagination pattern va dieu kien dung crawl |

### Thong tin da co

- Portal: CareerViet (`careerviet.vn`).
- Thu vien du kien: Scrapling.
- URL list mau: `https://careerviet.vn/viec-lam/cntt-phan-mem-tai-ha-noi-c1l4-vi.html`.
- Selector link job o list page: `a.job_link::attr(href)`.
- Mau HTML link job:

```html
<a class="job_link" data-id="35C6273E" target="_blank" title="Sales Admin( Fresher Are Welcome)" rel="noopener noreferrer" href="/vi/tim-viec-lam/sales-admin-fresher-are-welcome.35C6273E.html">Sales Admin( Fresher Are Welcome)</a>
```

- Quy tac pagination URL:
	- Page 1: `.../cntt-phan-mem-tai-ha-noi-c1l4-vi.html`
	- Page 2: `.../cntt-phan-mem-tai-ha-noi-c1l4-trang-2-vi.html`
	- Page 3: `.../cntt-phan-mem-tai-ha-noi-c1l4-trang-3-vi.html`
- Nut next tren UI: `li.next-page a` (icon span class `mdi mdi-chevron-right`).
- Quy tac dung crawl:
	- Dung khi page hien tai khong co them link job moi.
	- Hoac truy cap trang tiep theo nhung khong lay duoc job moi.
	- Hoac trang tiep theo khong con bat ky `a.job_link` nao.
- Danh gia anti-bot ban dau: trung binh.

### Quy tac parse/deploy de xuat

- Trich xuat links:
	- CSS: `a.job_link::attr(href)`.
	- Chuan hoa thanh absolute URL bang `make_absolute_url(href, "https://careerviet.vn")`.
- Xu ly phan trang:
	- Uu tien click/doi URL theo mau `-trang-{n}-`.
	- Kiem tra nut next bang selector `li.next-page a`.
- Dung crawl an toan:
	- Theo doi `seen_urls` va `new_urls_count` moi page.
	- Neu `new_urls_count == 0` trong 1 page thi break.
	- Neu tong links page == 0 thi break ngay.

### Khoang trong thong tin (cho lan cap nhat tiep theo)

- Selector detail cho: `title`, `company`, `salary`, `location`, `job_description`, `requirements`, `benefits`, `job_deadline`.
- Co che fallback khi selector chinh thay doi.
- Cach xu ly truong hop can JS render / can Playwright fallback.
- Rules retry/rate-limit toi uu cho CareerViet trong production.

### Checklist hien tai

- Da xac dinh URL list va quy luat pagination: Da.
- Da xac dinh selector lay danh sach job URL: Da (`a.job_link::attr(href)`).
- Da xac dinh selector cho cac truong detail chinh: Chua.
- Da co quy tac chuan hoa URL: Da (relative -> absolute voi base `https://careerviet.vn`).
- Da co danh gia rui ro anti-bot va giai phap fallback: Mot phan (chi co muc do anti-bot).
- Da xac dinh strategy retry/rate-limit: Mot phan (da co dieu kien dung crawl, chua co thong so retry cu the).

---

## 2. ITViec

| Truong | Noi dung |
|---|---|
| Portal | ITViec |
| Domain | `itviec.com` |
| Endpoint list/detail | List: `https://itviec.com/it-jobs/ha-noi`; list URL co query dong `job_selected` (khong dung lam key co dinh) |
| Thu vien / cong cu fetch | Scrapling HTTP (uu tien), Selenium/Playwright fallback khi can render UI preview |
| Muc do anti-bot | Thap -> Trung binh |
| Trang thai implementation | File `src/extract/itviec.py` moi co metadata comment, chua co logic parse |
| Nguon thong tin | HTML/list URL thuc te user cung cap (2026-03-07) |
| Ghi chu ky thuat | Da xac dinh URL dong, pagination `page=`, next button, va selector lay job link tu card |

### Thong tin da co

- URL list quan sat duoc:
	- `https://itviec.com/it-jobs/ha-noi?click_source=Navigation+menu&job_selected=...`
	- `https://itviec.com/it-jobs/ha-noi?click_source=Navigation+menu&job_selected=`
- Ket luan ve URL:
	- `job_selected` la tham so dong (vao trang se auto chon job dau tien), khong phai phan URL list tinh.
	- Canonical list URL de crawl nen la `https://itviec.com/it-jobs/ha-noi` (bo query dong neu khong can).
- Phan trang UI:
	- Container: `nav.ipagination`
	- Nut next: `div.page.next a[rel='next']`
	- Link phan trang mau: `/it-jobs/ha-noi?...&page=2&query=&source=search_job`
- Mau URL page quan sat duoc:
	- `...&page=2`
	- `...&page=3`
	- Co the di kem `job_selected=...` hoac `job_selected=`.
- Selector link job tren card (uu tien):
	- Card: `div.job-card[data-search--job-selection-job-url-value]`
	- Attr: `data-search--job-selection-job-url-value` (dang `/it-jobs/<slug>/content?...`)
- Selector link job fallback:
	- `h3[data-url]::attr(data-url)` (thuong la URL detail day du).
- Selector link detail khi selected (open new tab):
	- Anchor: `a[data-controller='utm-tracking'][target='_blank'][href*='/it-jobs/']::attr(href)`
	- Tieu de trong panel: `h2.text-it-black.text-hover-red::text`
	- Mau href quan sat: `/it-jobs/android-developer-middle-senior-ingenico-vietnam-0230?lab_feature=preview_jd_page`

### Quy tac parse/deploy de xuat

- Chuan hoa URL list:
	- Bat dau tu `https://itviec.com/it-jobs/ha-noi`.
	- Loai bo/khong phu thuoc query `job_selected` vi day la state UI.
- Trich xuat link job:
	- Uu tien doc `data-search--job-selection-job-url-value` tu `div.job-card`.
	- Fallback sang `h3[data-url]` khi attr tren card thay doi.
	- Neu da click selected panel, co the lay URL tu anchor `a[target='_blank'][href*='/it-jobs/']` trong panel detail de lay canonical slug job.
	- Chuan hoa relative URL thanh absolute URL voi base `https://itviec.com`.
	- Loai bo query tracking nhu `lab_feature=preview_jd_page`, `click_source`, `job_selected` de dedup ben vung hon.
	- Neu link dang `/content?...`, normalize ve URL job goc `/it-jobs/<slug>` uu tien hon URL content.
- Xu ly phan trang:
	- Uu tien parse `a[rel='next']::attr(href)` trong `div.page.next`.
	- Fallback tang `page=n` theo quy tac URL neu selector next thay doi.
- Dung crawl an toan:
	- Theo doi `seen_urls` va `new_urls_count` theo tung trang.
	- Break neu trang hien tai co `0` job link hop le.
	- Break neu sang trang tiep theo nhung `new_urls_count == 0`.
	- Break neu khong tim thay `a[rel='next']` va khong sinh duoc URL page tiep theo.

### Khoang trong thong tin (cho lan cap nhat tiep theo)

- Selector detail page on dinh cho: `company`, `salary`, `location`, `job_description`, `requirements`, `benefits`, `job_industry`.
- Rule xu ly truong hop salary bi an (`Sign in to view salary`) cho output schema.
- Co che fallback khi endpoint/content page doi cau truc (`/content?...` vs URL detail goc).
- Rules retry/rate-limit toi uu cho ITViec trong production.

### Checklist hien tai

- Da xac dinh URL list va quy luat pagination: Da.
- Da xac dinh selector lay danh sach job URL: Da (`div.job-card[data-search--job-selection-job-url-value]` + fallback `h3[data-url]`).
- Da xac dinh selector cho cac truong detail chinh: Mot phan (da co selector title + detail href khi selected).
- Da co quy tac chuan hoa URL: Da (bo phu thuoc `job_selected`, relative -> absolute, can normalize query tracking).
- Da co danh gia rui ro anti-bot va giai phap fallback: Mot phan.
- Da xac dinh strategy retry/rate-limit: Mot phan (da co dieu kien dung crawl, chua co thong so retry cu the).

---

## 3. Job123

| Truong | Noi dung |
|---|---|
| Portal | Job123 |
| Domain | `123job.vn` |
| Endpoint list/detail | List mau: `https://123job.vn/tuyen-dung?s=0&jt=0&cat=IT+phan+mem&sort=new&type_keyword=0&cityId=1&q=&l=Ha+Noi&city`; Detail pattern: `https://123job.vn/viec-lam/<slug>?codePosition=...` |
| Thu vien / cong cu fetch | Scrapling HTTP (uu tien), co the fallback browser automation neu can |
| Muc do anti-bot | Thap -> Trung binh |
| Trang thai implementation | File `src/extract/job_123.py` moi co metadata comment, chua co logic parse |
| Nguon thong tin | HTML/list URL/pagination user cung cap (2026-03-08) |
| Ghi chu ky thuat | Da xac dinh selector link job, mau URL phan trang `page=`, va nut next |

### Thong tin da co

- URL list quan sat duoc:
	- `https://123job.vn/tuyen-dung?s=0&jt=0&cat=IT+ph%E1%BA%A7n+m%E1%BB%81m&sort=new&type_keyword=0&cityId=1&q=&l=H%C3%A0+N%E1%BB%99i&city`
- Ket luan ve URL list:
	- URL de crawl on dinh co the dung bo query thua, giu key chinh: `cat`, `l`, `sort`, `cityId`.
	- Canonical list URL de crawl de xuat: `https://123job.vn/tuyen-dung?cat=IT+ph%E1%BA%A7n+m%E1%BB%81m&l=H%C3%A0+N%E1%BB%99i&sort=new&cityId=1`.
- Selector link job tren list page:
	- Wrapper title: `h2.job__list-item-title`
	- Link: `h2.job__list-item-title a::attr(href)`
	- Mau link detail: `https://123job.vn/viec-lam/java-developer-KqLa2AQlD1?codePosition=C1`
- Phan trang UI:
	- Container: `ul.pagination-listing`
	- URL page mau: `https://123job.vn/tuyen-dung?cat=IT+ph%E1%BA%A7n+m%E1%BB%81m&l=H%C3%A0+N%E1%BB%99i&sort=new&cityId=1&page=2`
	- Nut next: `ul.pagination-listing li a[aria-label='Next']`
	- Thuoc tinh next dang quan sat: `rel='Next'`, icon `i.la.la-angle-right`

### Quy tac parse/deploy de xuat

- Chuan hoa URL list:
	- Bat dau tu canonical URL co `cat`, `l`, `sort`, `cityId`.
	- Khong phu thuoc cac query khong can thiet nhu `s`, `jt`, `type_keyword`, `q`, `city` khi crawl production.
- Trich xuat link job:
	- Uu tien `h2.job__list-item-title a::attr(href)`.
	- Chuan hoa relative -> absolute voi base `https://123job.vn` (neu phat sinh relative URL).
	- De-dup theo URL da normalize, can nhac bo query tracking neu khong anh huong noi dung (`codePosition` can duoc danh gia giu/bo sau).
- Xu ly phan trang:
	- Uu tien parse next URL tu `a[aria-label='Next']::attr(href)`.
	- Fallback tang `page=n` theo query string khi selector next thay doi.
- Dung crawl an toan:
	- Theo doi `seen_urls` va `new_urls_count` moi page.
	- Break neu trang hien tai co `0` job link hop le.
	- Break neu sang trang tiep theo nhung `new_urls_count == 0`.
	- Break neu khong tim thay next URL va khong tao duoc URL page tiep theo.

### Khoang trong thong tin (cho lan cap nhat tiep theo)

- Selector detail page on dinh cho: `title`, `company`, `salary`, `location`, `job_description`, `requirements`, `benefits`, `job_deadline`.
- Danh gia xem `codePosition` co phai query tracking hay co anh huong canonical detail URL.
- Co che fallback khi list page can JS render trong mot so thoi diem.
- Rules retry/rate-limit toi uu cho Job123 trong production.

### Checklist hien tai

- Da xac dinh URL list va quy luat pagination: Da.
- Da xac dinh selector lay danh sach job URL: Da (`h2.job__list-item-title a::attr(href)`).
- Da xac dinh selector cho cac truong detail chinh: Chua.
- Da co quy tac chuan hoa URL: Da (de xuat canonical list URL + normalize absolute URL).
- Da co danh gia rui ro anti-bot va giai phap fallback: Mot phan.
- Da xac dinh strategy retry/rate-limit: Mot phan (da co dieu kien dung crawl, chua co thong so retry cu the).

---

## 4. Joboko

| Truong | Noi dung |
|---|---|
| Portal | Joboko |
| Domain | `vn.joboko.com` |
| Endpoint list/detail | List: `https://vn.joboko.com/jobs?l=2&ind=124`; Detail pattern: `https://vn.joboko.com/viec-lam-<slug>-xvi<id>` |
| Thu vien / cong cu fetch | Scrapling HTTP (uu tien), co the fallback browser automation neu can |
| Muc do anti-bot | Thap -> Trung binh |
| Trang thai implementation | File `src/extract/joboko.py` moi co metadata comment, chua co logic parse |
| Nguon thong tin | HTML list card + link detail + nut xem them user cung cap (2026-03-08) |
| Ghi chu ky thuat | Da xac dinh selector link job, selector link xem chi tiet, va pagination kieu load-more qua query `p=` |

### Thong tin da co

- URL list quan sat duoc:
	- `https://vn.joboko.com/jobs?l=2&ind=124`
- Selector link job tren list page:
	- Tieu de card: `h2.item-title`
	- Link: `h2.item-title a::attr(href)`
	- Mau href: `/viec-lam-chuyen-vien-tu-van-dau-tu-sale-dau-tu-lam-tai-long-bien-xvi6329176`
- Selector link xem chi tiet trong card:
	- `a.block-detail::attr(href)`
	- Mau href: `/viec-lam-giao-vien-tieng-anh-online-lich-linh-hoat-thu-nhap-hap-dan-den-20-trieu-xvi6280934`
- Co che phan trang / xem them:
	- Wrapper: `div.nw-job-list__more`
	- Nut xem them: `div.nw-job-list__more a.btn.btn-nw-success-ol::attr(href)`
	- Mau next href: `/jobs?l=2&ind=124&p=2`
	- Query phan trang dang quan sat: `p=<n>`

### Quy tac parse/deploy de xuat

- Chuan hoa URL list:
	- Bat dau tu canonical URL: `https://vn.joboko.com/jobs?l=2&ind=124`.
	- Dung query `p=n` cho pagination thay vi phu thuoc click UI.
- Trich xuat link job:
	- Uu tien `h2.item-title a::attr(href)`.
	- Fallback `a.block-detail::attr(href)` khi title card thay doi.
	- Chuan hoa relative -> absolute voi base `https://vn.joboko.com`.
	- De-dup theo URL detail da normalize.
- Xu ly pagination:
	- Uu tien parse next URL tu nut xem them `div.nw-job-list__more a.btn.btn-nw-success-ol`.
	- Fallback tang `p=n` neu khong tim thay nut xem them nhung van con du lieu.
	- Dung khi khong con nut xem them hoac page tiep theo khong tra ve link job moi.
- Dung crawl an toan:
	- Theo doi `seen_urls` va `new_urls_count` theo tung page.
	- Break neu page hien tai co `0` link job hop le.
	- Break neu `new_urls_count == 0` o page tiep theo.

### Khoang trong thong tin (cho lan cap nhat tiep theo)

- Selector detail page on dinh cho: `title`, `company`, `salary`, `location`, `job_description`, `requirements`, `benefits`, `job_deadline`.
- Xac minh job links co bao gio doi sang absolute URL ngay tren list page hay khong.
- Kiem tra co co che load-more bang XHR/API ngầm hay chi can request URL `p=`.
- Rules retry/rate-limit toi uu cho Joboko trong production.

### Checklist hien tai

- Da xac dinh URL list va quy luat pagination: Da.
- Da xac dinh selector lay danh sach job URL: Da (`h2.item-title a::attr(href)` + fallback `a.block-detail::attr(href)`).
- Da xac dinh selector cho cac truong detail chinh: Chua.
- Da co quy tac chuan hoa URL: Da (relative -> absolute voi base `https://vn.joboko.com`).
- Da co danh gia rui ro anti-bot va giai phap fallback: Mot phan.
- Da xac dinh strategy retry/rate-limit: Mot phan (da co dieu kien dung crawl, chua co thong so retry cu the).

---

## 5. JobsGO

| Truong | Noi dung |
|---|---|
| Portal | JobsGO |
| Domain | `jobsgo.vn` |
| Endpoint list/detail | List: `https://jobsgo.vn/viec-lam-cong-nghe-thong-tin-tai-ha-noi.html`; Detail pattern: `https://jobsgo.vn/viec-lam/<slug>-<id>.html` |
| Thu vien / cong cu fetch | Scrapling HTTP (uu tien), co the fallback browser automation neu can |
| Muc do anti-bot | Thap -> Trung binh |
| Trang thai implementation | File `src/extract/jobsgo.py` moi co metadata comment, chua co logic parse |
| Nguon thong tin | HTML list card + pagination user cung cap (2026-03-08) |
| Ghi chu ky thuat | Da xac dinh card selector, link detail tren card, query phan trang `page=`, va nut next |

### Thong tin da co

- URL list quan sat duoc:
	- `https://jobsgo.vn/viec-lam-cong-nghe-thong-tin-tai-ha-noi.html`
- Selector link job tren list page:
	- Card: `div.card.job-card`
	- Link detail tren card: `div.card.job-card a.text-decoration-none::attr(href)`
	- Tieu de job tham chieu: `h3.job-title`
	- Mau href: `https://jobsgo.vn/viec-lam/nhan-vien-kinh-doanh-du-an-thiet-bi-dien-lgtech-luong-cung-10-15-trieu-hoa-hong-25737229230.html`
- Phan trang UI:
	- Container: `ul.pagination`
	- URL page mau: `https://jobsgo.vn/viec-lam-cong-nghe-thong-tin-tai-ha-noi.html?page=2`
	- Nut next: `li.next a::attr(href)`
	- Mau next href quan sat: `/viec-lam-cong-nghe-thong-tin-tai-ha-noi.html?page=3`

### Quy tac parse/deploy de xuat

- Chuan hoa URL list:
	- Bat dau tu canonical URL: `https://jobsgo.vn/viec-lam-cong-nghe-thong-tin-tai-ha-noi.html`.
	- Dung query `page=n` cho pagination.
- Trich xuat link job:
	- Uu tien `div.card.job-card a.text-decoration-none::attr(href)`.
	- Fallback theo tieu de card: `h3.job-title` -> anchor cha gan nhat.
	- Chuan hoa relative -> absolute voi base `https://jobsgo.vn`.
	- De-dup theo URL detail da normalize.
- Xu ly phan trang:
	- Uu tien parse next URL tu `li.next a::attr(href)`.
	- Fallback tang `page=n` neu selector next thay doi nhung van con du lieu.
	- Dung khi `li.next` bi disabled/khong ton tai, hoac page tiep theo khong co job moi.
- Dung crawl an toan:
	- Theo doi `seen_urls` va `new_urls_count` moi page.
	- Break neu page hien tai co `0` link job hop le.
	- Break neu `new_urls_count == 0` o page tiep theo.

### Khoang trong thong tin (cho lan cap nhat tiep theo)

- Selector detail page on dinh cho: `title`, `company`, `salary`, `location`, `job_description`, `requirements`, `benefits`, `job_deadline`.
- Xac minh co nhieu anchor trong card hay khong de tranh lay nham URL (neu class CSS thay doi).
- Kiem tra co query tracking o detail URL can loai bo khi dedup hay khong.
- Rules retry/rate-limit toi uu cho JobsGO trong production.

### Checklist hien tai

- Da xac dinh URL list va quy luat pagination: Da.
- Da xac dinh selector lay danh sach job URL: Da (`div.card.job-card a.text-decoration-none::attr(href)`).
- Da xac dinh selector cho cac truong detail chinh: Chua.
- Da co quy tac chuan hoa URL: Da (relative -> absolute voi base `https://jobsgo.vn`).
- Da co danh gia rui ro anti-bot va giai phap fallback: Mot phan.
- Da xac dinh strategy retry/rate-limit: Mot phan (da co dieu kien dung crawl, chua co thong so retry cu the).
