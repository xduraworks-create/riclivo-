#!/usr/bin/env python3
"""
TAG GENERATOR — Add this function to automate.py
Generates 6-7 relevant hashtags per post
"""

def generate_tags(title, niche_name, research_text=""):
    """Generate 6-7 relevant tags for a post"""
    
    from openai import OpenAI
    import os
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    prompt = f"""Generate exactly 7 relevant hashtag tags for this blog post.

Title: {title}
Niche: {niche_name}
Context: {research_text[:300]}

Rules:
- Return ONLY a JSON array of 7 strings
- No # symbol in the tags
- Mix broad tags (AI, Technology) with specific ones (ChatGPT, OpenAI, GPT4)
- Include niche tag, topic tags, and trend tags
- CamelCase for multi-word tags
- Example: ["AI", "OpenAI", "ChatGPT", "ArtificialIntelligence", "TechNews", "AITools", "FutureOfWork"]

Return ONLY the JSON array, nothing else."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.7
        )
        text = response.choices[0].message.content.strip()
        text = text.replace("```json","").replace("```","").strip()
        tags = json.loads(text)
        # Always include niche and Riclivo
        base_tags = [niche_name, "Riclivo", "RiclivoOnline"]
        all_tags = list(dict.fromkeys(tags + base_tags))
        return all_tags[:8]
    except Exception as e:
        print(f"Tag generation error: {e}")
        return [niche_name, "Riclivo", "News", "Trending", "RiclivoOnline"]


# PASTE THIS INTO create_hugo_post() in automate.py
# Replace the existing tags section with:
"""
# Generate tags (6-7 relevant ones)
tags = generate_tags(title, niche_name, research.get('answer', '') if research else '')
"""

# Also update the frontmatter tags line to use the generated tags:
"""
tags: {json.dumps(tags)}
"""
