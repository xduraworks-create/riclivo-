#!/usr/bin/env python3
"""
Riclivo.online Weekly Specials & VS Post Generator
Handles all scheduled special content
"""

import os
import json
import time
import requests
import subprocess
from datetime import datetime
from pathlib import Path
import pytz
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automate import (
    write_post, fetch_image, fetch_two_images,
    create_hugo_post, generate_social_captions,
    research_topic, get_trending_topics,
    git_push, ping_search_engines, slugify,
    load_posted_topics, save_posted_topics,
    load_rotation, save_rotation,
    TAVILY_API_KEY, OPENAI_API_KEY, PEXELS_API_KEY,
    NICHES, STYLE_GUIDE, NICHE_CONFIG,
    NOW, SITE_URL, EST
)

from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# ============================================
# VS POST GENERATOR
# ============================================
def find_vs_topics(niche_names):
    """Find two trending topics in same niche for VS comparison"""
    
    all_topics = []
    for niche_name in niche_names:
        niche = NICHES.get(niche_name, {})
        topics = get_trending_topics(
            niche.get("keywords", []),
            niche.get("countries", ["US"]),
            niche.get("min_trend_score", 40)
        )
        for t in topics[:3]:
            t["niche"] = niche_name
            all_topics.append(t)
    
    if len(all_topics) >= 2:
        return all_topics[0], all_topics[1]
    return None, None

def write_vs_post(topic_a, topic_b, niche_name):
    """Write a 5-paragraph VS post"""
    
    research_a = research_topic(topic_a["title"], niche_name)
    time.sleep(1)
    research_b = research_topic(topic_b["title"], niche_name)
    
    niche_tone = STYLE_GUIDE["niche_tones"].get(niche_name, "")
    vs_rules = STYLE_GUIDE["vs_format"]
    banned = ", ".join(STYLE_GUIDE["banned_phrases"][:12])
    
    prompt = f"""You are a senior journalist at Riclivo.online writing a VS comparison post.

STRICT STRUCTURE — EXACTLY 5 PARAGRAPHS:
Paragraph 1 INTRO: {vs_rules['paragraph_1']}
Paragraph 2 ABOUT A: {vs_rules['paragraph_2']}
Paragraph 3 ABOUT B: {vs_rules['paragraph_3']}
Paragraph 4 COMPARISON: {vs_rules['paragraph_4']}
Paragraph 5 CONCLUSION: {vs_rules['paragraph_5']}

RULES:
- {chr(10).join(vs_rules['rules'])}
- NEVER use these phrases: {banned}
- Tone: {niche_tone}
- Word count: 950-1100 words total
- Write like a human journalist — opinionated, specific, engaging

SUBJECT A: {topic_a['title']}
Research A: {research_a.get('answer', '')}
Sources A: {' | '.join(research_a.get('sources', [])[:2])}

SUBJECT B: {topic_b['title']}
Research B: {research_b.get('answer', '')}
Sources B: {' | '.join(research_b.get('sources', [])[:2])}

Write a compelling VS post comparing these two. The title should follow this format:
[A] vs [B]: [Compelling hook about what makes this comparison interesting]

Return ONLY the post in markdown starting with # Title"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500,
            temperature=0.85
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"VS writing error: {e}")
        return None

def create_vs_post(vs_type):
    """Create a Wednesday VS post"""
    
    niche_map = {
        "vs_tech_ai": ["Technology", "AI"],
        "vs_football_sports": ["Football", "Sports"],
        "vs_health_finance": ["Health", "Finance"],
        "vs_entertainment": ["Entertainment", "News"]
    }
    
    niche_names = niche_map.get(vs_type, ["Technology", "AI"])
    primary_niche = niche_names[0]
    
    print(f"⚔️ Creating VS post for niches: {niche_names}")
    
    topic_a, topic_b = find_vs_topics(niche_names)
    
    if not topic_a or not topic_b:
        print(f"Could not find VS topics for {vs_type}")
        return
    
    print(f"VS Topics: {topic_a['title']} vs {topic_b['title']}")
    
    content = write_vs_post(topic_a, topic_b, primary_niche)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    
    # Fetch TWO images for VS post
    img_a, img_b, photo_a, photo_b = fetch_two_images(
        topic_a["title"][:40],
        topic_b["title"][:40],
        slug
    )
    
    # Use first image as cover (both referenced in content)
    cover_image = img_a
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, primary_niche, f"{SITE_URL}{post_url}")
    
    # Add VS image credits to content
    vs_images = ""
    if img_a and img_b:
        vs_images = f"\n\n![{topic_a['title'][:40]}]({img_a}) ![{topic_b['title'][:40]}]({img_b})\n*Images: Pexels*\n"
    
    # Insert VS images after intro paragraph
    post_lines = content.split('\n')
    insert_at = 4
    post_lines.insert(insert_at, vs_images)
    final_content = '\n'.join(post_lines)
    
    filepath, final_slug = create_hugo_post(
        post_title, final_content, primary_niche,
        cover_image, photo_a, captions, "vs"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    rotation = load_rotation()
    rotation["daily_count"] = rotation.get("daily_count", 0) + 1
    save_rotation(rotation)
    
    git_push(f"[VS] {post_title[:60]}")
    ping_search_engines(post_url)
    
    print(f"🎉 VS post published: {post_title}")

# ============================================
# WEEKLY SPECIALS WRITER
# ============================================
def write_weekly_special(special_type, research_data, extra_context=""):
    """Write weekly special content"""
    
    specials = STYLE_GUIDE["weekly_specials"]
    special_config = specials.get(special_type, {})
    banned = ", ".join(STYLE_GUIDE["banned_phrases"][:12])
    
    prompt = f"""You are a senior journalist at Riclivo.online writing a weekly special post.

