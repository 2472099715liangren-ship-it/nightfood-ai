import tempfile, unittest
from pathlib import Path
import app

class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.old=app.DB; app.DB=Path(self.tmp.name)/'test.db'; app.init()
        with app.connect() as c:c.execute("INSERT INTO sessions(id) VALUES('test')")
    def tearDown(self):app.DB=self.old; self.tmp.cleanup()
    def recommend(self,**kwargs):
        with app.connect() as c:return app.recommend(c,dict(budget=100,wait=40,district=1,hour=21,scene='朋友聚会',**kwargs),'test')
    def test_seed_repeatability(self):
        app.init()
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM restaurants').fetchone()[0],24)
            self.assertEqual(c.execute('SELECT count(*) FROM dishes').fetchone()[0],72)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_constraints_and_persistence(self):
        with app.connect() as c:
            result=app.recommend(c,{'budget':50,'wait':20,'district':1,'hour':21,'scene':'独自用餐'},'test')
            self.assertTrue(result['items'])
            for r in result['items']:
                self.assertLessEqual(r['price'],50); self.assertLessEqual(r['wait'],20)
                self.assertAlmostEqual(r['score'],sum(r['parts'].values()),places=1)
            self.assertEqual(c.execute('SELECT count(*) FROM recommendation_items').fetchone()[0],len(result['items']))
    def test_after_midnight_and_closed(self):
        with app.connect() as c:
            p={'budget':200,'wait':60,'district':1,'hour':3}
            result=app.recommend(c,p,'test'); self.assertTrue(result['items']); self.assertTrue(all(r['closes']==28 for r in result['items']))
            p['hour']=12; self.assertEqual(app.recommend(c,p,'test')['items'],[])
    def test_impossible_budget(self):
        with app.connect() as c:self.assertEqual(app.recommend(c,{'budget':10,'district':1},'test')['items'],[])
    def test_chat_constraints_and_help(self):
        with app.connect() as c:
            result=app.chat_recommend(c,{'message':'江汉路，人均 60 元，晚上 9 点，一个人吃清淡一点'},'test')
            self.assertEqual(result['constraints']['district'],1)
            self.assertEqual(result['constraints']['budget'],60)
            self.assertEqual(result['constraints']['scene'],'独自用餐')
            self.assertEqual(result['constraints']['cuisine'],'粥粉面')
            self.assertTrue(result['tips'])
            help_result=app.chat_recommend(c,{'message':'怎么用'},'test')
            self.assertEqual(help_result['total'],0)
            self.assertIn('预算',help_result['reply'])
    def test_favorites_isolated(self):
        with app.connect() as c:
            c.execute("INSERT INTO sessions(id) VALUES('other')");c.execute("INSERT INTO favorites(session_id,restaurant_id) VALUES('test',1)")
            self.assertEqual(c.execute("SELECT count(*) FROM favorites WHERE session_id='other'").fetchone()[0],0)
if __name__=='__main__':unittest.main()
