#!/usr/bin/env python3
"""
Riclivo.online Main Automation Script
Runs every hour via GitHub Actions
Fetches trending topics, researches, writes and publishes blog posts
"""

import os
import json
import time
import random
import requests
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import pytz

# ============================================
# CONFIGURATION
# ============================================
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

SITE_URL = "https://riclivo.online"
CONTENT_DIR = "content/posts"
STATIC_DIR = "static/images/posts"
DATA_DIR = "data"

EST = pytz.timezone("America/New_York")
NOW = datetime.now(EST)
HOUR = NOW.hour
WEEKDAY = NOW.weekday()  # 0=Monday, 6=Sunday
DAY_NAME = NOW.strftime("%A")

# ============================================
# LOAD CONFIG FILES
# ============================================
with open("data/niche_config.json") as f:
    NICHE_CONFIG = json.load(f)

with open("data/writing_style.json") as f:
    STYLE_GUIDE = json.load(f)

NICHES = {n["name"]: n for n in NICHE_CONFIG["niches"]}
ROTATION_PAIRS = NICHE_CONFIG["rotation_pairs"]

# ============================================
# LOAD / SAVE STATE FILES
# ============================================
def load_json(filepath, default):
    try:
        with open(filepath) as f:
            return json.load(f)
    except:
        return default

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

def load_posted_topics():
    return load_json("data/posted_topics.json", {})

def save_posted_topics(data):
    save_json("data/posted_topics.json", data)

def load_rotation():
    return load_json("data/rotation.json", {"current_pair_index": 0, "daily_count": 0, "last_date": ""})

def save_rotation(data):
    save_json("data/rotation.json", data)

# ============================================
# DETERMINE WHAT TO POST THIS HOUR
# ============================================
def get_schedule_for_now():
    """Returns what type of post to create based on day and hour"""
    
    schedule = {
        "type": "regular",
        "niches": None,
        "special": None
    }
    
    # PEAK HOURS - most trending topic any niche
    peak_hours = [13, 19]  # 1PM and 7PM EST
    if HOUR in peak_hours:
        schedule["type"] = "peak"
        return schedule
    
    # SPECIAL POSTS BY DAY AND HOUR
    specials = {
        # Monday
        (0, 7): "money_move_monday",
        # Tuesday  
        (1, 11): "tech_tuesday",
        (1, 9): "messi_ronaldo_watch",
        # Wednesday VS posts
        (2, 10): "vs_tech_ai",
        (2, 11): "vs_football_sports",
        (2, 14): "vs_health_finance",
        (2, 21): "vs_entertainment",
        # Thursday
        (3, 9): "tomorrow_preview",
        (3, 20): "crypto_corner",
        # Friday
        (4, 9): "ladies_corner",
        (4, 11): "ai_app_week",
        (4, 17): "week_in_numbers",
        # Saturday
        (5, 8): "weekend_kickoff",
        (5, 11): "nigerian_spotlight",
        (5, 14): "weekend_watch",
        (5, 17): "match_report",
        # Sunday
        (6, 8): "sunday_read",
        (6, 10): "sunday_fixtures",
        (6, 14): "this_week_in_ai",
        (6, 16): "sunday_wellness",
        (6, 20): "week_ahead",
        (6, 15): "transfer_mill",
    }
    
    # App of the day - every day 6AM
    if HOUR == 6:
        schedule["type"] = "special"
        schedule["special"] = "app_of_day"
        return schedule
    
    special_key = (WEEKDAY, HOUR)
    if special_key in specials:
        schedule["type"] = "special"
        schedule["special"] = specials[special_key]
        return schedule
    
    # Regular rotation post
    schedule["type"] = "regular"
    return schedule

# ============================================
# GET TRENDING TOPICS
# ============================================
def get_trending_topics(keywords, countries, min_score=50):
    """Fetch trending topics via Tavily search"""
    
    headers = {"Authorization": f"Bearer {TAVILY_API_KEY}"}
    
    # Build search query from keywords
    query = f"trending news today {' OR '.join(keywords[:3])}"
    
    payload = {
        "query": query,
        "search_depth": "advanced",
        "include_answer": True,
        "include_raw_content": False,
        "max_results": 10,
        "include_domains": [
            "bbc.com", "reuters.com", "theguardian.com",
            "techcrunch.com", "espn.com", "skysports.com",
            "bloomberg.com", "forbes.com", "cnn.com",
            "goal.com", "healthline.com", "coindesk.com"
        ]
    }
    
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json=payload,
            headers=headers,
            timeout=30
        )
        data = response.json()
        results = data.get("results", [])
        
        topics = []
        for r in results:
            topics.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0)
            })
        
        return [t for t in topics if t["score"] >= min_score / 100]
    
    except Exception as e:
        print(f"Tavily error: {e}")
        return []

