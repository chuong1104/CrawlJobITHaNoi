# Schemas - Định nghĩa schema chuẩn cho một Job record (dùng Pydantic v2)
#
# JobSchema fields:
# - job_id         : str  (hash unique: source + job_url)
# - source         : str  (tên portal: "topcv", "itviec", ...)
# - title          : str
# - company        : str
# - location       : str  (tên tỉnh/thành chuẩn)
# - salary_min     : int | None  (VND)
# - salary_max     : int | None  (VND)
# - salary_currency: str  ("VND" | "USD")
# - job_type       : str  (FULL_TIME | PART_TIME | CONTRACT | REMOTE)
# - level          : str  (INTERN | FRESHER | JUNIOR | MID | SENIOR | LEAD | MANAGER)
# - skills         : list[str]
# - description    : str
# - requirements   : str
# - benefits       : str
# - posted_date    : date
# - deadline       : date | None
# - job_url        : str
# - scraped_at     : datetime
