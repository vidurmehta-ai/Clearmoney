import os
import json
import random
from flask import Flask, render_template, jsonify, request
import anthropic

app = Flask(__name__)

AFFILIATES = [
    {
        "icon": "📊",
        "name": "Empower (Personal Capital)",
        "desc": "Free net worth tracker and retirement planner.",
        "commission": "$100–$200 per qualified signup",
        "cta": "💰 Want to see your real net worth in 2 minutes? I use Empower — it's free. Link in bio."
    },
    {
        "icon": "🏦",
        "name": "Acorns",
        "desc": "Round-up investing app. Perfect for beginners.",
        "commission": "$10–$15 per signup + recurring",
        "cta": "🌱 I started investing with literally $5. Acorns rounds up every purchase and invests it. Link in bio."
    },
    {
        "icon": "📈",
        "name": "Robinhood",
        "desc": "Zero-commission stock trading. Easy signup.",
        "commission": "$20–$35 per funded account",
        "cta": "📈 No broker fees. No minimums. Get a free stock when you sign up — link in bio."
    },
    {
        "icon": "💳",
        "name": "Credit Karma",
        "desc": "Free credit score monitoring. Every finance audience needs this.",
        "commission": "$2–$12 per signup",
        "cta": "📊 Check your credit score free — no credit card needed. I use Credit Karma. Link in bio."
    },
    {
        "icon": "🎯",
        "name": "YNAB (You Need A Budget)",
        "desc": "Best budgeting app in the market. High intent buyers.",
        "commission": "$30–$50 per paid trial conversion",
        "cta": "📋 The budgeting app that changed how I handle money — try YNAB free for 34 days. Link in bio."
    }
]

SEG_LABELS = {
    "beginner": "complete beginners who live paycheck to paycheck and have never invested a dollar",
    "young_pro": "young professionals aged 25–35 who earn decent money but spend it all and have no savings plan",
    "freedom": "people who want to retire early or achieve financial independence and are willing to make real changes"
}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    segment = request.json.get("segment", "beginner")
    audience = SEG_LABELS.get(segment, SEG_LABELS["beginner"])

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "API key not configured. Add ANTHROPIC_API_KEY in Render environment variables."}), 500

    prompt = f"""You are the content writer for "ClearMoney Weekly" — a personal finance Instagram page targeting {audience} in the USA.

Generate ONE complete Instagram carousel post. Respond ONLY in valid JSON. No markdown. No explanation. No backticks.

The content MUST sound like a real human wrote it — a smart friend who figured out money and wants to help. Use contractions. Mix short punchy sentences with longer ones. Avoid words like "leverage", "navigate", "utilize", "crucial". Use specific numbers and real examples. Never sound like a textbook.

Pick ONE fresh topic from: emergency funds, credit scores, compound interest, salary negotiation, index funds, debt payoff, impulse spending, net worth tracking, side income, retirement basics, bank fees, subscription audits, investing myths, savings rate, 401k basics.

Return this exact JSON:
{{
  "topic": "topic name",
  "hook": "Slide 1 hook — one punchy line under 12 words. Bold statement or surprising fact. No question marks.",
  "slides": [
    {{"title": "slide title", "body": "1-2 sentences, specific, human tone"}},
    {{"title": "slide title", "body": "1-2 sentences, specific, human tone"}},
    {{"title": "slide title", "body": "1-2 sentences, specific, human tone"}},
    {{"title": "slide title", "body": "1-2 sentences, specific, human tone"}},
    {{"title": "slide title", "body": "1-2 sentences, specific, human tone"}},
    {{"title": "slide title", "body": "1-2 sentences, specific, human tone"}},
    {{"title": "slide title", "body": "1-2 sentences, specific, human tone"}},
    {{"title": "Follow for more", "body": "Save this post and follow @ClearMoneyWeekly for one money tip every week. It adds up."}}
  ],
  "caption": "80-120 words. Conversational. Start with a hook. Include line breaks. End with a question to drive comments. Sound human.",
  "hashtags": ["personalfinance","moneytips","financialfreedom","budgeting","savingmoney","investing101","moneyadvice","financetips","wealthbuilding","clearmoney","moneymindset","financialliteracy","debtfree","investingforbeginners","moneygoals"],
  "posting_tip": "Specific tip on when and how to post this today for maximum USA reach — include day, time EST, one action"
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text
        clean = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean)
        parsed["affiliate"] = random.choice(AFFILIATES)
        return jsonify(parsed)

    except json.JSONDecodeError:
        return jsonify({"error": "Could not parse AI response. Please try again."}), 500
    except anthropic.AuthenticationError:
        return jsonify({"error": "Invalid API key. Check your ANTHROPIC_API_KEY in Render settings."}), 401
    except anthropic.RateLimitError:
        return jsonify({"error": "Rate limit hit. Wait 30 seconds and try again."}), 429
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
