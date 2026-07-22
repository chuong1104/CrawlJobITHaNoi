import re
from typing import Optional

class FallbackRegexExtractor:
    """
    Utility class to extract all possible job fields from a raw combined text block 
    (like a single job description containing requirements, benefits, company info).
    Supports both English and Vietnamese.
    """

    @classmethod
    def extract_title(cls, text: str) -> Optional[str]:
        patterns = [
            r'(?:vị\s+trí(?:\s+tuyển\s+dụng)?|tuyển\s+dụng|chức\s+danh|job\s+title|position|role)\s*[:\-]?\s*([^\n]{5,100})'
        ]
        for pat in patterns:
            m = re.search(pat, text[:1500], re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    @classmethod
    def extract_company(cls, text: str) -> Optional[str]:
        patterns = [
            r'(?:công\s+ty|company(?:\s+name)?|hiring\s+company)\s*[:\-]?\s*([^\n]{3,100})'
        ]
        for pat in patterns:
            m = re.search(pat, text[:1500], re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    @classmethod
    def extract_salary(cls, text: str) -> Optional[str]:
        patterns = [
            r'(?:lương|mức\s+lương|thu\s+nhập|thù\s+lao|mức\s+thu\s+nhập|chế\s+độ\s+lương)\s*[:\-]?\s*([0-9\s,\.\-~]+(?:triệu|tr|triệu/tháng|vnd|vnđ|usd|\$|k|nghìn|ngàn))',
            r'(?:lương|mức\s+lương|thu\s+nhập|thù\s+lao|mức\s+thu\s+nhập)\s*[:\-]?\s*(?:upto|lên\s+đến|up\s+to|tối\s+đa)\s+[0-9\s,\.\-~]+(?:triệu|tr|vnd|vnđ|usd|\$|k|nghìn|ngàn)',
            r'(?:lương|mức\s+lương|thu\s+nhập|thù\s+lao|mức\s+thu\s+nhập)\s*[:\-]?\s*(?:thỏa\s+thuận|cạnh\s+tranh|negotiable|thương\s+lượng)',
            r'(?:từ|lên\s+đến|up\s+to|upto)\s+(\d+[\.,]?\d*\s*(?:triệu|tr|vnd|vnđ|usd|\$))',
            r'(?:\d+[\.,]\d+\s*[-–~]\s*\d+[\.,]\d+)\s*(?:triệu|million|tr|k|nghìn|ngàn)\s*(?:VNĐ|VND|đ|VND/tháng|usd)?',
            r'(?:\d+\s*[-–~]\s*\d+)\s*(?:triệu|million|tr|k|nghìn|ngàn)\s*(?:VNĐ|VND|đ|VND/tháng|usd)?',
            r'(?:salary|compensation|pay|remuneration|wage|base\s+salary)\s*[:\-]?\s*([\$\€\£]\s*[\d,\.]+(?:\s*[-–~]\s*[\$\€\£]?\s*[\d,\.]+)?\s*(?:/\s*(?:hr|hour|month|year|yr|tháng|năm))?)',
            r'(?:salary|compensation|pay|remuneration|wage|base\s+salary)\s*[:\-]?\s*([^\n]{5,50})'
        ]
        search_text = text[:3000]
        for pat in patterns:
            m = re.search(pat, search_text, re.IGNORECASE)
            if m:
                snippet = m.group(1).strip() if len(m.groups()) > 0 and m.group(1) else m.group(0).strip()
                snippet = re.sub(r'^(?:lương|mức\s+lương|thu\s+nhập|thù\s+lao|mức\s+thu\s+nhập|chế\s+độ\s+lương|salary|compensation|pay|remuneration|wage|base\s+salary)\s*[:\-]?\s*', '', snippet, flags=re.IGNORECASE).strip()
                if snippet and len(snippet) < 60:
                    return snippet
        return None

    @classmethod
    def extract_location(cls, text: str) -> Optional[str]:
        patterns = [
            r'(?:địa\s+điểm(?:\s+làm\s+việc)?|nơi\s+làm\s+việc|làm\s+việc\s+tại|location|work\s+location)\s*[:\-]?\s*([^\n]{5,100})'
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    @classmethod
    def extract_experience(cls, text: str) -> Optional[str]:
        patterns = [
            r'(?:từ\s+|tối\s+thiểu\s+|ít\s+nhất\s+)?(\d+\s*[-–~]\s*\d+|\d+\+?)\s*năm(?:\s+kinh\s+nghiệm|\s+làm\s+việc)?',
            r'(?:kinh\s+nghiệm|yêu\s+cầu\s+kinh\s+nghiệm)\s*[:\-]?\s*(?:từ\s+|tối\s+thiểu\s+|ít\s+nhất\s+)?(\d+\s*[-–~]\s*\d+|\d+\+?)\s*năm?',
            r'(?:có|yêu\s+cầu)?\s*(?:ít\s+nhất|tối\s+thiểu)?\s*(\d+\s*[-–~]\s*\d+|\d+\+?)\s*năm\s+(?:kinh\s+nghiệm|làm\s+việc)',
            r'(\d+\s*[-–~]\s*\d+|\d+\+?)\s*years?(?:\s+of)?\s+(?:working\s+|relevant\s+|industry\s+)?experience',
            r'(?:minimum|at\s+least|min\.?)\s+(?:of\s+)?(\d+\s*[-–~]\s*\d+|\d+\+?)\s*years?(?:\s+of)?\s+(?:working\s+|relevant\s+|industry\s+)?experience',
            r'experience\s*[:\-]?\s*(?:minimum\s+)?(\d+\s*[-–~]\s*\d+|\d+\+?)\s*years?',
            r'(?:kinh\s+nghiệm|yêu\s+cầu\s+kinh\s+nghiệm)\s*[:\-]?\s*(không\s+yêu\s+cầu|chưa\s+có\s+kinh\s+nghiệm|dưới\s+1\s+năm)',
            r'(không\s+yêu\s+cầu\s+kinh\s+nghiệm|chấp\s+nhận\s+sinh\s+viên\s+mới\s+ra\s+trường|chấp\s+nhận\s+fresher)',
            r'(no\s+experience\s+required|entry[- ]level|fresh\s+graduate)'
        ]
        search_text = text[:3000]
        for pat in patterns:
            m = re.search(pat, search_text, re.IGNORECASE)
            if m:
                snippet = m.group(1).strip() if len(m.groups()) > 0 and m.group(1) else m.group(0).strip()
                snippet = re.sub(r'\s+', ' ', snippet)
                if re.match(r'^\d+\s*[-–~]\s*\d+$', snippet):
                    parts = re.split(r'[-–~]', snippet)
                    return f"{parts[0].strip()} - {parts[1].strip()} năm"
                elif re.match(r'^\d+\+?$', snippet):
                    return f"{snippet} năm"
                return snippet
        return None

    @classmethod
    def extract_job_type(cls, text: str) -> Optional[str]:
        patterns = [
            r'(?i)\b(full[- ]time|part[- ]time|contract|freelance|internship|remote|hybrid|on[- ]site|toàn\s+thời\s+gian|bán\s+thời\s+gian|thực\s+tập|thời\s+vụ|cộng\s+tác\s+viên|ctv)\b'
        ]
        for pat in patterns:
            m = re.search(pat, text[:1500], re.IGNORECASE)
            if m:
                val = m.group(1).lower().replace(" ", "-")
                mapping = {
                    "toàn-thời-gian": "Full-time", "bán-thời-gian": "Part-time", "thực-tập": "Internship",
                    "thời-vụ": "Contract", "cộng-tác-viên": "Freelance", "ctv": "Freelance",
                    "full-time": "Full-time", "part-time": "Part-time", "contract": "Contract",
                    "freelance": "Freelance", "internship": "Internship", "remote": "Remote",
                    "hybrid": "Hybrid", "on-site": "On-site"
                }
                return mapping.get(val, val.title())
        return None

    @classmethod
    def extract_job_industry(cls, text: str) -> Optional[str]:
        patterns = [
            r'(?:lĩnh\s+vực|ngành\s+nghề|industry|sector)\s*[:\-]?\s*([^\n]{3,50})'
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    @classmethod
    def extract_job_position(cls, text: str) -> Optional[str]:
        patterns = [
            r'(?i)\b(intern|internship|fresher|junior|mid[- ]level|middle|senior|lead|manager|director|head|vp|thực\s+tập\s+sinh|thực\s+tập|mới\s+tốt\s+nghiệp|trưởng\s+nhóm|trưởng\s+phòng|quản\s+lý|giám\s+đốc|nhân\s+viên)\b'
        ]
        for pat in patterns:
            m = re.search(pat, text[:1500], re.IGNORECASE)
            if m:
                val = m.group(1).lower().replace(" ", "-")
                mapping = {
                    "thực-tập": "Intern", "thực-tập-sinh": "Intern", "internship": "Intern",
                    "mới-tốt-nghiệp": "Fresher", "trưởng-nhóm": "Lead", "trưởng-phòng": "Manager",
                    "quản-lý": "Manager", "giám-đốc": "Director", "nhân-viên": "Staff", "mid-level": "Middle"
                }
                return mapping.get(val, val.title())
        return None

    @classmethod
    def extract_requirements(cls, text: str) -> Optional[str]:
        """Bóc tách khối văn bản Yêu cầu / Requirements"""
        vi_headers = [r'(?:\*\s*)?yêu\s+cầu\s*(?:công\s+việc|ứng\s+viên|kinh\s+nghiệm)?\s*:?', r'(?:\*\s*)?tiêu\s+chuẩn\s*(?:ứng\s+viên)?\s*:?', r'(?:\*\s*)?kỹ\s+năng\s*(?:yêu\s+cầu|cần\s+thiết)?\s*:?', r'(?:\*\s*)?chân\s+dung\s+ứng\s+viên\s*:?']
        en_headers = [r'(?:\*\s*)?(?:job\s+)?requirements?\s*:?', r'(?:\*\s*)?(?:basic\s+|minimum\s+|preferred\s+)?qualifications?\s*:?', r'(?:\*\s*)?what\s+(?:we|you)(?:\'ll)?\s+(?:need|look\s+for|require|bring)\s*:?', r'(?:\*\s*)?(?:required|essential|key)\s+skills?\s*:?', r'(?:\*\s*)?who\s+you\s+are\s*:?']
        
        all_headers = vi_headers + en_headers
        header_pattern = '|'.join(f'(?:{h})' for h in all_headers)
        m_start = re.search(header_pattern, text, re.IGNORECASE)
        if not m_start: return None

        next_section_patterns = [r'(?:\*\s*)?(?:quyền\s+lợi|phúc\s+lợi|chế\s+độ|đãi\s+ngộ)\s*:?', r'(?:\*\s*)?(?:benefits?|perks?|what\s+we\s+offer|compensation)\s*:?', r'(?:\*\s*)?(?:nộp\s+hồ\s+sơ|cách\s+apply|how\s+to\s+apply)\s*:?', r'(?:\*\s*)?(?:quá\s+trình\s+tuyển\s+dụng|interview\s+process|thông\s+tin\s+công\s+ty)\s*:?']
        next_section_re = '|'.join(f'(?:{p})' for p in next_section_patterns)
        m_end = re.search(next_section_re, text[m_start.end():], re.IGNORECASE)

        if m_end: req_text = text[m_start.end(): m_start.end() + m_end.start()]
        else: req_text = text[m_start.end(): m_start.end() + 2500]
        
        req_text = req_text.strip()
        return req_text if req_text else None

    @classmethod
    def extract_benefits(cls, text: str) -> Optional[str]:
        """Bóc tách khối văn bản Quyền lợi / Benefits"""
        vi_headers = [r'(?:\*\s*)?quyền\s+lợi\s*(?:được\s+hưởng)?\s*:?', r'(?:\*\s*)?phúc\s+lợi\s*:?', r'(?:\*\s*)?chế\s+độ\s*(?:đãi\s+ngộ|làm\s+việc|phúc\s+lợi)?\s*:?', r'(?:\*\s*)?đãi\s+ngộ\s*:?', r'(?:\*\s*)?tại\s+sao\s+(?:chọn|nên\s+làm\s+việc\s+tại)\s+.*?:?']
        en_headers = [r'(?:\*\s*)?benefits?\s*:?', r'(?:\*\s*)?perks?(?:\s+and\s+benefits?)?\s*:?', r'(?:\*\s*)?what\s+(?:we|you)\s+offer\s*:?', r'(?:\*\s*)?compensation\s+(?:and\s+benefits?)?\s*:?', r'(?:\*\s*)?why\s+(?:join\s+us|you\'ll\s+love\s+working\s+here)\s*:?', r'(?:\*\s*)?what\'s\s+in\s+it\s+for\s+you\s*:?']
        
        all_headers = vi_headers + en_headers
        header_pattern = '|'.join(f'(?:{h})' for h in all_headers)
        m_start = re.search(header_pattern, text, re.IGNORECASE)
        if not m_start: return None

        next_section_patterns = [r'(?:\*\s*)?nộp\s+hồ\s+sơ\s*:?', r'(?:\*\s*)?cách\s+(?:nộp|apply)\s*:?', r'how\s+to\s+apply\s*:?', r'(?:\*\s*)?liên\s+hệ\s*:?', r'contact\s+us\s*:?', r'(?:\*\s*)?(?:thông\s+tin\s+công\s+ty|về\s+chúng\s+tôi|about\s+us)\s*:?']
        next_section_re = '|'.join(f'(?:{p})' for p in next_section_patterns)
        m_end = re.search(next_section_re, text[m_start.end():], re.IGNORECASE)

        if m_end: ben_text = text[m_start.end(): m_start.end() + m_end.start()]
        else: ben_text = text[m_start.end(): m_start.end() + 2000]
        
        ben_text = ben_text.strip()
        return ben_text if ben_text else None

    @classmethod
    def extract_deadline(cls, text: str) -> Optional[str]:
        patterns = [
            r'(?:hạn\s+(?:nộp(?:\s+hồ\s+sơ)?|ứng\s+tuyển|apply)|deadline)\s*[:\-]?\s*(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4}(?:\s+\w+)?)',
            r'(?:nộp hồ sơ|ứng tuyển|apply) trước\s+(?:ngày\s+)?(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})',
            r'(?:apply\s+by|deadline|closing\s+date|applications?\s+close(?:s)?(?:\s+on)?)\s*[:\-]?\s*(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4})',
            r'(?:before|by|trước)\s+(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})'
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    @classmethod
    def extract_company_info(cls, text: str) -> Optional[str]:
        """Bóc tách khối thông tin giới thiệu công ty"""
        headers = [r'(?:\*\s*)?(?:về\s+chúng\s+tôi|giới\s+thiệu\s+công\s+ty|about\s+us|about\s+(?:the\s+)?company)\s*:?']
        header_pattern = '|'.join(f'(?:{h})' for h in headers)
        m_start = re.search(header_pattern, text, re.IGNORECASE)
        if not m_start: return None
        
        info_text = text[m_start.end(): m_start.end() + 2000].strip()
        return info_text if info_text else None

    @classmethod
    def extract_company_website(cls, text: str) -> Optional[str]:
        patterns = [
            r'(?:website|trang\s+web)\s*[:\-]?\s*(https?://[^\s\n]+)',
            r'(?:tìm\s+hiểu\s+thêm\s+tại|learn\s+more\s+at)\s*[:\-]?\s*(https?://[^\s\n]+)'
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    @classmethod
    def extract_job_description(cls, text: str) -> Optional[str]:
        """Bóc tách phần Mô tả công việc (Job Description)"""
        vi_headers = [r'(?:\*\s*)?mô\s+tả\s*(?:công\s+việc)?\s*:?', r'(?:\*\s*)?chi\s+tiết\s*(?:công\s+việc)?\s*:?']
        en_headers = [r'(?:\*\s*)?(?:job\s+)?description\s*:?', r'(?:\*\s*)?what\s+you\s+will\s+do\s*:?', r'(?:\*\s*)?(?:your\s+)?responsibilities\s*:?', r'(?:\*\s*)?the\s+role\s*:?']
        
        all_headers = vi_headers + en_headers
        header_pattern = '|'.join(f'(?:{h})' for h in all_headers)
        m_start = re.search(header_pattern, text, re.IGNORECASE)
        
        if not m_start:
            # Nếu không tìm thấy header "Mô tả công việc", có thể phần đầu chính là mô tả.
            # Lấy toàn bộ text từ đầu cho đến khi gặp "Yêu cầu" hoặc "Quyền lợi"
            next_section_re = r'(?i)(?:\*\s*)?(yêu\s+cầu|requirements?|quyền\s+lợi|benefits?|phúc\s+lợi|chân\s+dung)\s*:?'
            m_end = re.search(next_section_re, text)
            if m_end:
                desc_text = text[:m_end.start()].strip()
                return desc_text if desc_text else None
            return text.strip() # Nếu không có section nào, trả về toàn bộ text.
        
        next_section_patterns = [r'(?:\*\s*)?(?:yêu\s+cầu|requirements?|quyền\s+lợi|benefits?|phúc\s+lợi|chân\s+dung)\s*:?']
        next_section_re = '|'.join(f'(?:{p})' for p in next_section_patterns)
        m_end = re.search(next_section_re, text[m_start.end():], re.IGNORECASE)

        if m_end: desc_text = text[m_start.end(): m_start.end() + m_end.start()]
        else: desc_text = text[m_start.end(): m_start.end() + 2500]
        
        desc_text = desc_text.strip()
        return desc_text if desc_text else None

    @classmethod
    def parse_all(cls, full_text: str) -> dict:
        """Parse toàn bộ 14 trường có thể từ chuỗi raw text"""
        if not full_text or not isinstance(full_text, str):
            return {}
            
        return {
            "title": cls.extract_title(full_text),
            "company": cls.extract_company(full_text),
            "salary": cls.extract_salary(full_text),
            "location": cls.extract_location(full_text),
            "experience_level": cls.extract_experience(full_text),
            "job_type": cls.extract_job_type(full_text),
            "job_industry": cls.extract_job_industry(full_text),
            "job_position": cls.extract_job_position(full_text),
            "job_description": cls.extract_job_description(full_text),
            "requirements": cls.extract_requirements(full_text),
            "benefits": cls.extract_benefits(full_text),
            "job_deadline": cls.extract_deadline(full_text),
            "company_info": cls.extract_company_info(full_text),
            "company_website": cls.extract_company_website(full_text)
        }