def research_topic(topic_title, niche):
    """Deep research a specific topic via Tavily"""
    
    headers = {"Authorization": f"Bearer {TAVILY_API_KEY}"}
    
    payload = {
        "query": f"{topic_title} latest news facts details 2025 2026",
        "search_depth": "advanced",
        "include_answer": True,
        "max_results": 8
    }
    
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json=payload,
            headers=headers,
            timeout=30
        )
        data = response.json()
        
        research = {
            "answer": data.get("answer", ""),
            "sources": [r.get("content", "") for r in data.get("results", [])[:5]],
            "urls": [r.get("url", "") for r in data.get("results", [])[:3]]
        }
        
        return research
    
    except Exception as e:
        print(f"Research error: {e}")
        return {"answer": "", "sources": [], "urls": []}

# ============================================
# CHECK FOR DUPLICATES
# ============================================
def is_duplicate(title, posted_topics):
    """Check if topic was posted within cooldown period"""
    
    cooldown = NICHE_CONFIG["repeat_cooldown_days"]
    title_lower = title.lower()
    
    # Extract key words from title
    key_words = [w for w in title_lower.split() if len(w) > 4]
    
    for posted_title, posted_date in posted_topics.items():
        try:
            post_date = datetime.fromisoformat(posted_date)
            days_ago = (datetime.now() - post_date).days
            
            posted_lower = posted_title.lower()
            
            # Check for significant word overlap
            overlap = sum(1 for w in key_words if w in posted_lower)
            
            if overlap >= 3 and days_ago < cooldown:
                return True, days_ago
            
            # Exact match check
            if title_lower in posted_lower or posted_lower in title_lower:
                if days_ago < cooldown:
                    return True, days_ago
                    
        except:
            continue
    
    return False, 0

def should_repost_old_topic(title, posted_topics):
    """Check if old trending topic (7+ days) is worth reposting with fresh angle"""
    
    title_lower = title.lower()
    key_words = [w for w in title_lower.split() if len(w) > 4]
    
    for posted_title, posted_date in posted_topics.items():
        try:
            post_date = datetime.fromisoformat(posted_date)
            days_ago = (datetime.now() - post_date).days
            
            posted_lower = posted_title.lower()
            overlap = sum(1 for w in key_words if w in posted_lower)
            
            if overlap >= 3 and days_ago >= 7:
                return True, posted_title, days_ago
        except:
            continue
    
    return False, None, 0

# ============================================
# FETCH IMAGE FROM PEXELS
# ============================================
def fetch_image(query, post_slug):
    """Fetch a relevant image from Pexels"""
    
    headers = {"Authorization": PEXELS_API_KEY}
    
    # Clean query for image search
    image_query = query.replace("?", "").replace("!", "")[:50]
    
    try:
        response = requests.get(
            f"https://api.pexels.com/v1/search",
            headers=headers,
            params={
                "query": image_query,
                "per_page": 5,
                "orientation": "landscape"
            },
            timeout=15
        )
        
        data = response.json()
        photos = data.get("photos", [])
        
        if not photos:
            # Try broader search
            response = requests.get(
                f"https://api.pexels.com/v1/search",
                headers=headers,
                params={"query": "news", "per_page": 3, "orientation": "landscape"},
                timeout=15
            )
            data = response.json()
            photos = data.get("photos", [])
        
        if photos:
            photo = random.choice(photos[:3])
            image_url = photo["src"]["large"]
            photographer = photo["photographer"]
            
            # Download image
            img_dir = f"static/images/posts"
            os.makedirs(img_dir, exist_ok=True)
            img_path = f"{img_dir}/{post_slug}.jpg"
            
            img_response = requests.get(image_url, timeout=30)
            with open(img_path, "wb") as f:
                f.write(img_response.content)
            
            return f"/images/posts/{post_slug}.jpg", photographer
    
    except Exception as e:
        print(f"Pexels error: {e}")
    
    return None, None

def fetch_two_images(query_a, query_b, post_slug):
    """Fetch two images for VS posts"""
    img_a, photo_a = fetch_image(query_a, f"{post_slug}-a")
    time.sleep(1)
    img_b, photo_b = fetch_image(query_b, f"{post_slug}-b")
    return img_a, img_b, photo_a, photo_b

