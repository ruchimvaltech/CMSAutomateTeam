import os
from dotenv import load_dotenv
import json
import re

load_dotenv()  # loads .env into environment variables
from openai import OpenAI

# Azure OpenAI Configuration
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

if not AZURE_OPENAI_KEY or not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_DEPLOYMENT_NAME:
    raise ValueError("Azure OpenAI credentials not found in .env. Required: AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT_NAME")

client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY
)


def _strip_code_fences(s: str) -> str:
    # Remove Markdown code fences like ```json ... ```
    s = re.sub(r"^\s*```(?:json)?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"```\s*$", "", s)
    return s.strip()


def _remove_trailing_commas(s: str) -> str:
    # Remove trailing commas before closing braces/brackets
    return re.sub(r",\s*([}\]])", r"\1", s)


def _extract_balanced_json(s: str) -> str | None:
    # Extract the first balanced JSON object {...}
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return s[start:i+1]
    return None


def _escape_newlines_in_strings(s: str) -> str:
    # Replace raw CR/LF within JSON strings with \n to preserve validity
    out = []
    in_str = False
    escape = False
    for ch in s:
        if in_str:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                out.append(ch)
                in_str = False
                continue
            if ch == "\n" or ch == "\r":
                out.append("\\n")
            else:
                out.append(ch)
        else:
            if ch == '"':
                out.append(ch)
                in_str = True
            else:
                out.append(ch)
    return "".join(out)


def _safe_json_loads(s: str) -> dict:
    # Attempt direct parse
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Sanitize common issues then parse
    s2 = _strip_code_fences(s)
    s2 = _escape_newlines_in_strings(s2)
    s2 = _remove_trailing_commas(s2)
    try:
        return json.loads(s2)
    except json.JSONDecodeError:
        pass

    # Extract balanced object if extra text surrounds JSON
    block = _extract_balanced_json(s2)
    if block:
        block = _escape_newlines_in_strings(block)
        block = _remove_trailing_commas(block)
        return json.loads(block)

    # Last attempt: regex-based greedy object
    match = re.search(r"\{[\s\S]*\}", s2)
    if match:
        block = _escape_newlines_in_strings(match.group())
        block = _remove_trailing_commas(block)
        return json.loads(block)

    raise json.JSONDecodeError("Unable to parse JSON", s, 0)


def ask_ai(user_question, website_context):
    system_prompt = """
You are an expert UI/UX analyst and CMS architect.

You have been given structured content extracted from a website.
This content represents the COMPLETE and TRUSTED source of truth.

Your job:
- Analyze the website structure
- Identify page types, components, layouts, and patterns
- Infer reasonable conclusions even if labels are not explicit

IMPORTANT RULES:
- NEVER say "I don't know" if the information can be inferred
- If something is not explicitly stated, say "Based on the structure, it appears that..."
- Answer ONLY using the provided website context
- Be concise, structured, and confident
"""

    user_prompt = f"""
WEBSITE CONTENT:
----------------
{website_context}
----------------

USER QUESTION:
{user_question}

INSTRUCTIONS:
- Answer specifically about this website
- List components or page types when applicable
- Use bullet points if helpful
- Do not repeat the question
"""

    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    return response.choices[0].message.content

# ---------------- RFP MODE  ----------------

def _merge_rfp_batches(batches: list[dict]) -> dict:
    """
    Merges multiple RFP analysis batches into a single comprehensive result.
    Handles deduplication and aggregation of page_types, components, integrations.
    """
    if not batches:
        return {}
    
    if len(batches) == 1:
        return batches[0]
    
    merged = {
        "overview": batches[0]["overview"].copy(),
        "page_types": [],
        "components": [],
        "pages": [],
        "third_party_integrations": [],
        "recommendations": []
    }
    
    # Merge pages (direct concatenation, preserving order)
    for batch in batches:
        merged["pages"].extend(batch.get("pages", []))
    
    # Update total count
    merged["overview"]["total_pages_analyzed"] = len(merged["pages"])
    
    # Merge page_types (aggregate counts by name)
    pt_map = {}
    for batch in batches:
        for pt in batch.get("page_types", []):
            name = pt["name"]
            if name not in pt_map:
                pt_map[name] = pt.copy()
            else:
                # Aggregate count
                pt_map[name]["count"] = pt_map[name].get("count", 0) + pt.get("count", 0)
                # Extend example URLs (deduplicate)
                existing_urls = set(pt_map[name].get("example_urls", []))
                new_urls = [u for u in pt.get("example_urls", []) if u not in existing_urls]
                pt_map[name]["example_urls"].extend(new_urls[:3])  # Keep max 3 examples
    
    merged["page_types"] = list(pt_map.values())
    
    # Merge components (deduplicate by name, merge found_on_urls)
    comp_map = {}
    for batch in batches:
        for comp in batch.get("components", []):
            name = comp["name"]
            if name not in comp_map:
                comp_map[name] = comp.copy()
            else:
                # Merge found_on_urls (deduplicate)
                existing = set(comp_map[name].get("found_on_urls", []))
                new_urls = [u for u in comp.get("found_on_urls", []) if u not in existing]
                comp_map[name]["found_on_urls"].extend(new_urls)
    
    merged["components"] = list(comp_map.values())
    
    # Merge third_party_integrations (deduplicate by name, merge detected_on_urls)
    int_map = {}
    for batch in batches:
        for integ in batch.get("third_party_integrations", []):
            name = integ["name"]
            if name not in int_map:
                int_map[name] = integ.copy()
            else:
                existing = set(int_map[name].get("detected_on_urls", []))
                new_urls = [u for u in integ.get("detected_on_urls", []) if u not in existing]
                int_map[name]["detected_on_urls"].extend(new_urls)
    
    merged["third_party_integrations"] = list(int_map.values())
    
    # Merge recommendations (deduplicate)
    rec_set = set()
    for batch in batches:
        for rec in batch.get("recommendations", []):
            rec_set.add(rec)
    merged["recommendations"] = list(rec_set)
    
    return merged


def _filter_context_by_urls(context: str, urls: list[str]) -> str:
    """
    Filters website context to include only sections related to the given URLs.
    """
    lines = context.split("\n")
    filtered = []
    include = False
    
    for line in lines:
        if line.startswith("[URL]"):
            # Check if this URL is in our batch
            include = any(url in line for url in urls)
        
        if include:
            filtered.append(line)
    
    return "\n".join(filtered)


def generate_rfp_analysis(website_context: str, crawled_urls: list[str], batch_size: int = None) -> dict:
    """
    Generates structured RFP-ready website analysis.
    Automatically splits large crawls into batches to avoid token limits.
    Output is STRICT JSON to support Excel export.
    """

    # Build authoritative URL index
    urls = sorted(set(crawled_urls or re.findall(r'https?://[^\s)"\']+', website_context)))
    url_count = len(urls)
    
    if url_count == 0:
        raise ValueError("No URLs available. Provide crawled_urls or ensure context contains URLs.")
    
    # Dynamic batch sizing based on total URL count
    if batch_size is None:
        if url_count <= 100:
            batch_size = url_count  # Single batch
        elif url_count <= 500:
            batch_size = 100  # Standard batch size
        elif url_count <= 1000:
            batch_size = 80   # Smaller batches for better reliability
        else:
            batch_size = 50   # Very small batches for extremely large sites
    
    print(f"INFO: Total URLs to analyze: {url_count}, Batch size: {batch_size}")
    
    # Determine if batching is needed
    if url_count <= batch_size:
        print(f"INFO: Analyzing {url_count} URLs in a single batch")
        return _generate_rfp_batch(website_context, urls, url_count, 1, 1)
    
    # Split into batches
    num_batches = (url_count + batch_size - 1) // batch_size
    print(f"INFO: Splitting {url_count} URLs into {num_batches} batches of ~{batch_size}")
    print(f"INFO: Estimated processing time: {num_batches * 15}-{num_batches * 30} seconds")
    
    batches = []
    for i in range(num_batches):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, url_count)
        batch_urls = urls[start_idx:end_idx]
        
        print(f"INFO: Processing batch {i+1}/{num_batches} ({len(batch_urls)} URLs) - Progress: {int((i/num_batches)*100)}%")
        
        # Extract context for this batch (filter by URLs)
        batch_context = _filter_context_by_urls(website_context, batch_urls)
        
        try:
            batch_result = _generate_rfp_batch(batch_context, batch_urls, len(batch_urls), i+1, num_batches)
            batches.append(batch_result)
            print(f"SUCCESS: Batch {i+1}/{num_batches} completed with {len(batch_result.get('pages', []))} pages")
        except Exception as e:
            print(f"WARNING: Batch {i+1}/{num_batches} failed: {e}. Continuing with partial results...")
            continue
    
    if not batches:
        raise ValueError("All batches failed. Try reducing max_pages or batch_size.")
    
    print(f"INFO: Merging {len(batches)} successful batches...")
    merged = _merge_rfp_batches(batches)
    
    print(f"SUCCESS: Final analysis covers {len(merged.get('pages', []))} pages")
    # Post-process to annotate reusable components and map components to page types
    return _annotate_components_and_page_types(merged)


def _generate_rfp_batch(website_context: str, urls: list[str], url_count: int, batch_num: int = 1, total_batches: int = 1) -> dict:
    """
    Generates RFP analysis for a single batch of URLs.
    """
    if total_batches > 1:
        print(f"DEBUG: Batch {batch_num}/{total_batches} - Analyzing {url_count} URLs")
    
    url_index_text = "\n".join(f"- {u}" for u in urls)

    prompt = f"""
You are acting as a SENIOR CMS SOLUTION ARCHITECT preparing a
DETAILED RFP ANALYSIS DOCUMENT.

CRITICAL: Analyze EVERY SINGLE URL provided below.

------------------------------------------------------------
CRAWLED URL INDEX (AUTHORITATIVE – USE EXACTLY THESE URLs)
------------------------------------------------------------
Total URLs: {url_count}
{url_index_text}

You MUST:
- Create one 'pages' entry for EVERY URL in the index above (no omissions, no merges)
- Set 'total_pages_analyzed' to {url_count}
- Ensure the sum of 'page_types[].count' == {url_count}
- If a page type is unclear, use "Unknown" but still include the page
- Do NOT invent URLs or pages not present in the index
- Use only URLs from the index in 'example_urls' and 'found_on_urls'

------------------------------------------------------------
OUTPUT FORMAT (STRICT – MUST MATCH EXACTLY)
------------------------------------------------------------
{{
  "overview": {{
    "website_purpose": "",
    "industry": "",
    "overall_structure": "",
    "total_pages_analyzed": {url_count}
  }},
  "page_types": [
    {{
      "name": "",
      "description": "",
      "example_urls": [],
      "complexity": "Low | Medium | High",
      "count": 0
    }}
  ],
  "components": [
    {{
      "name": "",
      "description": "",
      "used_on_pages": "",
      "found_on_urls": [],
      "media_type": "None | Image | Video | Gallery | Image+Text | Carousel | Slider",
      "media_count": "",
      "cms_managed": "Yes | No | Partial",
      "third_party_dependency": "",
      "complexity": "Low | Medium | High",
      "effort_estimate_days": ""
    }}
  ],
  "pages": [
    {{
      "url": "",
      "page_type": "",
      "components": [],
      "complexity": "Low | Medium | High",
      "notes": ""
    }}
  ],
  "third_party_integrations": [
    {{
      "name": "",
      "category": "Analytics | Marketing | Media | CDN | Authentication | Payment | Chat | Social | Other",
      "purpose": "",
      "evidence_or_inference": "",
      "detected_on_urls": []
    }}
  ],
  "recommendations": []
}}

------------------------------------------------------------
ANALYSIS INSTRUCTIONS (MANDATORY – READ CAREFULLY)
------------------------------------------------------------

STEP 1: PAGE ENUMERATION
- Iterate through the CRAWLED URL INDEX above
- Produce one 'pages' entry per URL, preserving the exact URL string

STEP 2: PAGE TYPE CLASSIFICATION
- Classify each page into one logical type
- Common types: Homepage/Landing, Product/Service Detail, Category/Listing, Blog/News/Article, About/Team/Company, Contact/Form, FAQ/Support, Legal/Policy, Search Results, User Account/Dashboard, Unknown
- Sum of 'page_types.count' MUST equal {url_count}

STEP 3: COMPONENT IDENTIFICATION (UNBOUNDED, UX-LED)
- Act as a senior UX designer: infer components from visual layout, information architecture, and content structure for EACH page.
- Do NOT limit the component list to predefined categories; name components precisely and contextually (e.g., "Hero with CTA", "Sticky Header", "Mega Menu", "Breadcrumb", "Faceted Filters", "Tag Chips", "Card Grid", "Accordion", "Tabs", "Stepper", "Toast", "Modal", "Carousel", "Video Player", "Download List", "Table", "Data Visualization", "FAQ", "Contact Form", "Newsletter Form", "Map Embed", "Testimonials", "Related Articles", "Author Bio", "Comments", "Pagination", "Infinite Scroll", "Empty State", "Skeleton Loader", "Cookie Banner", "Chat Widget", "Search Bar", "Search Results", "Promo Ribbon", "Language Switcher"). These are examples, not limits.
- Capture both atomic (buttons, badges, chips) and composite (sections, cards, grids) components; include key variants when relevant.
- Derive a comprehensive per-page component list and ensure aggregation is reflected across page types.
- If labels are ambiguous, infer based on layout patterns, headings, repeated structures, and textual cues.

STEP 4: THIRD-PARTY INTEGRATION DETECTION (OPEN-ENDED)
- Act as a website analyst and identify ALL third-party services integrated into the site.
- Do NOT rely on any predefined list. Infer integrations from evidence such as:
  - script/iframe src domains, link/script tags, meta tags, inline snippets
  - form action endpoints, API/base URLs, request hosts referenced in the context
  - embedded widgets/SDKs, OAuth flows, payment buttons, chat launchers, social embeds
  - CDN/storage domains, tracking beacons, tag managers, A/B testing tools
- For each integration, include: name (provider), category (free-form label), purpose, evidence_or_inference, detected_on_urls.

STEP 5: QUALITY & STRICTNESS
- Output ONLY valid JSON
- 'total_pages_analyzed' MUST be {url_count}
- 'pages' array MUST contain exactly {url_count} entries

WEBSITE CONTENT (REFERENCE SOURCE):
{website_context}
"""

    # Define a function tool schema to force JSON output
    rfp_function = {
        "type": "function",
        "function": {
            "name": "submit_rfp",
            "description": "Return the structured RFP analysis as a strict JSON object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "overview": {
                        "type": "object",
                        "properties": {
                            "website_purpose": {"type": "string"},
                            "industry": {"type": "string"},
                            "overall_structure": {"type": "string"},
                            "total_pages_analyzed": {"type": "number"}
                        },
                        "required": ["website_purpose", "industry", "overall_structure", "total_pages_analyzed"]
                    },
                    "page_types": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "example_urls": {"type": "array", "items": {"type": "string"}},
                                "complexity": {"type": "string"},
                                "count": {"type": "number"}
                            },
                            "required": ["name", "description", "example_urls", "complexity", "count"]
                        }
                    },
                    "components": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "used_on_pages": {"type": "string"},
                                "found_on_urls": {"type": "array", "items": {"type": "string"}},
                                "media_type": {"type": "string"},
                                "media_count": {"type": "string"},
                                "cms_managed": {"type": "string"},
                                "third_party_dependency": {"type": "string"},
                                "complexity": {"type": "string"},
                                "effort_estimate_days": {"type": "string"}
                            },
                            "required": [
                                "name","description","used_on_pages","found_on_urls","media_type","media_count","cms_managed","third_party_dependency","complexity","effort_estimate_days"
                            ]
                        }
                    },
                    "pages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string"},
                                "page_type": {"type": "string"},
                                "components": {"type": "array", "items": {"type": "string"}},
                                "complexity": {"type": "string"},
                                "notes": {"type": "string"}
                            },
                            "required": ["url", "page_type", "components", "complexity", "notes"]
                        }
                    },
                    "third_party_integrations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "category": {"type": "string"},
                                "purpose": {"type": "string"},
                                "evidence_or_inference": {"type": "string"},
                                "detected_on_urls": {"type": "array", "items": {"type": "string"}}
                            },
                            "required": ["name", "category", "purpose", "evidence_or_inference", "detected_on_urls"]
                        }
                    },
                    "recommendations": {"type": "array", "items": {"type": "string"}}
                },
                "required": [
                    "overview", "page_types", "components", "pages", "third_party_integrations", "recommendations"
                ]
            }
        }
    }

    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT_NAME,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16000,
        tools=[rfp_function],
        tool_choice={"type": "function", "function": {"name": "submit_rfp"}}
    )

    message = response.choices[0].message
    
    # Prefer tool call JSON if provided
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls and len(tool_calls) > 0:
        args = tool_calls[0].function.arguments
        # Detect truncation
        if not args.rstrip().endswith("}"):
            print(f"WARNING: Tool call arguments appear truncated. Attempting repair...")
            args = args.rstrip().rstrip(",") + "]}}"  
        try:
            data = json.loads(args)
        except json.JSONDecodeError as e:
            print(f"WARNING: Parse failed, attempting sanitization...")
            data = _safe_json_loads(args)
    else:
        raw = message.content.strip() if message.content else ""
        if not raw:
            raise ValueError("Empty AI response")
        data = _safe_json_loads(raw)

    # Ensure required fields exist
    if "page_types" not in data or not data["page_types"]:
        data["page_types"] = [{"name": "Unknown", "description": "Pages analyzed", "example_urls": [], "complexity": "Medium", "count": len(data.get("pages", []))}]
    
    if "components" not in data:
        data["components"] = []
    
    if "third_party_integrations" not in data:
        data["third_party_integrations"] = []
    
    if "recommendations" not in data:
        data["recommendations"] = []

    return data


def _annotate_components_and_page_types(data: dict) -> dict:
    """
    Adds reusable flags to components and maps components to page types.
    - A component is marked reusable if it appears in more than one page type.
    - Each page type gains summary fields: components_all, components_reusable, component_count.
    """
    pages = data.get("pages", []) or []
    components = data.get("components", []) or []
    page_types = data.get("page_types", []) or []

    # Build usage maps
    comp_to_page_types: dict[str, set] = {}
    pt_to_components: dict[str, set] = {}

    # Map URL to page type for fallback enrichment
    url_to_pt: dict[str, str] = {}
    for p in pages:
        pt = (p.get("page_type") or "Unknown").strip() or "Unknown"
        comps = p.get("components", []) or []
        if pt not in pt_to_components:
            pt_to_components[pt] = set()
        for c in comps:
            if not isinstance(c, str):
                continue
            cname = c.strip()
            if not cname:
                continue
            pt_to_components[pt].add(cname)
            comp_to_page_types.setdefault(cname, set()).add(pt)
        url = p.get("url")
        if isinstance(url, str) and url:
            url_to_pt[url] = pt

    # Mark reusable on components list
    for comp in components:
        name = (comp.get("name") or "").strip()
        pts = comp_to_page_types.get(name, set())
        comp["reusable"] = "Yes" if len(pts) > 1 else "No"

    # Inject component mapping summaries into page_types entries
    # Create index for quick lookup
    name_to_pt_obj = { (pt.get("name") or "Unknown"): pt for pt in page_types }
    for pt_name, comp_set in pt_to_components.items():
        pt_obj = name_to_pt_obj.get(pt_name)
        if not pt_obj:
            # If AI didn't emit this page type, create a minimal entry
            pt_obj = {"name": pt_name, "description": "", "example_urls": [], "complexity": "", "count": 0}
            page_types.append(pt_obj)
            name_to_pt_obj[pt_name] = pt_obj
        comp_list = sorted(comp_set)
        reusable_list = [c for c in comp_list if len(comp_to_page_types.get(c, set())) > 1]
        pt_obj["components_all"] = ", ".join(comp_list)
        pt_obj["components_reusable"] = ", ".join(sorted(reusable_list))
        pt_obj["component_count"] = len(comp_list)

    # Fallback enrichment: use components[].found_on_urls to add components to page types
    for comp in components:
        cname = (comp.get("name") or "").strip()
        urls = comp.get("found_on_urls", []) or []
        for u in urls:
            pt = url_to_pt.get(u)
            if not pt:
                continue
            pt_to_components.setdefault(pt, set()).add(cname)
            comp_to_page_types.setdefault(cname, set()).add(pt)

    # Recompute page type summaries after enrichment
    for pt_name, comp_set in pt_to_components.items():
        pt_obj = name_to_pt_obj.get(pt_name)
        if not pt_obj:
            pt_obj = {"name": pt_name, "description": "", "example_urls": [], "complexity": "", "count": 0}
            page_types.append(pt_obj)
            name_to_pt_obj[pt_name] = pt_obj
        comp_list = sorted(comp_set)
        reusable_list = [c for c in comp_list if len(comp_to_page_types.get(c, set())) > 1]
        pt_obj["components_all"] = ", ".join(comp_list)
        pt_obj["components_reusable"] = ", ".join(sorted(reusable_list))
        pt_obj["component_count"] = len(comp_list)

    # Ensure structures are set back
    data["components"] = components
    data["page_types"] = page_types
    return data


# ---------------- suggested questions ----------------

import re


def generate_suggested_questions(website_context: str) -> list[str]:
    """
    Generates smart, context-aware suggested questions for the chatbot UI.
    Always returns a safe list.
    """

    prompt = f"""
You are an expert CMS analyst.

Based on the website content below, generate 6 to 8
useful, practical questions a user might ask to understand:
- Page types
- Components
- Media usage
- Third-party integrations
- Complexity or effort

Rules:
- Questions must be specific to this website
- Questions must be short and clear
- Do NOT number them
- Return ONLY a JSON array of strings (no explanation text)

WEBSITE CONTENT:
{website_context}
"""

    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT_NAME,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.choices[0].message.content.strip()

    # Empty response
    if not raw:
        return []

    # Extract JSON array if wrapped in text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    #  Regex extract [ ... ]
    match = re.search(r"\[[\s\S]*\]", raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Fallback
    return []
