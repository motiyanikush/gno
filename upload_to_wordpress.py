#!/usr/bin/env python3
"""
GNO CloudBot - Upload to WordPress
Uploads approved client win screenshots to WordPress and generates a premium HTML page.
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WP_URL = os.environ.get("WP_URL") or os.environ.get("WP_BASE_URL", "https://gnopartners.com")
WP_USERNAME = os.environ.get("WP_USERNAME", "")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")
APPROVED_WINS_FILE = Path("./approved_wins.json")
SCREENSHOTS_DIR = Path("./screenshots")
WP_PAGE_SLUG = "client-wins"
WP_PAGE_TITLE = "Client Wins"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def clean_company_name(channel_name: str) -> str:
    """Convert '#the-bald-brothers-gno' → 'The Bald Brothers'."""
    name = channel_name.lstrip("#")
    # Remove common suffixes like '-gno', '-agency', '-client'
    for suffix in ["-gno", "-agency", "-client", "-partners"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    words = name.replace("-", " ").replace("_", " ").split()
    return " ".join(word.capitalize() for word in words)


def load_approved_wins() -> list[dict]:
    """Load approved_wins.json and return entries ready for upload."""
    if not APPROVED_WINS_FILE.exists():
        print(f"[WARN] {APPROVED_WINS_FILE} not found — returning empty list.")
        return []
    with open(APPROVED_WINS_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    # Support both a plain list and {"wins": [...]} structure
    if isinstance(data, list):
        return data
    return data.get("wins", [])


def wp_auth_header() -> dict:
    """Generate Basic Auth header for WordPress REST API."""
    token = base64.b64encode(f"{WP_USERNAME}:{WP_APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def wp_upload_image(filepath: Path, title: str) -> str | None:
    """Upload an image to the WordPress Media Library. Returns the image URL."""
    url = f"{WP_URL}/wp-json/wp/v2/media"
    headers = wp_auth_header()
    headers["Content-Disposition"] = f'attachment; filename="{filepath.name}"'
    mime = "image/png" if filepath.suffix.lower() == ".png" else "image/jpeg"
    headers["Content-Type"] = mime

    with open(filepath, "rb") as fh:
        response = requests.post(url, headers=headers, data=fh, timeout=60)

    if response.status_code in (200, 201):
        media = response.json()
        image_url: str = media.get("source_url", "")
        print(f"[OK]   Uploaded {filepath.name} → {image_url}")
        return image_url

    print(f"[ERR]  Failed to upload {filepath.name}: {response.status_code} {response.text}")
    return None


def wp_find_page(slug: str) -> int | None:
    """Find an existing WordPress page by slug. Returns page ID or None."""
    url = f"{WP_URL}/wp-json/wp/v2/pages"
    params = {"slug": slug, "status": "any"}
    response = requests.get(url, headers=wp_auth_header(), params=params, timeout=30)
    if response.status_code == 200:
        pages = response.json()
        if pages:
            return int(pages[0]["id"])
    return None


def wp_create_or_update_page(
    page_id: int | None,
    title: str,
    content: str,
    slug: str,
) -> int | None:
    """Create or update a WordPress page. Returns the page ID."""
    headers = wp_auth_header()
    headers["Content-Type"] = "application/json"
    payload = {
        "title": title,
        "content": content,
        "slug": slug,
        "status": "publish",
    }
    if page_id:
        url = f"{WP_URL}/wp-json/wp/v2/pages/{page_id}"
        response = requests.post(url, headers=headers, json=payload, timeout=30)
    else:
        url = f"{WP_URL}/wp-json/wp/v2/pages"
        response = requests.post(url, headers=headers, json=payload, timeout=30)

    if response.status_code in (200, 201):
        pid = int(response.json()["id"])
        action = "updated" if page_id else "created"
        print(f"[OK]   Page {action}: {WP_URL}/?page_id={pid}")
        return pid

    print(f"[ERR]  Page operation failed: {response.status_code} {response.text}")
    return None


def build_page_html(wins_with_images: list[dict]) -> str:
    """
    Build a self-contained premium HTML string for the WordPress Client Wins page.

    Each item in wins_with_images has:
        - company_name  (str)
        - image_url     (str)
        - category      (str)
        - date          (str, optional)
    """
    now = datetime.now().strftime("%B %d, %Y")
    total_wins = len(wins_with_images)

    # ── Logo strip items (monogram badges) ──────────────────────────────────
    def monogram_badge(name: str, size: int = 56, font: int = 22) -> str:
        letter = name[0].upper() if name else "G"
        return (
            f'<div class="mono-badge" style="width:{size}px;height:{size}px;'
            f'font-size:{font}px">{letter}</div>'
        )

    logo_items_html = "".join(
        f'<div class="marquee-item">'
        f'{monogram_badge(w["company_name"])}'
        f'<span class="marquee-label">{w["company_name"]}</span>'
        f"</div>"
        for w in wins_with_images
    )
    # Duplicate for seamless loop
    marquee_html = logo_items_html * 2

    # ── Wins grid cards ─────────────────────────────────────────────────────
    cards_html = ""
    for i, win in enumerate(wins_with_images):
        company = win["company_name"]
        img_url = win["image_url"]
        category = win.get("category", "Client Win")
        date_str = win.get("date", "")
        delay = (i % 6) * 0.15

        cards_html += f"""
        <div class="win-card" data-index="{i}" style="animation-delay:{delay:.2f}s">
            <div class="card-header">
                {monogram_badge(company, 48, 18)}
                <div class="card-meta">
                    <span class="card-company">{company}</span>
                    <span class="card-sub">Client Channel</span>
                </div>
                <span class="category-badge">{category}</span>
            </div>
            <div class="card-img-wrap">
                <img src="{img_url}" alt="{company} — {category}" loading="lazy" />
            </div>
            {f'<div class="card-date">{date_str}</div>' if date_str else ''}
        </div>"""

    # ── Full HTML ────────────────────────────────────────────────────────────
    html = f"""
