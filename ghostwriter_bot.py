import re
import feedparser
import requests
import os
from groq import Groq
from datetime import datetime, timezone

# --- Config from env (Set these in GitHub Secrets) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# --- Feeds: wide net, 20 entries each ---
FEEDS = {
    "Hacker News Best": "https://hnrss.org/best",                                  # HN curated best, has Points + Comments
    "TechCrunch":       "https://techcrunch.com/feed/",
    "The Verge":        "https://www.theverge.com/rss/index.xml",
    "Wired":            "https://www.wired.com/feed/rss",
    "Reddit Technology":"https://www.reddit.com/r/technology/top/.rss?t=day",      # already ranked by upvotes
    "Reddit AI":        "https://www.reddit.com/r/artificial/top/.rss?t=day",      # already ranked by upvotes
}

# Keyword boost list — signals relevance and shareability
TRENDING_KEYWORDS = [
    'ai', 'gpt', 'openai', 'google', 'apple', 'microsoft', 'meta',
    'llm', 'chatgpt', 'gemini', 'startup', 'funding', 'acquisition',
    'breakthrough', 'launch', 'release', 'nvidia', 'claude', 'deepmind',
    'regulation', 'ban', 'billion', 'robotics', 'automation'
]

def get_recency_score(entry):
    """Score based on how recently the article was published."""
    published = entry.get('published_parsed')
    if not published:
        return 5  # unknown age, neutral score
    try:
        pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
        if age_hours <= 6:    return 20
        elif age_hours <= 12: return 15
        elif age_hours <= 24: return 10
        else:                 return 3
    except Exception:
        return 5

def get_hn_engagement_score(entry):
    """Parse Points and Comments from HN RSS description field."""
    desc = entry.get('summary', '')
    score = 0
    points_match   = re.search(r'Points:\s*(\d+)', desc)
    comments_match = re.search(r'Comments:\s*(\d+)', desc)
    if points_match:
        score += min(int(points_match.group(1)) // 10, 30)  # cap at 30
    if comments_match:
        score += min(int(comments_match.group(1)) // 20, 15)  # cap at 15
    return score

def get_keyword_score(title):
    """Boost score if title contains trending tech keywords."""
    title_lower = title.lower()
    return sum(2 for kw in TRENDING_KEYWORDS if kw in title_lower)

def calculate_score(entry, source, position):
    """Combine all signals into a single relevance score."""
    score = 0
    score += get_recency_score(entry)
    score += get_keyword_score(entry.get('title', ''))

    if 'Hacker News' in source:
        score += get_hn_engagement_score(entry)

    if 'Reddit' in source:
        # Feed is already sorted by upvotes — earlier position = higher engagement
        score += max(20 - position * 2, 0)

    return score

def deduplicate(entries, similarity_threshold=0.5):
    """Remove near-duplicate stories using Jaccard similarity on title words."""
    seen_word_sets = []
    unique = []
    for entry in entries:
        title_words = set(entry['title'].lower().split())
        is_duplicate = False
        for seen in seen_word_sets:
            intersection = len(title_words & seen)
            union = len(title_words | seen)
            if union > 0 and (intersection / union) > similarity_threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            unique.append(entry)
            seen_word_sets.append(title_words)
    return unique

def fetch_and_score_news(max_per_feed=20, top_n=15):
    """Fetch all feeds, score every entry, deduplicate, return top N."""
    all_entries = []

    for source, url in FEEDS.items():
        try:
            if 'reddit' in url:
                # Reddit blocks default feedparser UA — must set custom User-Agent
                response = requests.get(url, headers={'User-Agent': 'GhostwriterBot/1.0'}, timeout=10)
                feed = feedparser.parse(response.content)
            else:
                feed = feedparser.parse(url)

            for position, entry in enumerate(feed.entries[:max_per_feed]):
                title = entry.get('title', '').strip()
                link  = entry.get('link', '').strip()
                if not title or not link:
                    continue

                score = calculate_score(entry, source, position)
                all_entries.append({
                    'source': source,
                    'title':  title,
                    'link':   link,
                    'score':  score
                })

        except Exception as e:
            print(f"❌ Error fetching {source}: {e}")

    # Sort by score descending, deduplicate, pick top N
    all_entries.sort(key=lambda x: x['score'], reverse=True)
    all_entries = deduplicate(all_entries)
    top_entries = all_entries[:top_n]

    print(f"📊 Scored {len(all_entries)} unique stories. Top {len(top_entries)} selected.")
    for i, e in enumerate(top_entries, 1):
        print(f"  {i}. [{e['score']}pts] [{e['source']}] {e['title']}")

    return top_entries

def generate_linkedin_content(top_entries):
    """Send top scored headlines to Groq for LinkedIn post generation."""
    try:
        client = Groq(api_key=GROQ_API_KEY)
        bullet_list = "\n".join(
            [f"[{e['source']}] {e['title']}: {e['link']}" for e in top_entries]
        )

        prompt = f"""You are a top-tier Tech Thought Leader on LinkedIn.
The following headlines have been selected because they are the most trending, 
highly-engaged, and relevant tech stories right now — scored by recency, 
community upvotes, and keyword relevance.

Based on these stories, perform two tasks:

1. **Daily Tech Digest**: Summarise the 3 most important trends in 3-4 punchy bullets.
2. **LinkedIn Post Draft**: Write a high-engagement LinkedIn post about the single 
   most significant story.
   - Use a strong hook.
   - Add a 'Why this matters' section.
   - Include 3 relevant hashtags.
   - Tone: Professional, visionary, and slightly provocative.

Top Trending Stories:
{bullet_list}"""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"❌ Groq API error: {e}")
        return None

def send_to_telegram(content):
    """Send generated content to Telegram, splitting if over 4000 chars."""
    date_str = datetime.now().strftime("%d %b %Y")
    header   = f"🚀 *Daily Tech Ghostwriter — {date_str}*\n\n"
    full_msg = header + content

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    parts = [full_msg[i:i+4000] for i in range(0, len(full_msg), 4000)]

    for part in parts:
        response = requests.post(url, json={
            "chat_id":    CHAT_ID,
            "text":       part,
            "parse_mode": "Markdown"
        })
        if not response.ok:
            print(f"❌ Telegram send failed: {response.text}")
        else:
            print("✅ Message part sent to Telegram.")

if __name__ == "__main__":
    if not all([TELEGRAM_TOKEN, CHAT_ID, GROQ_API_KEY]):
        print("❌ Missing required environment variables. Check TELEGRAM_TOKEN, CHAT_ID, GROQ_API_KEY.")
        exit(1)

    print("🤖 Ghostwriter Agent starting...")

    top_entries = fetch_and_score_news(max_per_feed=20, top_n=15)

    if top_entries:
        print(f"\n✅ Generating LinkedIn content from top {len(top_entries)} stories...")
        ai_content = generate_linkedin_content(top_entries)
        if ai_content:
            send_to_telegram(ai_content)
            print("✅ Content sent to Telegram!")
        else:
            print("❌ Content generation failed. Nothing sent.")
    else:
        print("❌ No stories found across all feeds.")
