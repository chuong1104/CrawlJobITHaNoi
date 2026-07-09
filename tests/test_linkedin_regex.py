import unittest
from src.extract.linkedin import LinkedInScraperV2

class TestLinkedInRegex(unittest.TestCase):
    def setUp(self):
        self.scraper = LinkedInScraperV2()

    def test_parse_job_detail_regex_fallbacks(self):
        mock_html = """
        <html>
        <head>
          <title>Senior Data Engineer at Google | LinkedIn</title>
        </head>
        <body>
          <h1 class="jobs-unified-top-card__job-title">Senior Data Engineer</h1>
          <div class="jobs-unified-top-card__company-name">Google</div>
          <div id="job-details">
            <h3>Mô tả công việc</h3>
            Chúng tôi đang tìm kiếm một ứng viên phù hợp tham gia đội ngũ.
            
            Yêu cầu công việc:
            - Có tối thiểu 3 năm kinh nghiệm làm việc với Spark, Hadoop.
            - Kỹ năng tiếng Anh tốt.
            
            Thông tin khác:
            - Địa điểm làm việc: Làm việc tại Hà Nội, Việt Nam.
            - Hình thức: Hybrid (kết hợp làm việc từ xa và tại văn phòng).
            - Mức lương: upto 3000 USD / tháng tùy năng lực.
            - Hạn nộp: trước ngày 30/12/2026.
          </div>
        </body>
        </html>
        """
        
        # Gọi parse_job_detail
        parsed = self.scraper.parse_job_detail(mock_html, "https://www.linkedin.com/jobs/view/123456")
        
        # In kết quả kiểm thử để người dùng xem trực quan
        print("\n--- Parsed Mock Job ---")
        for k, v in parsed.items():
            if k != "job_description":
                print(f"{k}: {v}")
                
        # Kiểm tra tiêu đề và công ty
        self.assertEqual(parsed["title"], "Senior Data Engineer")
        self.assertEqual(parsed["company"], "Google")
        
        # Kiểm tra các trường được trích xuất bằng regex từ description
        self.assertIsNotNone(parsed["salary"])
        self.assertIn("3000 USD", parsed["salary"])
        
        self.assertIsNotNone(parsed["location"])
        self.assertEqual(parsed["location"], "Hà Nội")
        
        self.assertIsNotNone(parsed["experience_level"])
        self.assertIn("3 năm", parsed["experience_level"])
        
        self.assertIsNotNone(parsed["job_type"])
        self.assertEqual(parsed["job_type"], "Hybrid")
        
        self.assertIsNotNone(parsed["job_position"])
        self.assertEqual(parsed["job_position"], "Senior")
        
        self.assertIsNotNone(parsed["job_deadline"])
        self.assertEqual(parsed["job_deadline"], "30/12/2026")

if __name__ == "__main__":
    unittest.main()