<style>
/* ── Google Fonts ──────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400;1,600&family=DM+Sans:wght@400;500;600&display=swap');

/* ── Reset / Base ──────────────────────────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
    --gold: #c8a44e;
    --gold-dark: #b8943e;
    --gold-darker: #a8862e;
    --bg-dark: #1a1a1a;
    --bg-darker: #0d0d0d;
    --text-light: #ffffff;
    --text-muted: #a0a0a0;
    --card-bg: #ffffff;
    --radius: 16px;
    --transition: cubic-bezier(0.16, 1, 0.3, 1);
}}

/* ── GSAP initial state: hidden (GSAP will reveal) ─────────────────────── */
.hero-badge, .hero-heading, .hero-sub, .stat-item,
.win-card, .cta-box {{ opacity: 0; }}

/* Fallback: show everything if JS disabled — handled by <noscript> block below */

/* ── Keyframes ─────────────────────────────────────────────────────────── */
@keyframes marquee-scroll {{
    from {{ transform: translateX(0); }}
    to   {{ transform: translateX(-50%); }}
}}
@keyframes orb-float {{
    0%, 100% {{ transform: translate(0, 0) scale(1); }}
    33%       {{ transform: translate(40px, -30px) scale(1.05); }}
    66%       {{ transform: translate(-20px, 20px) scale(0.96); }}
}}
@keyframes badge-pulse {{
    0%, 100% {{ box-shadow: 0 0 0 0 rgba(200,164,78,.4); }}
    50%       {{ box-shadow: 0 0 0 8px rgba(200,164,78,0); }}
}}

/* ── Layout wrappers ───────────────────────────────────────────────────── */
.gno-page {{ font-family: 'DM Sans', sans-serif; color: var(--text-light); background: var(--bg-darker); overflow-x: hidden; }}