# ============================================
# WRITE POST WITH OPENAI
# ============================================
def write_post(topic, research, niche_name, post_type="regular", extra_context=""):
    """Generate blog post content using OpenAI"""
    
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    niche = NICHES.get(niche_name, NICHES["News"])
    style = STYLE_GUIDE
    niche_tone = style["niche_tones"].get(niche_name, style["niche_tones"]["News"])
    banned = ", ".join(style["banned_phrases"][:15])
    
    word_count = style["general_rules"]["word_count"].get(post_type, "650-850 words")
    
    research_text = f"""
Topic: {topic}
Research summary: {research.get('answer', '')}
Key facts from sources: {' | '.join(research.get('sources', [])[:3])}
"""
    
    system_prompt = f"""You are a senior journalist at Riclivo.online, a global news blog.

WRITING RULES:
- Tone: {niche_tone}
- Word count: {word_count}
- Max 3 sentences per paragraph
- NEVER use these phrases: {banned}
- Start with a hook — surprising fact, bold statement or question. NEVER start with "In today's" or "In recent years"
- Use "you" and "we" to connect with readers
- Include one strong opinion or prediction
- End with a question or bold prediction to spark comments
- Write naturally — if someone read this they should think a human journalist wrote it
- Vary sentence length — mix short punchy sentences with longer ones

NICHE: {niche_name}
BLOG: Riclivo.online — covers Tech, AI, Health, Finance, Entertainment, Football, Sports and News

{extra_context}

Return ONLY the blog post content in markdown format. 
First line should be the title as # Title
Do not include any preamble or explanation."""

    user_prompt = f"""Write a {post_type} blog post about this topic:

{research_text}

Remember: Sound like a human journalist, not AI. Be opinionated. Be specific. Be engaging."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=2000,
            temperature=0.85
        )
        
        content = response.choices[0].message.content
        return content
    
    except Exception as e:
        print(f"OpenAI error: {e}")
        return None

def generate_social_captions(title, excerpt, niche_name, post_url):
    """Generate platform-specific social media captions"""
    
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    social_style = STYLE_GUIDE["social_captions"]
    
    prompt = f"""Generate social media captions for this blog post:
Title: {title}
Excerpt: {excerpt[:300]}
Niche: {niche_name}
URL: {post_url}

Generate ALL of these in JSON format:
{{
  "twitter": "punchy hook + 1 key fact + URL + max 2 hashtags (max 280 chars total)",
  "instagram": "emotional hook + 3-4 sentences + 'Full story at link in bio 👆' + 8 relevant hashtags",
  "pinterest": "descriptive keyword-rich caption + 5 hashtags"
}}

Twitter style: {social_style['twitter']['style']}
Instagram style: {social_style['instagram']['style']}

Return ONLY valid JSON, nothing else."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.8
        )
        
        captions_text = response.choices[0].message.content.strip()
        captions_text = captions_text.replace("```json", "").replace("```", "").strip()
        captions = json.loads(captions_text)
        return captions
    
    except Exception as e:
        print(f"Caption error: {e}")
        return {
            "twitter": f"{title} {post_url} #Riclivo",
            "instagram": f"{title}\n\nFull story at link in bio 👆\n#Riclivo #News",
            "pinterest": f"{title} #Riclivo #News"
        }

# ============================================
# CREATE HUGO POST FILE
# ============================================
def slugify(title):
    """Convert title to URL slug"""
    import re
    slug = title.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    slug = slug.strip('-')
    return slug[:80]

def create_hugo_post(title, content, niche_name, image_path, photographer, captions, post_type="regular", is_repost=False):
    """Create a Hugo markdown post file"""
    
    niche = NICHES.get(niche_name, NICHES["News"])
    slug = slugify(title)
    date_str = NOW.strftime("%Y-%m-%dT%H:%M:%S-05:00")
    
    # Extract excerpt from content (first paragraph after title)
    lines = content.split('\n')
    excerpt_lines = [l for l in lines if l.strip() and not l.startswith('#')]
    excerpt = excerpt_lines[0][:200] if excerpt_lines else title
    
    # Build tags
    tags = [niche_name, "Riclivo", "News"]
    if "Messi" in title or "Ronaldo" in title:
        tags.extend(["Messi", "Ronaldo", "Football"])
    if "Premier League" in title or "EPL" in title:
        tags.extend(["PremierLeague", "EPL"])
    if post_type == "vs":
        tags.append("VS")
    if post_type == "weekly_special":
        tags.append("WeeklySpecial")
    
    # Build weight for featured posts (specials stay on front page longer)
    weight = 10 if post_type in ["weekly_special", "peak"] else 0
    
    cover_section = ""
    if image_path:
        cover_section = f"""cover:
    image: "{image_path}"
    alt: "{title}"
    caption: "Photo credit: {photographer or 'Pexels'}"
    relative: false"""
    
    # Social captions as YAML
    twitter_cap = captions.get("twitter", "").replace('"', "'")
    insta_cap = captions.get("instagram", "").replace('"', "'")[:300]
    
    frontmatter = f"""---
title: "{title.replace('"', "'")}"
date: {date_str}
draft: false
author: "Riclivo Editorial Team"
categories: ["{niche_name}"]
tags: {json.dumps(tags[:8])}
description: "{excerpt.replace('"', "'")}"
weight: {weight}
{cover_section}
social:
  twitter: "{twitter_cap}"
  instagram: "{insta_cap}"
---

"""
    
    # Remove the title from content (already in frontmatter)
    post_content = '\n'.join(lines[1:]).strip() if lines[0].startswith('#') else content
    
    # Add repost note if applicable
    if is_repost:
        post_content = f"*This topic is back in the news with new developments. Here's the updated story.*\n\n{post_content}"
    
    full_content = frontmatter + post_content
    
    # Create post directory and file
    post_dir = f"{CONTENT_DIR}"
    os.makedirs(post_dir, exist_ok=True)
    
    filename = f"{NOW.strftime('%Y-%m-%d')}-{slug}.md"
    filepath = f"{post_dir}/{filename}"
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_content)
    
    print(f"✅ Post created: {filepath}")
    return filepath, slug

