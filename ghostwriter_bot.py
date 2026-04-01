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
    "Wired": "https://wired.com",
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
            print(f"Error fetching {source}: {e}")
    return all_headlines

def generate_linkedin_content(headlines):
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
        model="llama-3.1-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1500
    )
    return response.choices[0].message.content

def send_to_telegram(content):
    date_str = datetime.now().strftime("%d %b %Y")
    header = f"🚀 *Daily Tech Ghostwriter — {date_str}*\n\n"
    full_msg = header + content
    
    url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
    # Split message if it's too long for Telegram (4096 char limit)
    if len(full_msg) > 4000:
        parts = [full_msg[i:i+4000] for i in range(0, len(full_msg), 4000)]
    else:
        parts = [full_msg]

    for part in parts:
        requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": part,
            "parse_mode": "Markdown"
        })

if __name__ == "__main__":
    print("🤖 Ghostwriter Agent starting...")
    headlines = fetch_tech_news()
    if headlines:
        print(f"Fetched {len(headlines)} headlines. Generating post...")
        ai_content = generate_linkedin_content(headlines)
        send_to_telegram(ai_content)
        print("✅ Content sent to Telegram!")
    else:
        print("❌ No news found.")
