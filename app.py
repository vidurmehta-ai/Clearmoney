import os
import json
import random
import textwrap
import zipfile
import io
from flask import Flask, render_template, jsonify, request, send_file
from PIL import Image, ImageDraw, ImageFont
import anthropic

app = Flask(__name__)

FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REG  = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

AFFILIATES = [
    {"icon":"📊","name":"Empower (Personal Capital)","desc":"Free net worth tracker and retirement planner.","commission":"$100–$200 per qualified signup","cta":"💰 Want to see your real net worth in 2 minutes? I use Empower — it's free. Link in bio."},
    {"icon":"🏦","name":"Acorns","desc":"Round-up investing app. Perfect for beginners.","commission":"$10–$15 per signup + recurring","cta":"🌱 I started investing with literally $5. Acorns rounds up every purchase and invests it. Link in bio."},
    {"icon":"📈","name":"Robinhood","desc":"Zero-commission stock trading. Easy signup.","commission":"$20–$35 per funded account","cta":"📈 No broker fees. No minimums. Get a free stock when you sign up — link in bio."},
    {"icon":"💳","name":"Credit Karma","desc":"Free credit score monitoring.","commission":"$2–$12 per signup","cta":"📊 Check your credit score free — no credit card needed. I use Credit Karma. Link in bio."},
    {"icon":"🎯","name":"YNAB (You Need A Budget)","desc":"Best budgeting app in the market.","commission":"$30–$50 per paid trial conversion","cta":"📋 The budgeting app that changed how I handle money — try YNAB free for 34 days. Link in bio."}
]

SEG_LABELS = {
    "beginner":  "complete beginners who live paycheck to paycheck and have never invested a dollar",
    "young_pro": "young professionals aged 25–35 who earn decent money but spend it all and have no savings plan",
    "freedom":   "people who want to retire early or achieve financial independence and are willing to make real changes"
}

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
            draw.text((W//2, start_y + i*80), line, fill='#f0f0f8', font=fn_hook, anchor='mm')
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

def generate_images(hook, slides):
    images = {}
    images['slide_01_hook.png'] = make_slide(1, hook, '', total=9, is_hook=True)
    for i, s in enumerate(slides):
        num = i + 2
        images[f'slide_{num:02d}.png'] = make_slide(num, s['title'], s['body'], total=9)
    return images

def pack_zip(images):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname, img in images.items():
            img_buf = io.BytesIO()
            img.save(img_buf, format='PNG', optimize=True)
            zf.writestr(fname, img_buf.getvalue())
    buf.seek(0)
    return buf

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    segment  = request.json.get('segment', 'beginner')
    audience = SEG_LABELS.get(segment, SEG_LABELS['beginner'])
    api_key  = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'API key not configured. Add ANTHROPIC_API_KEY in Render environment variables.'}), 500

    prompt = f"""You are the content writer for "ClearMoney Weekly" — a personal finance Instagram page targeting {audience} in the USA.

Generate ONE complete Instagram carousel post. Respond ONLY in valid JSON. No markdown. No explanation. No backticks.

Sound like a real human — a smart friend who figured out money. Use contractions. Mix short and long sentences. Avoid "leverage", "navigate", "utilize", "crucial". Use specific numbers. Never sound like a textbook. Keep titles under 6 words. Keep body under 25 words.

Pick ONE fresh topic: emergency funds, credit scores, compound interest, salary negotiation, index funds, debt payoff, impulse spending, net worth tracking, side income, retirement basics, bank fees, subscription audits, investing myths, savings rate, 401k basics.

Return this exact JSON:
{{
  "topic": "topic name",
  "hook": "one punchy line under 10 words. Bold statement or surprising fact. No question marks.",
  "slides": [
    {{"title": "short title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "short title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "short title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "short title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "short title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "short title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "short title under 6 words", "body": "1-2 sentences under 25 words"}},
    {{"title": "Follow @ClearMoneyWeekly", "body": "Save this post. One money tip every week. It adds up."}}
  ],
  "caption": "80-100 words. Conversational. Hook first line. Line breaks. End with a question.",
  "hashtags": ["personalfinance","moneytips","financialfreedom","budgeting","savingmoney","investing101","moneyadvice","financetips","wealthbuilding","clearmoney","moneymindset","financialliteracy","debtfree","investingforbeginners","moneygoals"],
  "posting_tip": "Best day, time EST, one action for maximum USA reach"
}}"""

    try:
        client  = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-opus-4-5',
            max_tokens=1000,
            messages=[{'role':'user','content':prompt}]
        )
        raw    = message.content[0].text
        clean  = raw.replace('```json','').replace('```','').strip()
        parsed = json.loads(clean)

        images  = generate_images(parsed['hook'], parsed['slides'])
        zip_buf = pack_zip(images)
        token   = str(random.randint(100000,999999))
        app.config.setdefault('ZIPS',{})[token] = zip_buf.read()

        parsed['affiliate'] = random.choice(AFFILIATES)
        parsed['zip_token'] = token
        return jsonify(parsed)

    except json.JSONDecodeError:
        return jsonify({'error':'Could not parse AI response. Please try again.'}), 500
    except anthropic.AuthenticationError:
        return jsonify({'error':'Invalid API key. Check ANTHROPIC_API_KEY in Render settings.'}), 401
    except anthropic.RateLimitError:
        return jsonify({'error':'Rate limit hit. Wait 30 seconds and try again.'}), 429
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<token>')
def download(token):
    data = app.config.get('ZIPS',{}).get(token)
    if not data:
        return 'Expired. Please generate again.', 404
    buf = io.BytesIO(data)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name='clearmoney_carousel.zip')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