SPECIAL TYPE: {special_type}
TITLE FORMAT: {special_config.get('title_format', '')}
STRUCTURE: {special_config.get('structure', '')}
TONE: {special_config.get('tone', 'engaging and informative')}

RULES:
- Word count: 1200-1500 words
- NEVER use these phrases: {banned}
- Write like a human journalist — specific, opinionated, engaging
- Max 3 sentences per paragraph
- Include specific names, numbers, and real details

RESEARCH DATA:
{json.dumps(research_data, indent=2)[:3000]}

{extra_context}

Return ONLY the post in markdown starting with # Title"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.85
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Special writing error: {e}")
        return None

# ============================================
# INDIVIDUAL SPECIAL POST CREATORS
# ============================================
def create_ai_app_week():
    """Friday 11AM - AI App of the Week"""
    print("🤖 Creating AI App of the Week...")
    
    research = research_topic("top AI apps trending this week 2026", "AI")
    research2 = research_topic("new AI tools launched this week", "AI")
    
    research_data = {
        "ai_apps_trending": research,
        "new_ai_tools": research2
    }
    
    extra = """Feature exactly 3 AI apps. For each app include:
1. What it is (1-2 sentences)
2. Why it's trending this week
3. How it impacts everyday users
4. Honest rating out of 10
5. Tag format: @AppName (for social media)

Make each app section feel like a mini-review, not a press release."""
    
    content = write_weekly_special("friday_ai_app", research_data, extra)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image("artificial intelligence apps technology", slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, "AI", f"{SITE_URL}{post_url}")
    
    filepath, final_slug = create_hugo_post(
        post_title, content, "AI",
        image_path, photographer, captions, "weekly_special"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    git_push(f"[AI WEEKLY] {post_title[:60]}")
    ping_search_engines(post_url)
    print(f"🎉 AI App of the Week published: {post_title}")

def create_ladies_corner():
    """Friday 9AM - Ladies Corner Health"""
    print("👩 Creating Ladies Corner...")
    
    research = research_topic("women health fitness wellness trending topics this week", "Health")
    research2 = research_topic("women health news 2026 latest", "Health")
    
    research_data = {"health_topics": research, "health_news": research2}
    
    extra = """Cover exactly 3 women's health/fitness topics. Each section should be extensive and informative.
Write warmly and empoweringly — like a knowledgeable older sister sharing important health information.
Include practical advice readers can act on today. Reference real studies or expert opinions where possible."""
    
    content = write_weekly_special("friday_ladies_corner", research_data, extra)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image("women health fitness wellness", slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, "Health", f"{SITE_URL}{post_url}")
    
    filepath, final_slug = create_hugo_post(
        post_title, content, "Health",
        image_path, photographer, captions, "weekly_special"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    git_push(f"[LADIES CORNER] {post_title[:60]}")
    ping_search_engines(post_url)
    print(f"🎉 Ladies Corner published: {post_title}")

def create_money_move_monday():
    """Monday 7AM - Money Move Monday"""
    print("💰 Creating Money Move Monday...")
    
    research = research_topic("best financial advice money tip investment this week 2026", "Finance")
    research_data = {"finance_tips": research}
    
    extra = """Give ONE specific, actionable money tip. Be concrete — specific steps, specific numbers, specific platforms.
This should be something a reader can literally start doing today or this week.
Relevant for US, UK, Canada and Nigerian readers where possible."""
    
    content = write_weekly_special("monday_money_move", research_data, extra)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image("money finance investment savings", slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, "Finance", f"{SITE_URL}{post_url}")
    
    filepath, final_slug = create_hugo_post(
        post_title, content, "Finance",
        image_path, photographer, captions, "weekly_special"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    git_push(f"[MONEY MONDAY] {post_title[:60]}")
    ping_search_engines(post_url)
    print(f"🎉 Money Move Monday published: {post_title}")

def create_messi_ronaldo_watch():
    """Tuesday - Messi & Ronaldo Watch"""
    print("⚽ Creating Messi & Ronaldo Watch...")
    
    messi_research = research_topic("Lionel Messi latest news this week goals transfer", "Football")
    ronaldo_research = research_topic("Cristiano Ronaldo latest news this week goals", "Football")
    
    research_data = {"messi": messi_research, "ronaldo": ronaldo_research}
    
    extra = """Dedicate roughly equal coverage to both Messi and Ronaldo.
Include specific match performances, goals, assists, statements, or transfer news from this week.
Include fan reactions and social media responses where relevant.
Be respectful and fair to both — this is not a debate post, it's an update on both legends."""
    
    content = write_weekly_special("tuesday_messi_ronaldo", research_data, extra)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image("football soccer stadium", slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, "Football", f"{SITE_URL}{post_url}")
    
    filepath, final_slug = create_hugo_post(
        post_title, content, "Football",
        image_path, photographer, captions, "weekly_special"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    git_push(f"[MESSI RONALDO] {post_title[:60]}")
    ping_search_engines(post_url)
    print(f"🎉 Messi & Ronaldo Watch published: {post_title}")

def create_crypto_corner():
    """Thursday 8PM - Crypto Corner"""
    print("₿ Creating Crypto Corner...")
    
    research = research_topic("Bitcoin Ethereum crypto market this week price 2026", "Finance")
    research2 = research_topic("top altcoin trending cryptocurrency news this week", "Finance")
    
    research_data = {"crypto_market": research, "altcoins": research2}
    
    extra = """Cover: Bitcoin price and sentiment, Ethereum update, one top altcoin story.
Include specific price points, percentage changes, and market cap where available.
End with what to watch next week. IMPORTANT: Never give direct financial advice — report facts and expert opinions only."""
    
    content = write_weekly_special("thursday_crypto", research_data, extra)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image("cryptocurrency bitcoin blockchain", slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, "Finance", f"{SITE_URL}{post_url}")
    
    filepath, final_slug = create_hugo_post(
        post_title, content, "Finance",
        image_path, photographer, captions, "weekly_special"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    git_push(f"[CRYPTO] {post_title[:60]}")
    ping_search_engines(post_url)
    print(f"🎉 Crypto Corner published: {post_title}")

def create_nigerian_spotlight():
    """Saturday 11AM - Nigerian Spotlight"""
    print("🇳🇬 Creating Nigerian Spotlight...")
    
    research = research_topic("Nigeria news this week economy Naira business 2026", "News")
    research2 = research_topic("Super Eagles Nigeria football news this week", "Football")
    
    research_data = {"nigeria_news": research, "super_eagles": research2}
    
    extra = """This post is specifically for Nigerian readers and the Nigerian diaspora.
Cover 3 Nigeria-relevant stories: one business/economy story, one general news, one sports (Super Eagles if relevant).
Include Naira exchange rate context where relevant. Speak to the Nigerian experience with global context.
Be proud, honest and informative — not sensationalist."""
    
    content = write_weekly_special("saturday_nigerian_spotlight", research_data, extra)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image("Nigeria Lagos Africa city", slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, "News", f"{SITE_URL}{post_url}")
    
    filepath, final_slug = create_hugo_post(
        post_title, content, "News",
        image_path, photographer, captions, "weekly_special"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    git_push(f"[NIGERIA] {post_title[:60]}")
    ping_search_engines(post_url)
    print(f"🎉 Nigerian Spotlight published: {post_title}")

def create_app_of_day():
    """Daily 6AM - App of the Day"""
    print("📱 Creating App of the Day...")
    
    research = research_topic("trending app launched viral mobile app today 2026", "Technology")
    research_data = {"app_trends": research}
    
    extra = """Feature exactly ONE app. Keep it short (280-350 words).
What it does, why it's trending TODAY, who it's for, where to download, quick rating.
Like a friend texting you about a cool new app they just found."""
    
    content = write_weekly_special("app_of_day", research_data, extra)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image("smartphone app mobile technology", slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, "Technology", f"{SITE_URL}{post_url}")
    
    filepath, final_slug = create_hugo_post(
        post_title, content, "Technology",
        image_path, photographer, captions, "weekly_special"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    git_push(f"[APP OF DAY] {post_title[:60]}")
    ping_search_engines(post_url)
    print(f"🎉 App of the Day published: {post_title}")

def create_weekend_kickoff():
    """Saturday 8AM - Weekend Kickoff Football"""
    print("⚽ Creating Weekend Kickoff...")
    
    research = research_topic("Premier League La Liga Serie A Bundesliga fixtures Saturday this weekend", "Football")
    research2 = research_topic("football predictions this weekend match preview", "Football")
    
    research_data = {"fixtures": research, "predictions": research2}
    
    extra = """Cover all major Saturday football fixtures across EPL, La Liga, Serie A, Bundesliga, Ligue 1.
For each key match: teams, kick-off time (convert to EST and BST), key players to watch, quick prediction.
End with one bold prediction for the day's standout match."""
    
    content = write_weekly_special("saturday_weekend_kickoff", research_data, extra)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image("football stadium crowd match", slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, "Football", f"{SITE_URL}{post_url}")
    
    filepath, final_slug = create_hugo_post(
        post_title, content, "Football",
        image_path, photographer, captions, "weekly_special"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    git_push(f"[KICKOFF] {post_title[:60]}")
    ping_search_engines(post_url)
    print(f"🎉 Weekend Kickoff published: {post_title}")

def create_sunday_read():
    """Sunday 8AM - The Sunday Read"""
    print("☀️ Creating Sunday Read...")
    
    research = research_topic("biggest most interesting news story this week 2026", "News")
    research_data = {"top_story": research}
    
    extra = """This is the premium long-form post of the week. 1400-1500 words minimum.
Pick the MOST interesting story of the week — not necessarily the most viral, but the most meaningful.
Write a deep, thoughtful piece: background → what happened → why it matters → different perspectives → what comes next.
This should be the kind of piece people bookmark and share. Make the reader feel smarter after reading it."""
    
    content = write_weekly_special("sunday_read", research_data, extra)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image("newspaper journalism reading sunday", slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, "News", f"{SITE_URL}{post_url}")
    
    filepath, final_slug = create_hugo_post(
        post_title, content, "News",
        image_path, photographer, captions, "weekly_special"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    git_push(f"[SUNDAY READ] {post_title[:60]}")
    ping_search_engines(post_url)
    print(f"🎉 Sunday Read published: {post_title}")

def create_transfer_mill():
    """Sunday 3PM - Transfer Rumour Mill"""
    print("🔄 Creating Transfer Rumour Mill...")
    
    research = research_topic("football transfer news rumours deals confirmed this week", "Football")
    research2 = research_topic("Premier League transfer window gossip news 2026", "Football")
    
    research_data = {"transfers": research, "epl_transfers": research2}
    
    extra = """Cover: Confirmed deals (this week), Hot rumours with credibility rating (HOT/WARM/COLD),
Players to watch, Deals that collapsed. Rate rumour credibility honestly.
Cover all major leagues: EPL, La Liga, Serie A, Bundesliga, Ligue 1, Turkish Süper Lig."""
    
    content = write_weekly_special("sunday_transfer_mill", research_data, extra)
    if not content:
        return
    
    lines = content.strip().split('\n')
    post_title = lines[0].replace('#', '').strip()
    slug = slugify(post_title)
    image_path, photographer = fetch_image("football player transfer contract signing", slug)
    
    post_url = f"/posts/{NOW.strftime('%Y-%m-%d')}-{slug}/"
    excerpt = lines[2] if len(lines) > 2 else post_title
    captions = generate_social_captions(post_title, excerpt, "Football", f"{SITE_URL}{post_url}")
    
    filepath, final_slug = create_hugo_post(
        post_title, content, "Football",
        image_path, photographer, captions, "weekly_special"
    )
    
    posted_topics = load_posted_topics()
    posted_topics[post_title] = NOW.isoformat()
    save_posted_topics(posted_topics)
    
    git_push(f"[TRANSFERS] {post_title[:60]}")
    ping_search_engines(post_url)
    print(f"🎉 Transfer Rumour Mill published: {post_title}")

# ============================================
# MAIN DISPATCHER
# ============================================
def create_special_post(special_type):
    """Route to correct special post creator"""
    
    creators = {
        "ai_app_week": create_ai_app_week,
        "ladies_corner": create_ladies_corner,
        "money_move_monday": create_money_move_monday,
        "messi_ronaldo_watch": create_messi_ronaldo_watch,
        "crypto_corner": create_crypto_corner,
        "nigerian_spotlight": create_nigerian_spotlight,
        "app_of_day": create_app_of_day,
        "weekend_kickoff": create_weekend_kickoff,
        "sunday_read": create_sunday_read,
        "transfer_mill": create_transfer_mill,
        "vs_tech_ai": lambda: create_vs_post("vs_tech_ai"),
        "vs_football_sports": lambda: create_vs_post("vs_football_sports"),
        "vs_health_finance": lambda: create_vs_post("vs_health_finance"),
        "vs_entertainment": lambda: create_vs_post("vs_entertainment"),
    }
    
    creator = creators.get(special_type)
    if creator:
        creator()
    else:
        print(f"Unknown special type: {special_type}")
        # Fall back to regular post
        from automate import create_regular_post
        create_regular_post()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        create_special_post(sys.argv[1])
