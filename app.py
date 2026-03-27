import os, json, random, textwrap, zipfile, io, sqlite3, requests, logging
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, send_file
from PIL import Image, ImageDraw, ImageFont
from apscheduler.schedulers.background import BackgroundScheduler
import anthropic

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REG  = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
DB_PATH   = '/tmp/clearmoney.db'

AFFILIATES = [
    {"icon":"📊","name":"Empower (Personal Capital)","desc":"Free net worth tracker and retirement planner.","commission":"$100–$200 per qualified signup","cta":"💰 Want to see your real net worth in 2 minutes? I use Empower — it's free. Link in bio."},
    {"icon":"🏦","name":"Acorns","desc":"Round-up investing app. Perfect for beginners.","commission":"$10–$15 per signup + recurring","cta":"🌱 I started investing with literally $5. Acorns rounds up every purchase and invests it. Link in bio."},
    {"icon":"📈","name":"Robinhood","desc":"Zero-commission stock trading. Easy signup.","commission":"$20–$35 per funded account","cta":"📈 No broker fees. No minimums. Get a free stock when you sign up — link in bio."},
    {"icon":"💳","name":"Credit Karma","desc":"Free credit score monitoring.","commission":"$2–$12 per signup","cta":"📊 Check your credit score free — no credit card needed. I use Credit Karma. Link in bio."},
    {"icon":"🎯","name":"YNAB (You Need A Budget)","desc":"Best budgeting app in the market.","commission":"$30–$50 per paid trial conversion","cta":"📋 The budgeting app that changed how I handle money — try YNAB free for 34 days. Link in bio."}
]

FALLBACK_TOPICS = [
    "emergency fund basics","credit score improvement","compound interest","salary negotiation",
    "index fund investing","debt payoff strategies","impulse spending habits","net worth tracking",
    "side income ideas","401k basics","bank fee elimination","subscription audit",
    "investing myths debunked","savings rate improvement","budgeting frameworks",
    "Roth IRA vs 401k","high yield savings accounts","credit card debt payoff",
    "financial independence","passive income streams","tax saving tips",
    "home buying basics","student loan repayment","insurance basics","estate planning basics",
    "dollar cost averaging","diversification basics","inflation protection","cash flow management",
    "financial goal setting"
]

SEG_LABELS = {
    "beginner":  "complete beginners who live paycheck to paycheck and have never invested a dollar",
    "young_pro": "young professionals aged 25-35 who earn decent money but spend it all and have no savings plan",
    "freedom":   "people who want to retire early or achieve financial independence and are willing to make real changes"
}

