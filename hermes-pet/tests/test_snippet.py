import unittest

from tools.hermes_pet.snippet import extract_snippet, classify_status


class SnippetTests(unittest.TestCase):
    def test_prefers_korean_conclusion_line(self):
        text = "서론은 길다.\n\n결론: 펫은 생각하지 않고 결과만 보여준다.\n다음 단계는 구현이다."
        self.assertEqual(extract_snippet(text, max_chars=80), "결론: 펫은 생각하지 않고 결과만 보여준다.")

    def test_skips_markdown_noise_and_truncates(self):
        text = "# 제목\n```bash\nrm -rf no\n```\n이 문장은 아주 길어서 화면 말풍선에는 다 들어가지 않고 적당히 잘려야 한다. 뒤쪽은 필요 없다."
        self.assertEqual(extract_snippet(text, max_chars=30), "이 문장은 아주 길어서 화면 말풍선에는 다 들어가지…")

    def test_classifies_error_and_approval_and_done(self):
        self.assertEqual(classify_status("오류: 실패했습니다"), "error")
        self.assertEqual(classify_status("승인이 필요해"), "needs_approval")
        self.assertEqual(classify_status("완료: 테스트 통과"), "completed")
        self.assertEqual(classify_status("자료 확인 중"), "working")


if __name__ == "__main__":
    unittest.main()
