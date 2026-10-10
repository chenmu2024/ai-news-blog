"""Offline regression for editorial intelligence. Run: python -m unittest content_os.test_editorial_intelligence"""
import unittest
from content_os.editorial_intelligence import analyze,score,PROFILES
class EditorialTests(unittest.TestCase):
 def test_all_profiles(self):
  self.assertEqual(set(analyze([],{})),set(PROFILES))
 def test_cluster(self):
  x=[{"profile":"business","title":"某公司发布季度报告","source":"A","url":"https://example.org/1"},{"profile":"business","title":"某公司发布季度报告","source":"B","url":"https://example.org/2"}]
  r=analyze(x,{})["business"]
  self.assertEqual(len(r),1)
  self.assertEqual(r[0]["cluster_size"],2)
  self.assertEqual(len(r[0]["independent_sources"]),2)
 def test_history_duplicate(self):
  _,f=score({"profile":"wechat","title":"一家AI公司的真实案例","url":"https://example.org"},["一家AI公司的真实案例"])
  self.assertIn("historical_near_duplicate",f)
 def test_scripture_hard_gate(self):
  _,f=score({"profile":"qiezhi","title":"论实践"},[])
  self.assertIn("primary_text_unverified",f)
 def test_unverified_heat_not_presented_as_verified(self):
  _,f=score({"profile":"fashion","title":"穿搭"},[])
  self.assertIn("unverified_heat",f)
if __name__=="__main__":unittest.main()
