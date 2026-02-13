import csv
import hashlib
import io
import json
import os
import secrets
import sqlite3
import time
import zipfile
from datetime import date, datetime, timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(__file__)
PUBLIC = os.path.join(ROOT, 'public')
UPLOADS = os.path.join(ROOT, 'uploads')
DATA = os.path.join(ROOT, 'data')
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(DATA, exist_ok=True)
DB_PATH = os.path.join(DATA, 'typing.db')


def db_conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def hash_pwd(p):
    return hashlib.sha256(p.encode()).hexdigest()


def init_db():
    with db_conn() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,user_id TEXT UNIQUE,password_hash TEXT,user_name TEXT,role TEXT,valid_upto TEXT);
        CREATE TABLE IF NOT EXISTS sessions(sid TEXT PRIMARY KEY,user_id TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS login_logs(id INTEGER PRIMARY KEY,user_id TEXT,login_time TEXT,logout_time TEXT,session_duration INTEGER);
        CREATE TABLE IF NOT EXISTS typing_results(id INTEGER PRIMARY KEY,user_id TEXT,mode TEXT,language TEXT,wpm REAL,accuracy REAL,raw_speed REAL,duration INTEGER,created_at TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS practice_contents(mode TEXT,language TEXT,content TEXT,PRIMARY KEY(mode,language));
        ''')
        if not con.execute("SELECT 1 FROM users WHERE user_id='admin'").fetchone():
            con.execute("INSERT INTO users(user_id,password_hash,user_name,role) VALUES(?,?,?,?)", ('admin', hash_pwd('kadmin'), 'Administrator', 'admin'))
        defaults = {'bonus_text': 'Click here for bonus', 'bonus_url': 'https://www.cncinfotech.com', 'certificate_bg': ''}
        for k, v in defaults.items():
            con.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (k, v))
        contents = {
            ('timed_words', 'english'): 'skill focus speed monitor progress practice institute keyboard learning student result accuracy words training session confidence future growth',
            ('timed_words', 'hindi'): 'कौशल अभ्यास गति शुद्धता परिणाम प्रगति प्रशिक्षण विद्यार्थी परीक्षा प्रमाणपत्र सफलता',
            ('home_row', 'english'): 'asdf jkl; sadf ;lkj asdf jkl; fjdk sall ;dfj aslk',
            ('home_row', 'hindi'): 'क ख ग घ ङ च छ ज झ ञ',
            ('sentence_spacing', 'english'): 'Typing with proper spacing improves readability and rhythm in every line you write.',
            ('sentence_spacing', 'hindi'): 'सही स्पेसिंग से टाइपिंग की गति और स्पष्टता दोनों बेहतर होती हैं।',
            ('vertical_reach', 'english'): 'Reach up and down the keyboard while keeping your wrists relaxed and stable always.',
            ('vertical_reach', 'hindi'): 'ऊपर और नीचे की कुंजियों तक संतुलित तरीके से पहुंचने का अभ्यास करें।',
            ('top_row', 'english'): 'qwerty uiop practice quick top row movement for better control and smooth typing',
            ('top_row', 'hindi'): 'औ ए इ ई उ ऊ ए ऐ ओ औ ऋ कुंजी अभ्यास',
            ('bottom_row', 'english'): 'zxcvbnm bottom row drills build finger agility and confidence',
            ('bottom_row', 'hindi'): 'निचली पंक्ति का अभ्यास उंगलियों की लचीलापन बढ़ाता है।'
        }
        for (m, l), t in contents.items():
            con.execute('INSERT OR IGNORE INTO practice_contents(mode,language,content) VALUES(?,?,?)', (m, l, t))


def parse_xlsx(path):
    out = []
    with zipfile.ZipFile(path) as z:
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            sxml = z.read('xl/sharedStrings.xml').decode('utf-8')
            strings = [x.split('</t>')[0] for x in sxml.split('<t>')[1:]]
        sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        rows = sheet.split('<row')[1:]
        for r in rows:
            vals = []
            for c in r.split('<c ')[1:]:
                t = 's' if ' t="s"' in c else 'n'
                if '<v>' not in c:
                    vals.append('')
                    continue
                v = c.split('<v>')[1].split('</v>')[0]
                vals.append(strings[int(v)] if t == 's' and v.isdigit() and int(v) < len(strings) else v)
            out.append(vals)
    if not out:
        return []
    header = out[0]
    rows = []
    for r in out[1:]:
        rows.append({header[i]: (r[i] if i < len(r) else '') for i in range(len(header))})
    return rows


def make_xlsx_template(path):
    rows = [['UserID', 'Password', 'UserName', 'ValidDays'], ['student01', 'pass123', 'Student One', '30']]
    shared = []
    for r in rows:
        for c in r:
            if c not in shared:
                shared.append(c)
    def si(i): return f'<si><t>{shared[i]}</t></si>'
    sst = f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(rows)*4}" uniqueCount="{len(shared)}">{"".join(si(i) for i in range(len(shared)))}</sst>'
    sheet_rows = []
    for ridx, r in enumerate(rows, 1):
        cells = []
        for cidx, v in enumerate(r):
            col = chr(65 + cidx)
            cells.append(f'<c r="{col}{ridx}" t="s"><v>{shared.index(v)}</v></c>')
        sheet_rows.append(f'<row r="{ridx}">{"".join(cells)}</row>')
    sheet = f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Users" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>')
        z.writestr('xl/sharedStrings.xml', sst)
        z.writestr('xl/worksheets/sheet1.xml', sheet)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def read_body(self):
        n = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(n)

    def current_user(self):
        ck = cookies.SimpleCookie(self.headers.get('Cookie'))
        sid = ck['sid'].value if 'sid' in ck else None
        if not sid:
            return None
        with db_conn() as con:
            s = con.execute('SELECT user_id FROM sessions WHERE sid=?', (sid,)).fetchone()
            if not s:
                return None
            u = con.execute('SELECT user_id,user_name,role,valid_upto FROM users WHERE user_id=?', (s['user_id'],)).fetchone()
            return dict(u) if u else None

    def require(self, admin=False):
        user = self.current_user()
        if not user:
            self.send_json({'message': 'Unauthorized'}, 401)
            return None
        if admin and user['role'] != 'admin':
            self.send_json({'message': 'Forbidden'}, 403)
            return None
        return user

    def do_GET(self):
        p = urlparse(self.path)
        if p.path.startswith('/uploads/'):
            fp = os.path.join(ROOT, p.path.lstrip('/'))
            if os.path.exists(fp):
                self.send_response(200); self.end_headers(); self.wfile.write(open(fp, 'rb').read()); return
        if p.path == '/api/session':
            u = self.current_user()
            if u: u = {'userId': u['user_id'], 'userName': u['user_name'], 'role': u['role']}
            return self.send_json({'user': u})
        if p.path == '/api/settings':
            if not self.require(): return
            with db_conn() as con:
                rows = con.execute('SELECT key,value FROM settings').fetchall()
            return self.send_json({r['key']: r['value'] for r in rows})
        if p.path == '/api/content':
            if not self.require(): return
            q = parse_qs(p.query)
            mode = q.get('mode', ['timed_words'])[0]; lang = q.get('language', ['english'])[0]
            with db_conn() as con:
                r = con.execute('SELECT content FROM practice_contents WHERE mode=? AND language=?', (mode, lang)).fetchone()
            return self.send_json({'content': r['content'] if r else ''})
        if p.path == '/api/results/me':
            u = self.require();
            if not u: return
            with db_conn() as con:
                rows = con.execute('SELECT * FROM typing_results WHERE user_id=? ORDER BY id DESC LIMIT 20', (u['user_id'],)).fetchall()
            return self.send_json([dict(r) for r in rows])
        if p.path == '/api/admin/users':
            if not self.require(admin=True): return
            with db_conn() as con:
                rows = con.execute('SELECT id,user_id,user_name,role,valid_upto, "" as created_at FROM users ORDER BY id DESC').fetchall()
            return self.send_json([dict(r) for r in rows])
        if p.path == '/api/admin/logs':
            if not self.require(admin=True): return
            with db_conn() as con:
                rows = con.execute('SELECT * FROM login_logs ORDER BY id DESC LIMIT 500').fetchall()
            return self.send_json([dict(r) for r in rows])
        if p.path == '/api/admin/content':
            if not self.require(admin=True): return
            with db_conn() as con:
                rows = con.execute('SELECT * FROM practice_contents').fetchall()
            return self.send_json([dict(r) for r in rows])
        if p.path == '/api/admin/users/template':
            if not self.require(admin=True): return
            tmp = os.path.join(DATA, 'template.xlsx'); make_xlsx_template(tmp)
            self.send_response(200)
            self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.send_header('Content-Disposition', 'attachment; filename="bulk_users_template.xlsx"')
            self.end_headers(); self.wfile.write(open(tmp, 'rb').read()); return
        f = os.path.join(PUBLIC, 'index.html') if p.path == '/' else os.path.join(PUBLIC, p.path.lstrip('/'))
        if os.path.exists(f) and os.path.isfile(f):
            self.send_response(200); self.end_headers(); self.wfile.write(open(f, 'rb').read()); return
        self.send_response(404); self.end_headers()

    def do_POST(self):
        p = urlparse(self.path)
        if p.path in ['/api/login', '/api/results', '/api/admin/users', '/api/admin/content', '/api/admin/settings', '/api/logout']:
            try:
                data = json.loads(self.read_body() or b'{}')
            except Exception:
                data = {}
        if p.path == '/api/login':
            uid, pwd = data.get('userId', ''), data.get('password', '')
            with db_conn() as con:
                u = con.execute('SELECT * FROM users WHERE user_id=?', (uid,)).fetchone()
                if not u or u['password_hash'] != hash_pwd(pwd):
                    return self.send_json({'message': 'Invalid credentials'}, 401)
                if u['role'] != 'admin' and u['valid_upto'] and date.fromisoformat(u['valid_upto']) < date.today():
                    return self.send_json({'message': 'Access expired. Contact administrator.'}, 403)
                sid = secrets.token_hex(24)
                con.execute('INSERT INTO sessions(sid,user_id,created_at) VALUES(?,?,?)', (sid, uid, datetime.utcnow().isoformat()))
                cur = con.execute('INSERT INTO login_logs(user_id,login_time) VALUES(?,?)', (uid, datetime.utcnow().isoformat()))
                con.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', (f'active_log_{sid}', str(cur.lastrowid)))
            self.send_response(200)
            self.send_header('Set-Cookie', f'sid={sid}; Path=/; HttpOnly')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            return self.wfile.write(json.dumps({'user': {'userId': u['user_id'], 'userName': u['user_name'], 'role': u['role']}}).encode())
        if p.path == '/api/logout':
            u = self.require();
            if not u: return
            ck = cookies.SimpleCookie(self.headers.get('Cookie')); sid = ck['sid'].value
            with db_conn() as con:
                row = con.execute('SELECT value FROM settings WHERE key=?', (f'active_log_{sid}',)).fetchone()
                if row:
                    logid = int(row['value'])
                    start = con.execute('SELECT login_time FROM login_logs WHERE id=?', (logid,)).fetchone()
                    dur = int((datetime.utcnow() - datetime.fromisoformat(start['login_time'])).total_seconds()) if start else 0
                    con.execute('UPDATE login_logs SET logout_time=?, session_duration=? WHERE id=?', (datetime.utcnow().isoformat(), dur, logid))
                con.execute('DELETE FROM sessions WHERE sid=?', (sid,))
            return self.send_json({'ok': True})
        if p.path == '/api/results':
            u = self.require();
            if not u: return
            with db_conn() as con:
                con.execute('INSERT INTO typing_results(user_id,mode,language,wpm,accuracy,raw_speed,duration,created_at) VALUES(?,?,?,?,?,?,?,?)',
                            (u['user_id'], data.get('mode'), data.get('language'), data.get('wpm', 0), data.get('accuracy', 0), data.get('rawSpeed', 0), data.get('duration', 0), datetime.utcnow().isoformat()))
            return self.send_json({'ok': True})
        if p.path == '/api/admin/users':
            if not self.require(admin=True): return
            try:
                with db_conn() as con:
                    con.execute('INSERT INTO users(user_id,password_hash,user_name,role,valid_upto) VALUES(?,?,?,?,?)',
                                (data['userId'], hash_pwd(data['password']), data['userName'], 'user', data.get('validUpto') or None))
                return self.send_json({'ok': True})
            except Exception:
                return self.send_json({'message': 'User creation failed. UserID may already exist.'}, 400)
        if p.path == '/api/admin/content':
            if not self.require(admin=True): return
            with db_conn() as con:
                con.execute('INSERT OR REPLACE INTO practice_contents(mode,language,content) VALUES(?,?,?)', (data['mode'], data['language'], data['content']))
            return self.send_json({'ok': True})
        if p.path == '/api/admin/settings':
            if not self.require(admin=True): return
            with db_conn() as con:
                con.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', ('bonus_text', data.get('bonusText', 'Click here for bonus')))
                con.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', ('bonus_url', data.get('bonusUrl', '#')))
            return self.send_json({'ok': True})
        if p.path in ['/api/admin/users/bulk', '/api/admin/certificate']:
            if not self.require(admin=True): return
            ctype = self.headers.get('Content-Type', '')
            boundary = ctype.split('boundary=')[-1].encode()
            raw = self.read_body()
            parts = raw.split(b'--' + boundary)
            fbytes = b''; filename = 'upload.bin'
            for part in parts:
                if b'filename=' in part:
                    head, body = part.split(b'\r\n\r\n', 1)
                    filename = head.split(b'filename="')[1].split(b'"')[0].decode(errors='ignore')
                    fbytes = body.rsplit(b'\r\n', 1)[0]
            temp = os.path.join(DATA, f'upload_{int(time.time())}_{filename}')
            open(temp, 'wb').write(fbytes)
            if p.path == '/api/admin/certificate':
                ext = os.path.splitext(filename)[1] or '.png'
                out = os.path.join(UPLOADS, f'certificate{ext}')
                os.replace(temp, out)
                with db_conn() as con:
                    con.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', ('certificate_bg', f'/uploads/certificate{ext}'))
                return self.send_json({'ok': True, 'path': f'/uploads/certificate{ext}'})
            rows = parse_xlsx(temp)
            os.remove(temp)
            created = 0; errors = []
            with db_conn() as con:
                for r in rows:
                    try:
                        days = int(str(r.get('ValidDays', '0') or '0'))
                        vu = (date.today() + timedelta(days=days)).isoformat()
                        con.execute('INSERT INTO users(user_id,password_hash,user_name,role,valid_upto) VALUES(?,?,?,?,?)',
                                    (str(r['UserID']), hash_pwd(str(r['Password'])), str(r['UserName']), 'user', vu))
                        created += 1
                    except Exception as e:
                        errors.append({'row': r, 'error': str(e)})
            return self.send_json({'created': created, 'errors': errors})
        self.send_json({'message': 'Not found'}, 404)

    def do_PUT(self):
        p = urlparse(self.path)
        if '/api/admin/users/' in p.path and p.path.endswith('/valid-upto'):
            if not self.require(admin=True): return
            uid = p.path.split('/')[4]
            data = json.loads(self.read_body() or b'{}')
            with db_conn() as con:
                con.execute('UPDATE users SET valid_upto=? WHERE id=?', (data.get('validUpto') or None, uid))
            return self.send_json({'ok': True})
        self.send_json({'message': 'Not found'}, 404)

    def do_DELETE(self):
        p = urlparse(self.path)
        if '/api/admin/users/' in p.path:
            if not self.require(admin=True): return
            uid = p.path.split('/')[4]
            with db_conn() as con:
                con.execute("DELETE FROM users WHERE id=? AND role!='admin'", (uid,))
            return self.send_json({'ok': True})
        self.send_json({'message': 'Not found'}, 404)


if __name__ == '__main__':
    init_db()
    server = ThreadingHTTPServer(('0.0.0.0', 3000), Handler)
    print('Server running on http://localhost:3000')
    server.serve_forever()
