import json, math, os, re, sqlite3, uuid
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


def chat_recommend(c, payload, sid):
    """用现有可解释规则推荐器提供对话式建议；不调用外部大模型。"""
    message = str(payload.get('message', '')).strip()
    if not message or len(message) > 2000:
        raise ValueError('请输入 1–2000 字的需求')

    current = payload.get('context') if isinstance(payload.get('context'), dict) else {}
    districts = rows(c, 'SELECT id,name FROM districts')
    district_ids = {d['name']: d['id'] for d in districts}
    try: budget = int(current.get('budget', 100))
    except (TypeError, ValueError): budget = 100
    try: wait = int(current.get('wait', 40))
    except (TypeError, ValueError): wait = 40
    try: hour = float(current.get('hour', 21))
    except (TypeError, ValueError): hour = 21
    try: district = int(current.get('district', 1))
    except (TypeError, ValueError): district = 1
    if not 10 <= budget <= 500: budget = 100
    if not 0 <= wait <= 120: wait = 40
    if not 0 <= hour < 24: hour = 21
    if district not in district_ids.values(): district = 1
    scene = current.get('scene', '朋友聚会')
    if scene not in ['朋友聚会', '独自用餐', '出游夜宵']: scene = '朋友聚会'
    cuisine = current.get('cuisine', '不限')
    if cuisine not in ['不限', '烧烤', '小龙虾', '湖北菜', '家常菜', '粥粉面']: cuisine = '不限'

    for name, did in district_ids.items():
        if name in message:
            district = did
            break

    budget_match = re.search(r'(?:人均|预算|每人|每位|控制在|不超过|最多)\s*[¥￥]?\s*(\d{1,3})\s*(?:元|块)?', message)
    if not budget_match:
        budget_match = re.search(r'[¥￥]\s*(\d{1,3})', message)
    if not budget_match:
        budget_match = re.search(r'(\d{1,3})\s*(?:元|块)(?:以内|左右)?', message)
    if budget_match:
        candidate = int(budget_match.group(1))
        if 10 <= candidate <= 500: budget = candidate

    wait_match = re.search(r'(?:等位|等待)(?:时间)?\s*(?:不超过|控制在|最多)?\s*(\d{1,3})\s*分钟', message)
    if not wait_match:
        wait_match = re.search(r'(\d{1,3})\s*分钟.*(?:等位|等待)', message)
    if wait_match:
        candidate = int(wait_match.group(1))
        if 0 <= candidate <= 120: wait = candidate

    time_match = re.search(r'(凌晨|早上|上午|中午|下午|傍晚|晚上|今晚)?\s*(\d{1,2})(?::(\d{2})|点(?:半|(\d{1,2})分?)?)', message)
    if time_match:
        period, h, minute, half_minute = time_match.groups()
        h = int(h)
        minutes = int(minute or (30 if '半' in time_match.group(0) else half_minute or 0))
        if 0 <= h <= 23 and 0 <= minutes <= 59:
            parsed_hour = h + minutes / 60
            if period in ['晚上', '傍晚', '下午'] and h < 12: parsed_hour += 12
            if period in ['凌晨', '早上', '上午'] and h == 12: parsed_hour = minutes / 60
            if period == '中午' and h < 11: parsed_hour += 12
            hour = parsed_hour % 24

    if any(word in message for word in ['一个人', '独自', '单人', '自己吃']):
        scene = '独自用餐'
    elif any(word in message for word in ['朋友', '聚会', '同事', '多人']):
        scene = '朋友聚会'
    elif any(word in message for word in ['夜宵', '出游', '逛街', '散步']):
        scene = '出游夜宵'

    if any(word in message for word in ['小龙虾', '虾']):
        cuisine = '小龙虾'
    elif any(word in message for word in ['烧烤', '烤肉', '烤串']):
        cuisine = '烧烤'
    elif any(word in message for word in ['清淡', '粥', '面条', '粉面']):
        cuisine = '粥粉面'
    elif any(word in message for word in ['家常菜', '家常口味']):
        cuisine = '家常菜'
    elif any(word in message for word in ['湖北菜', '武汉特色', '本地菜']):
        cuisine = '湖北菜'

    constraints = {'district': district, 'budget': budget, 'wait': wait, 'hour': hour, 'scene': scene, 'cuisine': cuisine}
    if any(word in message for word in ['帮助', '怎么用', '你能做什么', '功能介绍']):
        return {
            'reply': '我可以根据商圈、预算、到店时间、等待时长、就餐场景和口味帮你缩小选择范围。你可以直接说“江汉路，人均 60 元，晚上 9 点，一个人吃清淡一点”。',
            'constraints': constraints, 'items': [], 'total': 0,
            'tips': ['给出商圈或附近地标，推荐会更贴近你的活动范围。', '说明预算和最长等待时间，可以先排除不合适的选项。', '夜间营业时间目前是演示数据，出发前请核实商家信息。']
        }

    result = recommend(c, constraints, sid)
    found = result['items']
    if found:
        first = found[0]
        reply = (f"我按「{next((d['name'] for d in districts if d['id'] == district), '所选商圈')}、人均 ¥{budget} 以内、等待不超过 {wait} 分钟、"
                 f"{scene}、{cuisine}」筛选，找到 {len(found)} 家符合当前条件的演示商户。"
                 f"优先可以看看 {first['name']}：人均约 ¥{first['price']}，预计等位 {first['wait']} 分钟，"
                 f"综合匹配分 {first['score']}。{first['reasons'][0]}。")
        tips = []
        if budget <= 50: tips.append('预算较紧时，建议给饮料或加菜预留余量，并优先比较人均价格。')
        if wait <= 20: tips.append('时间比较紧，建议优先查看预计等位较短的选项，并在出发前确认现场情况。')
        if scene == '独自用餐': tips.append('独自用餐可以优先考虑人均较低、等待较短的商家。')
        if scene == '朋友聚会': tips.append('朋友聚会可提前确认座位、拼桌和多人套餐等信息。')
        if hour >= 23 or hour < 5: tips.append('你选择的时间较晚，营业时间为演示数据，请务必出发前联系商家核实。')
        if not tips: tips.append('可以打开商家详情查看菜品和推荐依据，再比较 2–3 家后决定。')
    else:
        reply = '目前没有找到同时满足这些条件的演示商户。可以尝试提高预算、放宽等待时间，或更换商圈、到店时间和口味。'
        tips = ['先把预算提高 10–20 元，看看是否出现更多选项。', '将最长等待时间放宽到 40 分钟，扩大可选范围。', '如果时间较晚，请优先确认营业状态，再决定是否前往。']
    return {'reply': reply, 'constraints': constraints, 'items': found, 'total': len(found), 'tips': tips}


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
                if path=='/api/reviews':
                    items=rows(c,"SELECT f.id,f.restaurant_id,r.name restaurant_name,d.name district,f.rating,f.comment,f.created_at FROM feedback f JOIN restaurants r ON r.id=f.restaurant_id JOIN districts d ON d.id=r.district_id ORDER BY f.id DESC LIMIT 200")
                    summary=c.execute('SELECT count(*) total,round(avg(rating),1) average FROM feedback').fetchone()
                    return self.send({'items':items,'summary':dict(summary)})
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
                elif self.path=='/api/chat': result=chat_recommend(c,p,sid)
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