# ============================================
# GIT PUSH
# ============================================
def git_push(message):
    """Commit and push to GitHub"""
    try:
        subprocess.run(["git", "config", "user.email", "n.c.denis@riclivo.com"], check=True)
        subprocess.run(["git", "config", "user.name", "Riclivo Bot"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "push"], check=True)
        print(f"✅ Pushed to GitHub: {message}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}")
        return False

# ============================================
# SEO PING - Tell Search Engines About New Post
# ============================================
def ping_search_engines(post_url):
    """Notify search engines about new post"""
    
    full_url = f"{SITE_URL}{post_url}"
    
    # IndexNow - notifies Bing, Yandex, and others at once
    try:
        indexnow_payload = {
            "host": "riclivo.online",
            "key": os.environ.get("INDEXNOW_KEY", "riclivo-indexnow-key"),
            "urlList": [full_url]
        }
        requests.post(
            "https://api.indexnow.org/indexnow",
            json=indexnow_payload,
            timeout=10
        )
        print(f"✅ IndexNow pinged: {full_url}")
    except Exception as e:
        print(f"IndexNow error: {e}")
    
    # Ping Google via Search Console API (if token available)
    gsc_token = os.environ.get("GOOGLE_SEARCH_CONSOLE_TOKEN")
    if gsc_token:
        try:
            requests.post(
                f"https://indexing.googleapis.com/v3/urlNotifications:publish",
                json={"url": full_url, "type": "URL_UPDATED"},
                headers={"Authorization": f"Bearer {gsc_token}"},
                timeout=10
            )
            print(f"✅ Google Search Console notified")
        except Exception as e:
            print(f"GSC error: {e}")

