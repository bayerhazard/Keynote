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

        prompt = f"""Du bist ein professioneller Content-Creator für HTML-Präsentationen mit Reveal.js.

## Briefing:
**THEMA:** {briefing["title"]}

**Kontext:**
{chr(10).join(f"- {kp}" for kp in briefing["key_points"]) if briefing["key_points"] else "- Allgemeine Informationen zum Thema"}

{image_section}

## Anforderungen:
1. DUNKLER HINTERGRUND: `#0A0A0A` oder `#111111` für alle Sections
2. KEINE weißen/hellen Hintergründe
3. Erstelle 5-8 professionelle Folien: Startfolie, 3-5 Inhaltsfolien, Endfolie
4. Verwende ansprechende Layouts: Texte, Bilder, Zitate, Bullet Points
5. Schriftgrößen sollen GUT LESBAR sein (h1: 3-4em, h2: 2-2.5em, body: 1.2-1.5em)
6. Bilder: `object-fit: cover` oder `contain` verwenden, NICHT stretchen

## Technisch:
- Reveal.js 5.x von CDN: https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/
- GSAP von CDN: https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js
- Google Fonts: Inter
- `Reveal.initialize()` am Ende des Body
- Slide-Counter mit Klasse `.slide-counter`
- `Reveal.getTotalSlides()` für Gesamtanzahl

## Erlaubte Farben:
- Gold-Akzent: `#C9A45C`
- Dunkel-Gold: `#B8935F`
- Text: `#FFFFFF`, `#D4D4D4`, `#B0B0B0`
- Cards: `#1A1A1A`

Erstelle jetzt die HTML-Präsentation. Verwende reines HTML ohne Markdown-Wrapper!"""

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

        if "Reveal.initialize" not in html_output:
            html_output = html_output.replace(
                "</body>",
                """<script>
        Reveal.initialize({
            hash: true,
            slideNumber: false,
            controls: true,
            progress: false,
            center: false,
            transition: 'fade',
            width: 1920,
            height: 1080,
        });
        document.querySelectorAll('section').forEach(function(s) {
            s.style.background = '#0A0A0A';
        });
        document.body.style.background = '#0A0A0A';
        </script></body>""",
            )

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
            var counters = document.querySelectorAll('.slide-counter');
            var current = Reveal.getIndices().current + 1;
            counters.forEach(function(c) {{
                if(c) c.textContent = 'Folie ' + current + ' von {{total_slides}}';
            }});
        }}
        Reveal.on('ready', updateSlideCounter);
        Reveal.on('slidechanged', updateSlideCounter);
        
        // Fallback: Alle Sections dunkel setzen falls LLM das vergessen hat
        document.querySelectorAll('section').forEach(function(s) {{
            s.style.background = '#0A0A0A';
        }});
        document.body.style.background = '#0A0A0A';
        document.querySelector('.reveal').style.background = '#0A0A0A';
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
