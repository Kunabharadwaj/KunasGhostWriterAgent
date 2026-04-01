import feedparser
import requests
import os
from groq import Groq
from datetime import datetime

# --- Config from env (Set these in GitHub Secrets) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# --- Tech & AI RSS Feeds ---
FEEDS = {
    "TechCrunch": "https://techcrunch.com/feed/",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Wired": "https://www.wired.com/feed/rss",          # ✅ Fixed: was https://wired.com
    "Hacker News": "https://hnrss.org/frontpage?points=100",
}

def fetch_tech_news(max_per_feed=5):
    all_headlines = []
    for source, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                all_headlines.append(f"[{source}] {entry.title}: {entry.link}")
        except Exception as e:
            print(f"❌ Error fetching {source}: {e}")
    return all_headlines

def generate_linkedin_content(headlines):
    try:                                                  # ✅ Fixed: added try/except
        client = Groq(api_key=GROQ_API_KEY)
        bullet_list = "\n".join(headlines)

        prompt = f"""You are a top-tier Tech Thought Leader on LinkedIn.
Based on these latest news headlines, perform two tasks:

1. **Daily Tech Digest**: Summarise the 3 most important trends in 3-4 punchy bullets.
2. **LinkedIn Post Draft**: Write a high-engagement LinkedIn post about the most significant story. 
   - Use a strong hook.
   - Add a 'Why this matters' section.
   - Include 3 relevant hashtags.
   - Tone: Professional, visionary, and slightly provocative.

Latest News:
{bullet_list}"""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",               # ✅ Fixed: was deprecated llama-3.1-70b-versatile
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ Groq API error: {e}")
        return None

def send_to_telegram(content):
    date_str = datetime.now().strftime("%d %b %Y")
    header = f"🚀 *Daily Tech Ghostwriter — {date_str}*\n\n"
    full_msg = header + content

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"  # ✅ Fixed: was https://telegram.org{TOKEN}

    if len(full_msg) > 4000:
        parts = [full_msg[i:i+4000] for i in range(0, len(full_msg), 4000)]
    else:
        parts = [full_msg]

    for part in parts:
        response = requests.post(url, json={            # ✅ Fixed: added response validation
            "chat_id": CHAT_ID,
            "text": part,
            "parse_mode": "Markdown"
        })
        if not response.ok:
            print(f"❌ Telegram send failed: {response.text}")
        else:
            print("✅ Message part sent to Telegram.")

if __name__ == "__main__":
    # ✅ Fixed: validate env vars before running
    if not all([TELEGRAM_TOKEN, CHAT_ID, GROQ_API_KEY]):
        print("❌ Missing required environment variables. Check TELEGRAM_TOKEN, CHAT_ID, GROQ_API_KEY.")
        exit(1)

    print("🤖 Ghostwriter Agent starting...")
    headlines = fetch_tech_news()
    if headlines:
        print(f"✅ Fetched {len(headlines)} headlines. Generating post...")
        ai_content = generate_linkedin_content(headlines)
        if ai_content:                                  # ✅ Fixed: only send if generation succeeded
            send_to_telegram(ai_content)
            print("✅ Content sent to Telegram!")
        else:
            print("❌ Content generation failed. Nothing sent.")
    else:
        print("❌ No news found.")
