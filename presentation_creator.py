import json
import re
import httpx
import asyncio
from typing import List, Dict, Any, Optional, Union, Generator, Iterator
from pydantic import BaseModel, Field
from fastapi import Request


class Pipe:
    class Valves(BaseModel):
        PEXELS_API_KEY: str = Field(
            default="", description="Pexels API Key (https://www.pexels.com/api/)."
        )
        LLM_MODEL: str = Field(
            default="aimighty",
            description="Open WebUI LLM model name for HTML generation.",
        )
        OPENAI_BASE_URL: str = Field(
            default="http://localhost:8080/api",
            description="Open WebUI API Base URL (OpenAI-kompatibel). "
            "Bei Docker meist 'http://host.docker.internal:8080/api' "
            "oder 'http://open-webui:8080/api'.",
        )
        OPENAI_API_KEY: str = Field(
            default="",
            description="API Key / JWT für die Open WebUI API "
            "(Settings → Account → API Keys).",
        )

    def __init__(self):
        self.type = "pipe"
        self.id = "presentation_creator"
        self.name = "Professional Presentation Creator"
        self.valves = self.Valves()

    async def on_startup(self):
        pass

    async def on_shutdown(self):
        pass

    async def fetch_pexels_images(
        self, client: httpx.AsyncClient, queries: List[str], main_topic: str = ""
    ) -> Dict[str, str]:
        if not self.valves.PEXELS_API_KEY:
            print("Pexels: No API key configured")
            return {}

        image_map = {}
        headers = {"Authorization": self.valves.PEXELS_API_KEY}

        all_queries = []

        if main_topic:
            all_queries.append(main_topic)
            for q in queries:
                if q.lower() != main_topic.lower():
                    combined = f"{main_topic} {q}"
                    all_queries.append(combined)

        all_queries.extend(queries)
        all_queries = list(dict.fromkeys(all_queries))[:20]

        tasks = []
        for query in all_queries:
            clean_query = query.strip().replace(" ", "+")
            url = f"https://api.pexels.com/v1/search?query={clean_query}&per_page=3"
            tasks.append(self._fetch_single_image(client, url, headers, query))

        results = await asyncio.gather(*tasks)
        for query, img_url in results:
            if img_url:
                image_map[query] = img_url

        print(f"Pexels: Found {len(image_map)} images for main topic '{main_topic}'")
        return image_map

    async def _fetch_single_image(
        self, client: httpx.AsyncClient, url: str, headers: dict, query: str
    ) -> tuple:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            print(f"Pexels request for '{query}': {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                if data.get("photos") and len(data["photos"]) > 0:
                    img_url = (
                        data["photos"][0]["src"]["large2x"]
                        or data["photos"][0]["src"]["large"]
                    )
                    print(f"Pexels: Found image for '{query}'")
                    return (query, img_url)
                else:
                    print(f"Pexels: No photos found for '{query}'")
            elif response.status_code == 401:
                print(f"Pexels: Unauthorized - Invalid API key")
            elif response.status_code == 429:
                print(f"Pexels: Rate limited")
            else:
                print(f"Pexels: Error {response.status_code} - {response.text[:200]}")
        except httpx.TimeoutException:
            print(f"Pexels: Timeout for '{query}'")
        except Exception as e:
            print(f"Pexels error for '{query}': {e}")
        return (query, None)

    def create_briefing(self, messages: List[Dict]) -> Dict[str, Any]:
        conversation_parts = []
        for msg in messages:
            content = msg.get("content", "")
            if content:
                conversation_parts.append(content)

        conversation = " ".join(conversation_parts)
        conversation_lower = conversation.lower()

        skip_topics = {
            "präsentation",
            "presentation",
            "praesentation",
            "präsentations",
            "folien",
            "folie",
            "slides",
            "slide",
            "powerpoint",
            "keynote",
        }

        title = "Unbekanntes Thema"
        title_patterns = [
            r'(?:erstelle|mach|erklär|zeig|will|brauche|benötige)[:\s]+(?:(?:mir\s+)?(?:eine?\s+)?(?:pr[äa]sentation|pr[äa]sent)[^\s]*\s*(?:über|übern|von|zu)?\s*)([^"\n]{3,80})',
            r'pr[äa]sentation[:\s]+(?:über|übern|von|zu)?\s*["\']?([^"\n]{3,80})',
            r'(?:über|übern|von|zu)[:\s]+["\']?([^"\n]{3,80})["\']?(?:\s|,|$)',
            r'thema[:\s]+["\']?([^"\n]{3,80})["\']?',
            r"(?:dog|hund|katze|cat|hundetraining|hunde)[:\s]+",
        ]
        for pattern in title_patterns:
            match = re.search(pattern, conversation, re.IGNORECASE | re.MULTILINE)
            if match:
                potential_title = match.group(1).strip()
                words = potential_title.lower().split()
                if (
                    not any(skip in words for skip in skip_topics)
                    and len(potential_title) > 2
                ):
                    title = potential_title
                    if len(title) > 5:
                        break

        words = re.findall(r"\b[A-Z][a-zäöüß]+\b|\b[a-zäöüß]{4,}\b", conversation)
        word_freq = {}
        for word in words:
            w_lower = word.lower()
            if w_lower not in skip_topics and len(w_lower) > 3:
                word_freq[w_lower] = word_freq.get(w_lower, 0) + 1

        common_topic_map = {
            "marketing": "marketing business",
            "verkauf": "sales business",
            "produkt": "product",
            "software": "software technology",
            "künstliche intelligenz": "artificial intelligence technology",
            "ki": "ai technology",
            "daten": "data analytics",
            "team": "team collaboration",
            "unternehmen": "business company",
            "strategie": "strategy business",
            "wachstum": "growth business",
            "projekt": "project management",
            "technologie": "technology innovation",
            "innovation": "innovation technology",
            "finance": "finance business",
            "finanzen": "finance business",
            "personal": "human resources team",
            "kunde": "customer business",
            "hund": "dog pet",
            "hunde": "dog pet",
            "katze": "cat pet",
            "gesundheit": "health wellness",
            "ernährung": "nutrition food",
            "bildung": "education learning",
            "reisen": "travel vacation",
            "finanzen": "finance money",
            "immobilien": "real estate property",
            "auto": "car automobile",
        }

        keywords = []
        conv_lower = conversation.lower()
        for topic, search_term in common_topic_map.items():
            if topic in conv_lower:
                keywords.append(search_term)

        for word, count in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]:
            if count >= 2 and len(word) > 4:
                keywords.append(word)

        unique_keywords = list(dict.fromkeys(keywords))[:10]

        key_points = []
        bullet_matches = re.findall(
            r"[-*•]\s*(.{15,200}?)(?=\n[-*•]|\n\n|$)", conversation
        )
        if bullet_matches:
            key_points = [m.strip() for m in bullet_matches if len(m.strip()) > 15][:6]
        else:
            sentences = re.split(r"[.!?]\s+", conversation)
            for sent in sentences:
                if 30 < len(sent) < 180 and not any(
                    w in sent.lower()
                    for w in ["präsentation", "presentation", "folie", "slide"]
                ):
                    key_points.append(sent.strip())
            key_points = key_points[:6]

        return {
            "title": title,
            "conversation": conversation[:3000],
            "keywords": unique_keywords if unique_keywords else [title],
            "key_points": key_points,
            "total_messages": len(messages),
        }

    def build_html_prompt(self, briefing: Dict, images: Dict[str, str]) -> str:
        image_section = ""
        if images:
            image_section = "\n\n## Verfügbare Bilder (von Pexels):\n"
            image_section += "WICHTIG: Alle Bilder MÜSSEN das HAUPTTHEMA zeigen. Bei Thema 'Hunde' und Folie 'Pflege' → Bild: 'Hunde Pflege'\n\n"
            for keyword, url in images.items():
                image_section += f"- {keyword}: {url}\n"

        prompt = f"""Du bist ein professioneller Content-Creator. Der User möchte eine HTML-Präsentation über ein bestimmtes Thema erstellen.

## Deine Aufgabe:
1. Extrahiere das EIGENTLICHE THEM A aus der Anfrage (NICHT "Präsentation" - das ist nur das Format!)
2. Analysiere den Kontext für HINTERGRUND-INFORMATIONEN zum Thema
3. Erstelle eine INHALTLICHE Präsentation über das Thema selbst, nicht über "wie man Präsentationen erstellt"

## Briefing (extrahiert aus der Anfrage):
**THEMA:** {briefing["title"]}

**Kontext/Informationen zum Thema:**
{chr(10).join(f"- {kp}" for kp in briefing["key_points"]) if briefing["key_points"] else "- Allgemeine Informationen zum Thema"}

## WICHTIG - HINTERGRUNDGESTALTUNG:
- HINTERGRUND MUSS IMMER DUNKEL SEIN: background: #0A0A0A oder #111111
- KEINE weißen oder hellen Hintergründe verwenden!
- Alles muss dunkel und elegant aussehen
- Sections: background: #0A0A0A oder Verläufe von #0A0A0A nach #1A1A1A

{image_section}

## Style Guide - DUNKLES DESIGN (VOLLSTÄNDIG):
```css
:root {{
    --bg-main: #0A0A0A;
    --bg-dark: #111111;
    --accent-gold: #C9A45C;
    --dark-gold: #B8935F;
    --gold-glow: rgba(201, 164, 92, 0.3);
    --text-primary: #FFFFFF;
    --text-secondary: #D4D4D4;
    --text-body: #B0B0B0;
    --bg-card: #1A1A1A;
}}

/* WICHTIG: ALLES MUSS DUNKEL SEIN - ERZWINING! */
body, html {{ 
    background: #0A0A0A !important; 
    margin: 0;
    padding: 0;
}}
.reveal {{ background: #0A0A0A !important; }}
.reveal .slides {{ background: #0A0A0A !important; }}
.reveal .slides section, 
.reveal-viewport section {{ 
    background: #0A0A0A !important; 
}}
section.slide-content {{ background: #0A0A0A !important; }}

/* Typography */
.reveal {{ font-family: 'Inter', sans-serif; }}
.reveal h1 {{ font-size: 3.5em; font-weight: 700; background: linear-gradient(135deg, #C9A45C, #B8935F); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.reveal h2 {{ font-size: 2.2em; font-weight: 400; color: #D4D4D4; }}
.reveal p, .reveal li {{ font-size: 1em; color: #B0B0B0; }}

/* Layouts */
.split-layout {{ display: flex; align-items: center; gap: 40px; }}
.split-layout > div {{ flex: 1; }}
.split-layout img {{ width: 100%; border-radius: 20px; }}
.grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }}

/* Card - DUNKEL */
.card {{
    background: #1A1A1A;
    border-radius: 20px;
    border: 1px solid rgba(201, 164, 92, 0.15);
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    padding: 30px;
    height: 100%;
}}
.card h3 {{ color: #C9A45C; font-size: 1.4em; margin-bottom: 15px; }}

/* Button */
.btn-pill {{
    background: linear-gradient(135deg, #C9A45C, #B8935F);
    color: #050505;
    border-radius: 50px;
    padding: 15px 40px;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
    border: none;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
}}

/* Quote */
.quote-box {{
    border-left: 4px solid #C9A45C;
    padding-left: 40px;
    font-style: italic;
    font-size: 1.5em;
    color: #D4D4D4;
}}

/* FUSSZEILE - Glassmorphism (auf INHALTSFOLIEN) */
.footer-container {{
    position: absolute;
    bottom: 15px;
    left: 20px;
    right: 20px;
    height: 36px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    backdrop-filter: blur(10px);
    background: rgba(255,255,255,0.05);
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.1);
    padding: 0 15px;
    box-sizing: border-box;
    pointer-events: none;
}}
.footer-text {{
    font-size: 0.6em;
    color: #D4D4D4;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin: 0;
}}
```

## Folien-Struktur - JEDE SECTION MUSS EXPLIZIT DUNKLEN HINTERGRUND HABEN:

### 1. STARTFOLIE - KEIN FOOTER:
```html
<section style="background: #0A0A0A !important; text-align: center;">
    <div style="padding-top: 100px;">
        <h1>"{briefing["title"]}"</h1>
        <p style="color: #D4D4D4; font-size: 1.2em;">AImighty</p>
        <button class="btn-pill" onclick="startPresentation()">Präsentation starten</button>
    </div>
</section>
```

### 2. INHALTSFOLIEN (min. 4-6) - MUSS FOOTER HABEN:
```html
<section style="background: #0A0A0A !important;">
    <div style="padding: 40px;">
        <!-- CONTENT HIER -->
    </div>
    <footer class="footer-container">
        <span class="footer-text">{briefing["title"]}</span>
        <span class="footer-text">AImighty</span>
        <span class="footer-text slide-counter">Folie 2 von 6</span>
    </footer>
</section>
```

### 3. ABSCHLUSSFOLIE - KEIN FOOTER:
```html
<section style="background: #0A0A0A !important; text-align: center;">
    <h1>Vielen Dank!</h1>
    <p>AImighty</p>
</section>
```

## JavaScript - PFlicht:
```javascript
// WICHTIG: Alle sections bekommen explizit dunklen Hintergrund
document.querySelectorAll('section').forEach(s => {{
    s.style.background = '#0A0A0A';
}});

// Slide Counter aktualisieren
function updateSlideCounter() {{
    const counters = document.querySelectorAll('.slide-counter');
    const current = Reveal.getIndices().current + 1;
    const total = Reveal.getTotalSlides();
    counters.forEach(el => {{
        if(el) el.textContent = 'Folie ' + current + ' von ' + total;
    }});
}}

// GSAP Animationen
Reveal.on('ready', () => {{ updateSlideCounter(); }});
Reveal.on('slidechanged', event => {{
    updateSlideCounter();
    gsap.fromTo('.anim-h2', {{y: 30, opacity: 0}}, {{y: 0, opacity: 1, duration: 1.2, ease: 'power4.out'}});
    gsap.fromTo('.anim-p', {{y: 20, opacity: 0}}, {{y: 0, opacity: 1, duration: 1, stagger: 0.2, ease: 'power2.out'}});
    gsap.fromTo('.anim-item', {{y: 30, opacity: 0}}, {{y: 0, opacity: 1, duration: 1, stagger: 0.2, ease: 'power3.out'}});
}});
```

## Technische Anforderungen:
1. Reveal.js 5.x von CDN
2. GSAP von CDN
3. Google Fonts: Inter
4. JEDE section MUSS `style="background: #0A0A0A !important;"` haben!
5. Slide-Counter verwendet die KLASSE `.slide-counter` (NICHT ID!)
6. KEINE separaten Script-Blöcke für Counter - alles in EINEM Script

Erstelle jetzt die komplette HTML-Präsentation. Verwende reines HTML ohne Markdown-Wrapper!"""

        return prompt

    async def call_llm(self, prompt: str) -> str:
        if not self.valves.OPENAI_BASE_URL or not self.valves.OPENAI_API_KEY:
            return f"FEHLER: OPENAI_BASE_URL oder OPENAI_API_KEY nicht konfiguriert."

        headers = {
            "Authorization": f"Bearer {self.valves.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.valves.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.valves.OPENAI_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    return (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                else:
                    return f"API Error: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error calling LLM: {str(e)}"

    async def pipe(
        self, body: Dict[str, Any], __request__: Request = None, __user__: dict = None
    ) -> Union[str, List[str]]:
        messages = body.get("messages", [])
        if not messages:
            return "Keine Nachrichten gefunden. Bitte starten Sie einen Chat, um eine Präsentation zu erstellen."

        briefing = self.create_briefing(messages)

        main_topic = briefing["title"]
        main_topic_clean = re.sub(r"[^\w\s]", " ", main_topic).strip()
        main_topic_clean = re.sub(r"\s+", " ", main_topic_clean)

        pexels_queries = []

        if briefing["keywords"] and len(briefing["keywords"]) > 0:
            pexels_queries.extend(briefing["keywords"])

        if briefing["key_points"]:
            for kp in briefing["key_points"][:8]:
                words = kp.split()[:4]
                if words:
                    query = " ".join(words)
                    if len(query) > 3:
                        pexels_queries.append(query)

        if not pexels_queries or main_topic.lower() in ["präsentation", "presentation"]:
            pexels_queries = [
                "business meeting",
                "professional presentation",
                "office team",
                "corporate success",
            ]

        pexels_queries = [q.strip() for q in pexels_queries if q and len(q.strip()) > 3]
        pexels_queries = list(dict.fromkeys(pexels_queries))[:12]

        images = {}
        pexels_debug = ""

        if self.valves.PEXELS_API_KEY:
            if not pexels_queries:
                pexels_debug = "\n⚠️ Keine Suchbegriffe für Pexels gefunden."
            else:
                async with httpx.AsyncClient() as client:
                    images = await self.fetch_pexels_images(
                        client, pexels_queries, main_topic=main_topic_clean
                    )
                if not images:
                    pexels_debug = f"\n⚠️ Pexels: Keine Bilder gefunden"
                else:
                    pexels_debug = f"\n✓ {len(images)} Bilder zum Thema '{main_topic_clean}' geladen"
                    sample_imgs = list(images.keys())[:3]
                    pexels_debug += f" (z.B. {', '.join(sample_imgs)})"
        else:
            pexels_debug = "\n⚠️ Pexels: Kein API Key konfiguriert."

        html_prompt = self.build_html_prompt(briefing, images)

        html_output = await self.call_llm(html_prompt)

        html_output = re.sub(r"^```html\s*", "", html_output)
        html_output = re.sub(r"```$", "", html_output)
        html_output = re.sub(r"^```\s*", "", html_output)

        if (
            not html_output.strip().startswith("<!DOCTYPE")
            and "<html" not in html_output[:100]
        ):
            return f"""# Präsentation kann nicht generiert werden

Es gab ein Problem bei der HTML-Generierung.

**Fehlerdetails:**
{html_output[:500] if len(html_output) > 500 else html_output}

Bitte versuchen Sie es erneut oder prüfen Sie:
1. Ist OPENAI_BASE_URL und OPENAI_API_KEY in den Valves konfiguriert?
2. Funktioniert die Verbindung zum LLM?
3. Ist der Prompt klar genug für die Präsentation?
"""

        total_slides = html_output.count("<section")

        slide_counter_js = f"""
        <script>
        function updateSlideCounter() {{
            var counters = document.querySelectorAll('#slide-counter');
            var current = Reveal.getIndices().current + 1;
            counters.forEach(function(c) {{
                if(c && c.id === 'slide-counter') c.textContent = 'Folie ' + current + ' von {total_slides}';
            }});
        }}
        Reveal.on('ready', updateSlideCounter);
        Reveal.on('slidechanged', updateSlideCounter);
        </script>
        """
        html_output = html_output.replace("</body>", slide_counter_js + "</body>")

        return f"""# ✨ Präsentation erstellt!

**Titel:** {briefing["title"]}

Die HTML-Präsentation wurde erfolgreich generiert mit:
- {len(images)} Bilder von Pexels{pexels_debug}
- {total_slides} Folien
- Reveal.js + GSAP Animationen

---

```html
{html_output}
```

---

Öffne die HTML-Datei in einem Browser, um die Präsentation anzusehen."""


if __name__ == "__main__":
    print("Professional Presentation Creator Pipe Ready.")
