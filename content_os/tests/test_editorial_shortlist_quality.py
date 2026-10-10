import unittest
from content_os.build_editorial_shortlist import editorial_quality

class ShortlistQualityTests(unittest.TestCase):
    def test_business_generic_marketing_is_weak(self):
        relevance, _, flags = editorial_quality("business", "成为小红书种草高手：福利课程PDF下载")
        self.assertIn("marketing_or_sales_content", flags)
        self.assertIn("business_weak_company_event_signal", flags)
        self.assertLess(relevance, 40)

    def test_business_company_event_is_relevant(self):
        relevance, _, flags = editorial_quality("business", "瑞幸海外门店突破100家，供应链怎么复制")
        self.assertNotIn("business_weak_company_event_signal", flags)
        self.assertGreaterEqual(relevance, 70)

    def test_fashion_requires_named_priority_celeb_and_outfit(self):
        _, _, flags = editorial_quality("fashion", "秋天西装怎么穿更显瘦")
        self.assertIn("fashion_no_named_priority_celebrity", flags)
        _, _, airport_only = editorial_quality("fashion", "杨幂泰国机场生图疯传：我们到底在追什么")
        self.assertIn("fashion_weak_outfit_context", airport_only)
        _, _, ok = editorial_quality("fashion", "Jisoo机场穿搭：短外套怎么搭")
        self.assertNotIn("fashion_no_named_priority_celebrity", ok)
        self.assertNotIn("fashion_weak_outfit_context", ok)

    def test_clickbait_gets_sensitive_flag(self):
        _, _, flags = editorial_quality("jingyun", "31岁妈妈跳楼：击溃中年女人有多容易")
        self.assertIn("sensational_or_sensitive_framing", flags)

    def test_jingyun_relationship_clickbait_is_manual_only(self):
        _, _, flags = editorial_quality("jingyun", "实录：一个中年女人万箭穿心的婚外情")
        self.assertIn("relationship_clickbait_requires_manual_review", flags)

    def test_history_sales_content_is_rejected_signal(self):
        _, _, flags = editorial_quality("zizhitongjian", "冯唐讲资治通鉴全部课程视频合集")
        self.assertIn("marketing_or_sales_content", flags)
        self.assertIn("history_commercial_content", flags)

if __name__ == "__main__":
    unittest.main()
