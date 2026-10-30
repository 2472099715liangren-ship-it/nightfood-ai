import json, math, os, sqlite3, uuid
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
DB = Path(os.environ.get('APP_DB', ROOT / 'data' / 'night.db'))
def connect():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def init():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript('''
CREATE TABLE IF NOT EXISTS districts(id INTEGER PRIMARY KEY,name TEXT UNIQUE,description TEXT,lat REAL,lng REAL);
CREATE TABLE IF NOT EXISTS restaurants(id INTEGER PRIMARY KEY,district_id INTEGER REFERENCES districts(id),name TEXT,cuisine TEXT,price INTEGER,rating REAL,wait INTEGER,lat REAL,lng REAL,tags TEXT,color TEXT);
CREATE TABLE IF NOT EXISTS hours(restaurant_id INTEGER PRIMARY KEY REFERENCES restaurants(id),opens INTEGER,closes INTEGER);
CREATE TABLE IF NOT EXISTS dishes(id INTEGER PRIMARY KEY,restaurant_id INTEGER REFERENCES restaurants(id),name TEXT,price INTEGER);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS recommendation_runs(id INTEGER PRIMARY KEY,session_id TEXT REFERENCES sessions(id),constraints_json TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS recommendation_items(id INTEGER PRIMARY KEY,run_id INTEGER REFERENCES recommendation_runs(id),restaurant_id INTEGER REFERENCES restaurants(id),score REAL,explanation TEXT);
CREATE TABLE IF NOT EXISTS favorites(session_id TEXT REFERENCES sessions(id),restaurant_id INTEGER REFERENCES restaurants(id),created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(session_id,restaurant_id));
CREATE TABLE IF NOT EXISTS surveys(id INTEGER PRIMARY KEY,session_id TEXT REFERENCES sessions(id),scene TEXT,priority TEXT,trust INTEGER,willingness INTEGER,comment TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY,session_id TEXT REFERENCES sessions(id),restaurant_id INTEGER REFERENCES restaurants(id),rating INTEGER,comment TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,session_id TEXT REFERENCES sessions(id),kind TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
''')
        if c.execute('SELECT count(*) FROM districts').fetchone()[0]: return
        districts=[('江汉路','老街烟火与都市夜色交汇',30.586,114.291),('楚河汉街','沿河漫步，遇见精致风味',30.557,114.342),('光谷步行街','年轻人的夜间美食聚场',30.506,114.402),('粮道街','藏在街巷里的武汉味道',30.545,114.307)]
        c.executemany('INSERT INTO districts(name,description,lat,lng) VALUES(?,?,?,?)',districts)
        names=[('江城炭火烧烤','烧烤',65,'朋友聚会,烟火气','#d07b44'),('巷里小龙虾','小龙虾',98,'朋友聚会,武汉特色','#b84a3d'),('一碗热干面','湖北菜',22,'独自用餐,武汉特色','#c6a253'),('深夜食堂·小馆','家常菜',48,'独自用餐,安静','#768a67'),('沿江鲜鱼馆','湖北菜',86,'朋友聚会,武汉特色','#658c91'),('街角砂锅粥','粥粉面',35,'清淡,独自用餐','#a68b64')]
        for d in range(1,5):
            for j,(name,cuisine,price,tags,color) in enumerate(names):
                lat,lng=districts[d-1][2:]; rid=(d-1)*6+j+1
                c.execute('INSERT INTO restaurants VALUES(?,?,?,?,?,?,?,?,?,?,?)',(rid,d,name+' · '+districts[d-1][0],cuisine,price+(d-1)*3,round(4.3+(j%4)*.2,1),8+j*5,lat+.003*(j-2),lng+.004*(j%3-1),tags,color))
                c.execute('INSERT INTO hours VALUES(?,?,?)',(rid,17,26 if j%3 else 28))
                for k in range(3): c.execute('INSERT INTO dishes(restaurant_id,name,price) VALUES(?,?,?)',(rid,[cuisine+'招牌拼盘','特色时蔬','风味小食'][k],max(8,price//(k+1))))

def rows(c,sql,args=()): return [dict(r) for r in c.execute(sql,args)]
def restaurants(c):
    result=rows(c,'SELECT r.*,d.name district,h.opens,h.closes FROM restaurants r JOIN districts d ON d.id=r.district_id JOIN hours h ON h.restaurant_id=r.id')
    for r in result:
        r['tags']=r['tags'].split(','); r['dishes']=rows(c,'SELECT name,price FROM dishes WHERE restaurant_id=?',(r['id'],))
    return result

def recommend(c,p,sid):
    budget=int(p.get('budget',100)); limit=int(p.get('wait',40)); district=int(p.get('district',1)); hour=float(p.get('hour',21)); scene=p.get('scene','朋友聚会'); cuisine=p.get('cuisine','不限')
    if not (10<=budget<=500 and 0<=limit<=120 and 0<=hour<24): raise ValueError('预算、时间或等待范围不正确')
    loc=c.execute('SELECT lat,lng FROM districts WHERE id=?',(district,)).fetchone()
    if not loc: raise ValueError('商圈不存在')
    run=c.execute('INSERT INTO recommendation_runs(session_id,constraints_json) VALUES(?,?)',(sid,json.dumps(p,ensure_ascii=False))).lastrowid
    result=[]
    for r in restaurants(c):
        h=hour+24 if hour<12 else hour
        if not(r['opens']<=h<r['closes']) or r['price']>budget or r['wait']>limit or (cuisine!='不限' and r['cuisine']!=cuisine): continue
        distance=round(math.hypot((r['lat']-loc['lat'])*111,(r['lng']-loc['lng'])*96),1)
        parts={'预算适配':round(25*(1-r['price']/budget*.5),1),'空间可达':round(25/(1+distance/2),1),'等待时间':round(20*(1-r['wait']/max(limit,1)*.6),1),'场景偏好':20 if scene in r['tags'] else 8,'商户评分':round(r['rating']/5*10,1)}
        r.update(distance=distance,score=round(sum(parts.values()),1),parts=parts,reasons=[f"人均 ¥{r['price']}，在 ¥{budget} 预算内",f"距所选商圈中心约 {distance} km，预计等位 {r['wait']} 分钟",f"{'适合' if scene in r['tags'] else '可考虑用于'}{scene}；营业至次日 {r['closes']-24:02d}:00"],tradeoff='距离为直线估算；营业与等位信息为演示值，请到店前核实。')
        result.append(r)
    result.sort(key=lambda r:r['score'],reverse=True)
    for r in result: c.execute('INSERT INTO recommendation_items(run_id,restaurant_id,score,explanation) VALUES(?,?,?,?)',(run,r['id'],r['score'],json.dumps(r['parts'],ensure_ascii=False)))
    return {'items':result,'run_id':run,'total':len(result)}

class Handler(BaseHTTPRequestHandler):
    def send(self,value,status=200):
        data=json.dumps(value,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path=self.path.split('?')[0]
        if path.startswith('/api/'):
            with connect() as c:
                if path=='/api/health': return self.send({'status':'ok'})
                if path=='/api/catalog': return self.send({'districts':rows(c,'SELECT * FROM districts'),'restaurants':restaurants(c)})
                if path=='/api/stats':
                    counts={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['restaurants','districts','dishes','recommendation_runs','surveys','feedback','favorites']}
                    counts['trust']=c.execute('SELECT round(avg(trust),1) FROM surveys').fetchone()[0]
                    return self.send({'counts':counts,'scenes':rows(c,'SELECT scene,count(*) count FROM surveys GROUP BY scene'),'tables':11})
                if path=='/api/favorites': return self.send(rows(c,'SELECT restaurant_id FROM favorites WHERE session_id=?',(self.headers.get('X-Session',''),)))
                return self.send({'error':'接口不存在'},404)
        file=ROOT/'static'/('index.html' if path=='/' else path.lstrip('/'))
        if not file.resolve().is_relative_to((ROOT/'static').resolve()) or not file.is_file(): return self.send({'error':'页面不存在'},404)
        data=file.read_bytes(); self.send_response(200); self.send_header('Content-Type',{'html':'text/html; charset=utf-8','css':'text/css','js':'text/javascript'}.get(file.suffix[1:],'application/octet-stream')); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length',0))
            if size>20000: return self.send({'error':'请求过大'},413)
            p=json.loads(self.rfile.read(size))
            if not isinstance(p,dict): raise ValueError('请求应为 JSON 对象')
            sid=self.headers.get('X-Session','')
            if not sid or len(sid)>100: raise ValueError('缺少有效会话')
            with connect() as c:
                c.execute('INSERT OR IGNORE INTO sessions(id) VALUES(?)',(sid,))
                if self.path=='/api/recommend': result=recommend(c,p,sid)
                elif self.path=='/api/favorites':
                    rid=int(p['restaurant_id'])
                    if p.get('active'): c.execute('INSERT OR IGNORE INTO favorites(session_id,restaurant_id) VALUES(?,?)',(sid,rid))
                    else: c.execute('DELETE FROM favorites WHERE session_id=? AND restaurant_id=?',(sid,rid))
                    result={'ok':True}
                elif self.path=='/api/surveys':
                    trust=int(p['trust']); willingness=int(p['willingness'])
                    if not(1<=trust<=5 and 1<=willingness<=5): raise ValueError('量表范围为 1–5')
                    if p['scene'] not in ['朋友聚会','独自用餐','出游夜宵'] or p['priority'] not in ['预算','距离','等待','口味']: raise ValueError('问卷选项无效')
                    c.execute('INSERT INTO surveys(session_id,scene,priority,trust,willingness,comment) VALUES(?,?,?,?,?,?)',(sid,p['scene'],p['priority'],trust,willingness,str(p.get('comment',''))[:2000])); result={'ok':True}
                elif self.path=='/api/feedback':
                    rating=int(p['rating'])
                    if not 1<=rating<=5: raise ValueError('评分范围为 1–5')
                    c.execute('INSERT INTO feedback(session_id,restaurant_id,rating,comment) VALUES(?,?,?,?)',(sid,int(p['restaurant_id']),rating,str(p.get('comment',''))[:2000])); result={'ok':True}
                else: return self.send({'error':'接口不存在'},404)
                c.execute('INSERT INTO events(session_id,kind) VALUES(?,?)',(sid,self.path)); c.commit()
            self.send(result)
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as e: self.send({'error':'参数无效或关联记录不存在'},400)
        except Exception: self.send({'error':'服务器处理失败'},500)

if __name__=='__main__':
    init(); port=int(os.environ.get('PORT','8000')); print(f'Night dining server on {port}',flush=True); ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