# ============================================
# MAIN REGULAR POST FLOW
# ============================================
def create_regular_post(niche_pair=None):
    """Create a regular rotation post"""
    
    rotation = load_rotation()
    posted_topics = load_posted_topics()
    
    # Reset daily count if new day
    today = NOW.strftime("%Y-%m-%d")
    if rotation.get("last_date") != today:
        rotation["daily_count"] = 0
        rotation["last_date"] = today
    
    # Check daily limit
    max_posts = NICHE_CONFIG["max_daily_posts"]
    if rotation["daily_count"] >= max_posts:
        print(f"Daily post limit reached ({max_posts})")
        return
    
    # Get niche pair for this rotation
    if not niche_pair:
        pair_index = rotation.get("current_pair_index", 0) % len(ROTATION_PAIRS)
        niche_pair = ROTATION_PAIRS[pair_index]
        rotation["current_pair_index"] = (pair_index + 1) % len(ROTATION_PAIRS)
    
    # Try each niche in the pair
    for niche_name in niche_pair:
        niche = NICHES.get(niche_name)
        if not niche:
            continue
        
        print(f"🔍 Searching trends for: {niche_name}")
        
        # Get trending topics
        topics = get_trending_topics(
            niche["keywords"],
            niche["countries"],
            niche["min_trend_score"]
        )
        
        if not topics:
            print(f"No trending topics found for {niche_name}")
            continue
        
        # Find non-duplicate topic
        chosen_topic = None
        is_repost = False
        
        for topic in topics:
            title = topic["title"]
            
            dup, days_ago = is_duplicate(title, posted_topics)
            if dup:
                print(f"⏭ Skipping duplicate: {title}")
                continue
            
            # Check if old topic trending again (repost with fresh angle)
            repost, old_title, old_days = should_repost_old_topic(title, posted_topics)
            if repost:
                print(f"🔄 Reposting old topic with fresh angle: {title} (last posted {old_days} days ago)")
                is_repost = True
            
            chosen_topic = topic
            break
        
        if not chosen_topic:
            print(f"All topics for {niche_name} are duplicates")
            continue
        
        # Research the topic
        print(f"📚 Researching: {chosen_topic['title']}")
        research = research_topic(chosen_topic["title"], niche_name)
        
        # Write the post
        print(f"✍️ Writing post for: {chosen_topic['title']}")
        content = write_post(
            chosen_topic["title"],
            research,
            niche_name,
            "regular",
            f"This is for the {niche_name} section of Riclivo.online"
        )
        
        if not content:
            continue
        
        # Extract title from content
        lines = content.strip().split('\n')
        post_title = lines[0].replace('#', '').strip() if lines[0].startswith('#') else chosen_topic["title"]
        
        # Fetch image
        print(f"🖼️ Fetching image...")
        slug = slugify(post_title)
        image_path, photographer = fetch_image(niche_name + " " + post_title[:30], slug)
        
        # Generate social captions
        excerpt = lines[2] if len(lines) > 2 else post_title
        post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
        captions = generate_social_captions(post_title, excerpt, niche_name, f"{SITE_URL}{post_url}")
        
        # Create Hugo post
        filepath, slug = create_hugo_post(
            post_title, content, niche_name,
            image_path, photographer, captions,
            "regular", is_repost
        )
        
        # Update posted topics
        posted_topics[post_title] = NOW.isoformat()
        save_posted_topics(posted_topics)
        
        # Update rotation
        rotation["daily_count"] += 1
        save_rotation(rotation)
        
        # Push to GitHub
        git_push(f"[{niche_name}] {post_title[:60]}")
        
        # Ping search engines
        ping_search_engines(post_url)
        
        print(f"🎉 Post published: {post_title}")
        
        # Small delay between niches
        time.sleep(2)

# ============================================
# PEAK HOUR POST - Most Trending Right Now
# ============================================
def create_peak_post():
    """Create peak hour post with hottest trending topic"""
    
    print("⚡ Creating PEAK HOUR post - finding hottest trend...")
    
    posted_topics = load_posted_topics()
    best_topic = None
    best_score = 0
    best_niche = None
    
    # Search all niches for highest trending topic
    for niche_name, niche in NICHES.items():
        topics = get_trending_topics(
            niche["keywords"],
            niche["countries"],
            NICHE_CONFIG["peak_hour_threshold"]
        )
        
        for topic in topics:
            if topic["score"] > best_score:
                dup, _ = is_duplicate(topic["title"], posted_topics)
                if not dup:
                    best_topic = topic
                    best_score = topic["score"]
                    best_niche = niche_name
    
    if not best_topic:
        print("No peak topic found, running regular post instead")
        create_regular_post()
        return
    
    print(f"🔥 Peak topic found: {best_topic['title']} (score: {best_score})")
    
    research = research_topic(best_topic["title"], best_niche)
    content = write_post(best_topic["title"], research, best_niche, "peak_post")
    
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image(best_niche + " " + post_title[:30], slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, best_niche, f"{SITE_URL}{post_url}")
    
    filepath, slug = create_hugo_post(
        post_title, content, best_niche,
        image_path, photographer, captions, "peak"
    )
    
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    rotation = load_rotation()
    rotation["daily_count"] = rotation.get("daily_count", 0) + 1
    save_rotation(rotation)
    
    git_push(f"[PEAK] {post_title[:60]}")
    ping_search_engines(post_url)
    
    print(f"🎉 Peak post published: {post_title}")

# ============================================
# MAIN ENTRY POINT
# ============================================
def main():
    print(f"\n{'='*50}")
    print(f"Riclivo Automation — {DAY_NAME} {NOW.strftime('%I:%M %p')} EST")
    print(f"{'='*50}\n")
    
    schedule = get_schedule_for_now()
    
    print(f"Schedule type: {schedule['type']}")
    if schedule.get("special"):
        print(f"Special post: {schedule['special']}")
    
    if schedule["type"] == "peak":
        create_peak_post()
    
    elif schedule["type"] == "special":
        # Import and run the appropriate special post generator
        from scripts.weekly_special import create_special_post
        create_special_post(schedule["special"])
    
    elif schedule["type"] == "regular":
        create_regular_post()
    
    print(f"\n✅ Automation run complete")

if __name__ == "__main__":
    main()