/* ── HERO ──────────────────────────────────────────────────────────────── */
.hero {{
    position: relative;
    background: linear-gradient(160deg, #1a1a1a 0%, #0d0d0d 60%, #1a1714 100%);
    padding: 100px 24px 120px;
    text-align: center;
    overflow: hidden;
}}
.hero-orb {{
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    animation: orb-float 8s ease-in-out infinite;
    pointer-events: none;
}}
.hero-orb-1 {{
    width: 420px; height: 420px;
    background: radial-gradient(circle, rgba(200,164,78,.18) 0%, transparent 70%);
    top: -80px; left: -100px;
    animation-delay: 0s;
}}
.hero-orb-2 {{
    width: 320px; height: 320px;
    background: radial-gradient(circle, rgba(200,164,78,.12) 0%, transparent 70%);
    bottom: -60px; right: -60px;
    animation-delay: 3s;
}}
.hero-inner {{ position: relative; z-index: 1; max-width: 860px; margin: 0 auto; }}
.hero-badge {{
    display: inline-flex; align-items: center; gap: 8px;
    background: rgba(200,164,78,.12);
    border: 1px solid rgba(200,164,78,.35);
    color: var(--gold);
    font-family: 'DM Sans', sans-serif;
    font-size: .8rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
    padding: 8px 20px; border-radius: 100px;
    margin-bottom: 32px;
    animation: badge-pulse 3s ease-in-out infinite;
}}
.hero-heading {{
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: clamp(2.8rem, 6vw, 5rem);
    font-weight: 600; line-height: 1.1;
    color: var(--text-light);
    margin-bottom: 24px;
}}
.hero-heading em {{ color: var(--gold); font-style: italic; }}
.hero-sub {{
    font-size: clamp(.95rem, 2vw, 1.15rem);
    color: var(--text-muted);
    line-height: 1.7;
    max-width: 620px;
    margin: 0 auto 56px;
}}
.stats-row {{
    display: flex; flex-wrap: wrap; justify-content: center; gap: 16px 48px;
}}
.stat-item {{
    display: flex; flex-direction: column; align-items: center; gap: 4px;
    min-width: 130px;
}}
.stat-number {{
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: clamp(2rem, 4vw, 2.8rem);
    font-weight: 600;
    color: var(--gold);
    line-height: 1;
}}
.stat-label {{
    font-size: .8rem; color: var(--text-muted);
    letter-spacing: .08em; text-transform: uppercase;
}}

/* ── MARQUEE ───────────────────────────────────────────────────────────── */
.marquee-section {{
    background: var(--bg-dark);
    border-top: 1px solid rgba(200,164,78,.12);
    border-bottom: 1px solid rgba(200,164,78,.12);
    padding: 40px 0;
    overflow: hidden;
    position: relative;
}}
.marquee-section::before,
.marquee-section::after {{
    content: '';
    position: absolute; top: 0; bottom: 0; width: 120px; z-index: 2;
    pointer-events: none;
}}
.marquee-section::before {{ left: 0;  background: linear-gradient(to right,  var(--bg-dark), transparent); }}
.marquee-section::after  {{ right: 0; background: linear-gradient(to left, var(--bg-dark), transparent); }}
.marquee-label-heading {{
    text-align: center;
    font-size: .72rem; letter-spacing: .18em; text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 24px;
}}
.marquee-track {{
    display: flex;
    width: max-content;
    animation: marquee-scroll 32s linear infinite;
}}
.marquee-item {{
    display: flex; align-items: center; gap: 12px;
    margin: 0 28px;
    white-space: nowrap;
}}
.marquee-label {{
    font-size: .9rem; color: var(--text-muted);
    font-weight: 500;
}}

/* ── MONOGRAM BADGE ────────────────────────────────────────────────────── */
.mono-badge {{
    display: inline-flex; align-items: center; justify-content: center;
    border-radius: 50%;
    background: var(--bg-dark);
    border: 1.5px solid rgba(200,164,78,.4);
    color: var(--gold);
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-weight: 600;
    flex-shrink: 0;
}}

/* ── WINS GRID ─────────────────────────────────────────────────────────── */
.wins-section {{
    background: #f5f4f0;
    padding: 96px 24px;
}}
.section-heading {{
    text-align: center;
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: clamp(1.6rem, 3.5vw, 2.4rem);
    font-weight: 600;
    color: var(--bg-dark);
    margin-bottom: 64px;
    display: flex; align-items: center; justify-content: center; gap: 16px;
}}
.section-heading::before,
.section-heading::after {{
    content: '';
    flex: 1; max-width: 120px;
    height: 1px;
    background: linear-gradient(to right, transparent, var(--gold));
}}
.section-heading::after {{
    background: linear-gradient(to left, transparent, var(--gold));
}}
.wins-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 28px;
    max-width: 1100px;
    margin: 0 auto;
}}
@media (min-width: 768px) {{
    .wins-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
.win-card {{
    background: var(--card-bg);
    border-radius: var(--radius);
    border: 1px solid rgba(0,0,0,.07);
    box-shadow: 0 4px 24px rgba(0,0,0,.07);
    overflow: hidden;
    transition: transform .4s var(--transition), box-shadow .4s var(--transition);
    cursor: default;
}}
.win-card:hover {{
    transform: translateY(-8px);
    box-shadow: 0 16px 48px rgba(200,164,78,.2), 0 4px 24px rgba(0,0,0,.1);
}}
.card-header {{
    display: flex; align-items: center; gap: 14px;
    padding: 20px 20px 16px;
    border-bottom: 1px solid rgba(0,0,0,.06);
}}
.card-meta {{ flex: 1; min-width: 0; }}
.card-company {{
    display: block;
    font-weight: 600; font-size: .95rem;
    color: var(--bg-dark);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.card-sub {{ font-size: .78rem; color: #888; }}
.category-badge {{
    font-size: .72rem; font-weight: 600;
    letter-spacing: .08em; text-transform: uppercase;
    color: var(--gold-dark);
    border: 1.5px solid var(--gold-dark);
    border-radius: 100px;
    padding: 4px 12px;
    white-space: nowrap;
    flex-shrink: 0;
}}
.card-img-wrap {{ width: 100%; overflow: hidden; background: #fafafa; }}
.card-img-wrap img {{
    width: 100%; display: block;
    object-fit: contain;
    transition: transform .6s var(--transition);
}}
.win-card:hover .card-img-wrap img {{ transform: scale(1.02); }}
.card-date {{
    font-size: .75rem; color: #bbb;
    padding: 10px 20px;
    text-align: right;
}}

/* ── CTA ───────────────────────────────────────────────────────────────── */
.cta-section {{
    background: linear-gradient(160deg, #1a1a1a 0%, #0d0d0d 60%, #1a1714 100%);
    padding: 96px 24px;
    text-align: center;
    position: relative;
    overflow: hidden;
}}
.cta-orb {{
    position: absolute; border-radius: 50%;
    filter: blur(100px); pointer-events: none;
    width: 500px; height: 500px;
    background: radial-gradient(circle, rgba(200,164,78,.14) 0%, transparent 70%);
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
}}
.cta-box {{
    position: relative; z-index: 1;
    max-width: 640px; margin: 0 auto;
}}
.cta-heading {{
    font-family: 'Cormorant Garamond', Georgia, serif;
    font-size: clamp(2rem, 4.5vw, 3.2rem);
    font-weight: 600; line-height: 1.15;
    color: var(--text-light);
    margin-bottom: 18px;
}}
.cta-heading em {{ color: var(--gold); font-style: italic; }}
.cta-sub {{
    font-size: 1rem; color: var(--text-muted);
    line-height: 1.6; margin-bottom: 40px;
}}
.cta-btn {{
    display: inline-flex; align-items: center; gap: 8px;
    background: linear-gradient(135deg, var(--gold) 0%, var(--gold-darker) 100%);
    color: #0d0d0d;
    font-family: 'DM Sans', sans-serif;
    font-weight: 700; font-size: .95rem;
    letter-spacing: .04em;
    padding: 16px 36px; border-radius: 100px;
    text-decoration: none;
    transition: transform .3s var(--transition), box-shadow .3s var(--transition);
}}
.cta-btn:hover {{
    transform: scale(1.04);
    box-shadow: 0 0 40px rgba(200,164,78,.5), 0 8px 32px rgba(0,0,0,.3);
}}

/* ── FOOTER ────────────────────────────────────────────────────────────── */
.gno-footer {{
    background: var(--bg-darker);
    border-top: 1px solid rgba(255,255,255,.06);
    padding: 24px;
    text-align: center;
    font-size: .78rem;
    color: #555;
    letter-spacing: .04em;
}}
</style>

<noscript><style>
.hero-badge, .hero-heading, .hero-sub, .stat-item,
.win-card, .cta-box {{ opacity: 1 !important; transform: none !important; }}
</style></noscript>

<div class="gno-page">

<!-- ── HERO ──────────────────────────────────────────────────────────────── -->
<section class="hero">
    <div class="hero-orb hero-orb-1"></div>
    <div class="hero-orb hero-orb-2"></div>
    <div class="hero-inner">
        <div class="hero-badge">✦ Verified Client Feedback</div>
        <h1 class="hero-heading">Our Clients Are <em>Winning</em></h1>
        <p class="hero-sub">Unfiltered messages from our client channels. Real results, real feedback, straight from the people we work with every day.</p>
        <div class="stats-row">
            <div class="stat-item">
                <span class="stat-number" data-target="350" data-suffix="+">0</span>
                <span class="stat-label">Active Clients</span>
            </div>
            <div class="stat-item">
                <span class="stat-number" data-target="200" data-suffix="+">0</span>
                <span class="stat-label">Brands Scaled</span>
            </div>
            <div class="stat-item">
                <span class="stat-number" data-target="22" data-prefix="$" data-suffix="M+">0</span>
                <span class="stat-label">Client Revenue Managed</span>
            </div>
        </div>
    </div>
</section>

<!-- ── MARQUEE ────────────────────────────────────────────────────────────── -->
<section class="marquee-section">
    <p class="marquee-label-heading">Trusted By Leading Brands</p>
    <div class="marquee-track">
        {marquee_html}
    </div>
</section>

<!-- ── WINS GRID ──────────────────────────────────────────────────────────── -->
<section class="wins-section">
    <h2 class="section-heading">Latest Wins</h2>
    <div class="wins-grid">
        {cards_html}
    </div>
</section>

<!-- ── CTA ────────────────────────────────────────────────────────────────── -->
<section class="cta-section">
    <div class="cta-orb"></div>
    <div class="cta-box">
        <h2 class="cta-heading">Ready to Become Our <em>Next Win?</em></h2>
        <p class="cta-sub">Join 200+ brands scaling profitably with GNO Partners</p>
        <a class="cta-btn" href="https://gnopartners.com/contact/">Get Free Growth Analysis &#8594;</a>
    </div>
</section>

<!-- ── FOOTER ─────────────────────────────────────────────────────────────── -->
<footer class="gno-footer">Last updated: {now}</footer>

</div><!-- .gno-page -->

<!-- ── GSAP ───────────────────────────────────────────────────────────────── -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js"></script>
<script>
(function () {{
    if (typeof gsap === 'undefined') return;
    gsap.registerPlugin(ScrollTrigger);

    // ── Hero timeline ────────────────────────────────────────────────────
    var heroTL = gsap.timeline({{ defaults: {{ ease: 'power3.out' }} }});
    heroTL
        .from('.hero-badge',   {{ opacity: 0, y: 20, duration: .8 }})
        .from('.hero-heading', {{ opacity: 0, y: 30, duration: .9, clipPath: 'inset(0 0 100% 0)', ease: 'power3.out' }}, '-=.4')
        .from('.hero-sub',     {{ opacity: 0, y: 20, duration: .8 }}, '-=.5')
        .from('.stat-item',    {{ opacity: 0, y: 24, duration: .7, stagger: .15 }}, '-=.4');

    // ── Stat counters ────────────────────────────────────────────────────
    document.querySelectorAll('.stat-number[data-target]').forEach(function (el) {{
        var target = parseFloat(el.getAttribute('data-target'));
        var prefix = el.getAttribute('data-prefix') || '';
        var suffix = el.getAttribute('data-suffix') || '';
        var obj = {{ val: 0 }};
        ScrollTrigger.create({{
            trigger: el,
            start: 'top 85%',
            once: true,
            onEnter: function () {{
                gsap.to(obj, {{
                    val: target,
                    duration: 2,
                    ease: 'power2.out',
                    snap: {{ val: target < 50 ? .1 : 1 }},
                    onUpdate: function () {{
                        el.textContent = prefix + Math.round(obj.val) + suffix;
                    }}
                }});
            }}
        }});
    }});

    // ── Win cards scroll reveal ─────────────────────────────────────────
    gsap.utils.toArray('.win-card').forEach(function (card, i) {{
        gsap.from(card, {{
            opacity: 0,
            y: 48,
            duration: .9,
            ease: 'power3.out',
            scrollTrigger: {{
                trigger: card,
                start: 'top 88%',
                once: true
            }},
            delay: (i % 2) * 0.15
        }});
    }});

    // ── CTA box ─────────────────────────────────────────────────────────
    gsap.from('.cta-box', {{
        opacity: 0, y: 40, duration: 1, ease: 'power3.out',
        scrollTrigger: {{ trigger: '.cta-box', start: 'top 82%', once: true }}
    }});
}})();
</script>
"""
    return html


def save_updated_approved(data: list[dict]) -> None:
    """Save the updated approved wins list back to disk."""
    with open(APPROVED_WINS_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"[OK]   Saved updated {APPROVED_WINS_FILE}")


def upload_to_wordpress(test_mode: bool = False, dry_run: bool = False) -> None:
    """Main upload orchestrator."""
    wins = load_approved_wins()
    if not wins:
        print("[INFO] No approved wins to upload.")
        return

    wins_with_images: list[dict] = []

    for win in wins:
        # Skip if already uploaded
        if win.get("wp_uploaded"):
            print(f"[SKIP] {win.get('company_name', '?')} already uploaded.")
            if win.get("image_url"):
                wins_with_images.append(win)
            continue

        screenshot = win.get("screenshot_path", "")
        if not screenshot:
            channel = win.get("channel", "unknown")
            screenshot = str(SCREENSHOTS_DIR / f"{channel}.png")

        filepath = Path(screenshot)
        if not filepath.exists():
            print(f"[WARN] Screenshot not found: {filepath}")
            continue

        company_name = win.get("company_name") or clean_company_name(win.get("channel", "unknown"))
        win["company_name"] = company_name

        if dry_run:
            print(f"[DRY]  Would upload: {filepath}  →  {company_name}")
            win["image_url"] = "https://example.com/placeholder.png"
            wins_with_images.append(win)
            continue

        if test_mode:
            print(f"[TEST] Simulating upload for {company_name}")
            win["image_url"] = "https://example.com/placeholder.png"
            win["wp_uploaded"] = True
            wins_with_images.append(win)
            continue

        image_url = wp_upload_image(filepath, title=company_name)
        if image_url:
            win["image_url"] = image_url
            win["wp_uploaded"] = True
            wins_with_images.append(win)

    if not wins_with_images:
        print("[INFO] No images to include in the page.")
        return

    page_html = build_page_html(wins_with_images)

    if dry_run:
        print("[DRY]  Would build page HTML and publish to WordPress.")
        print(f"[DRY]  {len(wins_with_images)} win(s) would be included.")
        return

    page_id = wp_find_page(WP_PAGE_SLUG)
    result_id = wp_create_or_update_page(
        page_id=page_id,
        title=WP_PAGE_TITLE,
        content=page_html,
        slug=WP_PAGE_SLUG,
    )
    if result_id:
        print(f"[OK]   WordPress page live: {WP_URL}/{WP_PAGE_SLUG}/")
        save_updated_approved(wins)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="GNO CloudBot — Upload wins to WordPress")
    parser.add_argument("--test", action="store_true", help="Run in test mode (skip real uploads)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, do nothing")
    args = parser.parse_args()

    if not WP_USERNAME or not WP_APP_PASSWORD:
        if not (args.test or args.dry_run):
            print("[ERR]  WP_USERNAME and WP_APP_PASSWORD must be set.")
            sys.exit(1)

    upload_to_wordpress(test_mode=args.test, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
