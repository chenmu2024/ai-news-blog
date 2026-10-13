import unittest
from content_os.humanizer.humanizer_gate import evaluate

class HumanizerGateTests(unittest.TestCase):
    def test_natural_structure_passes(self):
        text="# 标题\n\n那天他把材料摊在桌上，只问了一句：到底卡在哪一步？\n\n规则其实不复杂。真正麻烦的是地区、参保状态和申请时间要一起看。有人符合第一条，却会因为年度范围不同被挡在下一步。\n\n把这些条件逐项对上以后，事情反而清楚了。"
        self.assertEqual(evaluate("business",text)["status"],"PASS")

    def test_template_heavy_copy_fails(self):
        text="# 标题\n\n首先，我们需要了解背景。\n\n其次，值得注意的是这一变化。\n\n与此同时，从某种程度上说，这意味着新的机会。\n\n总体来看，可以看出趋势已经形成。\n\n综上所述，未来值得期待。"
        result=evaluate("wechat",text)
        self.assertEqual(result["status"],"FAIL")
        self.assertIn("template_connectors_dense",result["risks"])

    def test_repeated_contrast_fails(self):
        text="# 标题\n\n这不是速度问题，而是判断问题。\n\n这不是工具问题，而是流程问题。\n\n这不是成本问题，而是取舍问题。"
        result=evaluate("wechat",text)
        self.assertEqual(result["status"],"FAIL")
        self.assertIn("repeated_not_x_but_y",result["risks"])

if __name__=="__main__":
    unittest.main()