# ── Database ─────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS trends
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     topic TEXT NOT NULL,
                     score INTEGER DEFAULT 50,
                     fetched_at TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS used_topics
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     topic TEXT NOT NULL,
                     segment TEXT NOT NULL,
                     used_at TEXT NOT NULL)''')
    conn.commit()
    conn.close()
    logging.info("DB initialized")

def get_trends_from_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute('SELECT topic FROM trends ORDER BY score DESC').fetchall()
        conn.close()
        if rows:
            return [r[0] for r in rows]
    except:
        pass
    return []

def get_used_topics(segment):
    try:
        conn = sqlite3.connect(DB_PATH)
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        rows = conn.execute(
            'SELECT topic FROM used_topics WHERE segment=? AND used_at>?',
            (segment, cutoff)
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except:
        return []

def mark_topic_used(topic, segment):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO used_topics VALUES (NULL,?,?,?)',
                     (topic, segment, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

def save_trends(topics):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM trends')
        for i, topic in enumerate(topics):
            score = 100 - (i * 5)
            conn.execute('INSERT INTO trends VALUES (NULL,?,?,?)',
                         (topic, score, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        logging.info(f"Saved {len(topics)} trends to DB")
    except Exception as e:
        logging.error(f"Save trends error: {e}")

# ── Perplexity Trend Fetch ───────────────────────────────────────────────────

def fetch_trends_perplexity():
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        logging.warning("No Perplexity key — using fallback topics")
        save_trends(FALLBACK_TOPICS)
        return

    prompt = """What are the top 20 personal finance topics that Americans are most actively searching for and discussing right now in 2026? 
    Focus on: budgeting, investing, debt, savings, credit, retirement, taxes, income.
    Return ONLY a JSON array of topic strings, no explanations, no markdown, no backticks.
    Example format: ["topic 1", "topic 2", "topic 3"]
    Keep each topic under 6 words. Make them specific and actionable."""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "sonar",
            "messages": [
                {"role": "system", "content": "You are a financial trend analyst. Return only valid JSON arrays."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500,
            "search_recency_filter": "week"
        }
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        content = data['choices'][0]['message']['content']
        clean = content.replace('```json','').replace('```','').strip()
        topics = json.loads(clean)
        if isinstance(topics, list) and len(topics) > 0:
            save_trends(topics[:20])
            logging.info(f"Fetched {len(topics)} topics from Perplexity")
        else:
            raise ValueError("Empty topic list")
    except Exception as e:
        logging.error(f"Perplexity fetch failed: {e} — using fallback")
        save_trends(FALLBACK_TOPICS)

def pick_topic(segment):
    trends = get_trends_from_db()
    if not trends:
        trends = FALLBACK_TOPICS
    used = get_used_topics(segment)
    available = [t for t in trends if t not in used]
    if not available:
        available = trends  # reset if all used
    topic = random.choice(available[:10])  # pick from top 10
    mark_topic_used(topic, segment)
    return topic

# ── Image Generation ─────────────────────────────────────────────────────────

def make_slide(slide_num, title, body, total=9, is_hook=False):
    W, H = 1080, 1080
    img  = Image.new('RGB', (W, H), color='#0a0a0f')
    draw = ImageDraw.Draw(img)
    for x in range(0, W, 40):
        for y in range(0, H, 40):
            draw.ellipse([x-1,y-1,x+1,y+1], fill='#161620')
    draw.rectangle([0,0,W,8], fill='#00e5a0')
    fn_small = ImageFont.truetype(FONT_BOLD, 22)
    draw.rounded_rectangle([56,36,170,88], radius=22, fill='#1c1c26', outline='#2a2a38')
    draw.text((113,62), f'{slide_num} / {total}', fill='#7a7a9a', font=fn_small, anchor='mm')
    fn_brand = ImageFont.truetype(FONT_REG, 20)
    draw.text((W-56,62), '@ClearMoneyWeekly', fill='#2a2a38', font=fn_brand, anchor='rm')
    if is_hook:
        fn_hook = ImageFont.truetype(FONT_BOLD, 64)
        wrapped = textwrap.fill(title, width=18)
        lines   = wrapped.split('\n')
        total_h = len(lines) * 80
        start_y = (H - total_h) // 2 - 40
        for i, line in enumerate(lines):
            draw.text((W//2, start_y+i*80), line, fill='#f0f0f8', font=fn_hook, anchor='mm')
        draw.rectangle([W//2-120, start_y+total_h+20, W//2+120, start_y+total_h+26], fill='#00e5a0')
        fn_swipe = ImageFont.truetype(FONT_REG, 28)
        draw.text((W//2, H-140), 'Swipe to learn more →', fill='#7a7a9a', font=fn_swipe, anchor='mm')
    else:
        fn_title  = ImageFont.truetype(FONT_BOLD, 52)
        wrapped_t = textwrap.fill(title, width=22)
        draw.text((60,180), wrapped_t, fill='#f0f0f8', font=fn_title)
        t_lines = wrapped_t.count('\n') + 1
        bar_y   = 180 + t_lines * 65 + 16
        draw.rectangle([60, bar_y, 220, bar_y+5], fill='#00e5a0')
        fn_body   = ImageFont.truetype(FONT_REG, 36)
        wrapped_b = textwrap.fill(body, width=32)
        draw.text((60, bar_y+44), wrapped_b, fill='#a0a0c0', font=fn_body)
    draw.rectangle([0, H-90, W, H], fill='#13131a')
    draw.rectangle([0, H-90, W, H-88], fill='#2a2a38')
    fn_foot = ImageFont.truetype(FONT_REG, 22)
    draw.text((W//2, H-44), 'ClearMoney Weekly  •  clearmoney.onrender.com', fill='#2a2a38', font=fn_foot, anchor='mm')
    return img

def build_zip(hook, slides):
    images = {'slide_01_hook.png': make_slide(1, hook, '', total=9, is_hook=True)}
    for i, s in enumerate(slides):
        images[f'slide_{i+2:02d}.png'] = make_slide(i+2, s['title'], s['body'], total=9)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname, img in images.items():
            ib = io.BytesIO()
            img.save(ib, format='PNG', optimize=True)
            zf.writestr(fname, ib.getvalue())
    buf.seek(0)
    return buf.read()

# ── Claude Generation ─────────────────────────────────────────────────────────

def call_claude(segment, topic, api_key):
    audience = SEG_LABELS.get(segment, SEG_LABELS['beginner'])
    prompt = f"""You are the content writer for "ClearMoney Weekly" — a personal finance Instagram page targeting {audience} in the USA.

Write ONE carousel post about: "{topic}"

Respond ONLY in valid JSON. No markdown. No backticks. No explanation.

Sound like a real human — a smart friend who figured out money. Use contractions. Mix short punchy sentences with longer ones. Avoid "leverage", "navigate", "utilize", "crucial". Use specific dollar amounts and real examples. Never sound like a textbook. Titles under 6 words. Body under 25 words.

Return this exact JSON:
{{
  "topic": "{topic}",
  "hook": "one punchy line under 10 words. Bold statement or surprising fact. No question marks.",
  "slides": [
    {{"title": "title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "Follow @ClearMoneyWeekly", "body": "Save this post. One money tip every week. It adds up."}}
  ],
  "caption": "80-100 words. Conversational. Hook first line. Line breaks. End with a question.",
  "hashtags": ["personalfinance","moneytips","financialfreedom","budgeting","savingmoney","investing101","moneyadvice","financetips","wealthbuilding","clearmoney","moneymindset","financialliteracy","debtfree","investingforbeginners","moneygoals"],
  "posting_tip": "Best day and time EST for maximum USA reach"
}}"""
    client  = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model='claude-opus-4-5', max_tokens=1000,
        messages=[{'role':'user','content':prompt}]
    )
    raw   = message.content[0].text
    clean = raw.replace('```json','').replace('```','').strip()
    return json.loads(clean)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    trends = get_trends_from_db()
    trend_count = len(trends)
    last_trend = trends[0] if trends else 'Loading...'
    return render_template('index.html', trend_count=trend_count, last_trend=last_trend)

@app.route('/generate', methods=['POST'])
def generate():
    segment = request.json.get('segment','beginner')
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error':'ANTHROPIC_API_KEY not set in Render environment.'}), 500
    try:
        topic  = pick_topic(segment)
        parsed = call_claude(segment, topic, api_key)
        zip_data = build_zip(parsed['hook'], parsed['slides'])
        token = str(random.randint(100000,999999))
        app.config.setdefault('ZIPS',{})[token] = zip_data
        parsed['affiliate'] = random.choice(AFFILIATES)
        parsed['zip_token'] = token
        return jsonify(parsed)
    except json.JSONDecodeError:
        return jsonify({'error':'Could not parse AI response. Try again.'}), 500
    except anthropic.AuthenticationError:
        return jsonify({'error':'Invalid Anthropic API key.'}), 401
    except anthropic.RateLimitError:
        return jsonify({'error':'Rate limit hit. Wait 30 seconds.'}), 429
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/batch', methods=['POST'])
def batch():
    import time
    from flask import Response, stream_with_context

    segment = request.json.get('segment','beginner')
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error':'ANTHROPIC_API_KEY not set.'}), 500

    def generate_stream():
        all_zip_data = {}
        errors = []
        for day in range(1, 31):
            try:
                topic  = pick_topic(segment)
                parsed = call_claude(segment, topic, api_key)
                images = {'slide_01_hook.png': make_slide(1, parsed['hook'], '', total=9, is_hook=True)}
                for i, s in enumerate(parsed['slides']):
                    images[f'slide_{i+2:02d}.png'] = make_slide(i+2, s['title'], s['body'], total=9)
                for fname, img in images.items():
                    all_zip_data[f'Day_{day:02d}/{fname}'] = img
                yield f"data: {json.dumps({'day': day, 'topic': topic, 'status': 'ok'})}\n\n"
                time.sleep(0.5)
            except Exception as e:
                errors.append(f"Day {day}: {str(e)}")
                yield f"data: {json.dumps({'day': day, 'topic': 'error', 'status': 'error', 'error': str(e)})}\n\n"

        # Pack all into one zip
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path, img in all_zip_data.items():
                ib = io.BytesIO()
                img.save(ib, format='PNG', optimize=True)
                zf.writestr(path, ib.getvalue())
        buf.seek(0)
        token = str(random.randint(100000,999999))
        app.config.setdefault('ZIPS',{})[token] = buf.read()
        yield f"data: {json.dumps({'day': 'done', 'token': token, 'errors': errors})}\n\n"

    return Response(stream_with_context(generate_stream()), mimetype='text/event-stream')

@app.route('/refresh-trends', methods=['POST'])
def refresh_trends():
    try:
        fetch_trends_perplexity()
        trends = get_trends_from_db()
        return jsonify({'success': True, 'count': len(trends), 'topics': trends[:5]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/trends')
def view_trends():
    trends = get_trends_from_db()
    return jsonify({'topics': trends, 'count': len(trends)})

@app.route('/download/<token>')
def download(token):
    data = app.config.get('ZIPS',{}).get(token)
    if not data:
        return 'Expired. Please generate again.', 404
    buf = io.BytesIO(data)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name='clearmoney_carousel.zip')

# ── Scheduler ─────────────────────────────────────────────────────────────────

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_trends_perplexity, 'cron', day_of_week='sun', hour=0, minute=0)
    scheduler.start()
    logging.info("Scheduler started — trends refresh every Sunday midnight")

# ── Startup ───────────────────────────────────────────────────────────────────

with app.app_context():
    init_db()
    if not get_trends_from_db():
        logging.info("No trends in DB — fetching now")
        fetch_trends_perplexity()
    start_scheduler()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
