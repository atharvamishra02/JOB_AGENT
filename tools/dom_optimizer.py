import logging
import re
from bs4 import BeautifulSoup, NavigableString
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def _get_nearby_label(el, soup):
    """Find label text near an input element via multiple strategies."""
    if el.get("id"):
        label = soup.find("label", attrs={"for": el["id"]})
        if label:
            return label.get_text(strip=True)[:60]

    parent = el.parent
    if parent and parent.name == "label":
        text = parent.get_text(strip=True)[:60]
        if text:
            return text

    for sib in el.previous_siblings:
        if isinstance(sib, NavigableString):
            t = sib.strip()
            if t:
                return t[:60]
        elif hasattr(sib, "get_text"):
            t = sib.get_text(strip=True)
            if t and len(t) < 80:
                return t[:60]
            break

    labels = []
    for attr in ["aria-labelledby", "aria-describedby"]:
        if el.get(attr):
            ids = el[attr].split()
            for ref_id in ids:
                ref = soup.find(id=ref_id)
                if ref and ref.get_text(strip=True):
                    labels.append(ref.get_text(strip=True))
    if labels:
        return " - ".join(labels)[:100]

    parent = el.parent
    if parent:
        t = parent.get_text(separator=" ", strip=True)
        if 0 < len(t) < 150:
            return t[:80]

    return ""

def simplify_html(html: str) -> str:
    """
    Minifies HTML to the bare essentials for navigation and form filling.
    Original implementation from deep_browser_utils.py.
    """
    soup = BeautifulSoup(html, "html.parser")

    for s in soup(["script", "style", "svg", "path", "meta", "link", "noscript"]):
        s.decompose()

    modal = (
        soup.find(attrs={"aria-modal": "true"})
        or soup.find(attrs={"data-test-modal": True})
        or soup.find(class_=re.compile(
            r"jobs-easy-apply-modal|artdeco-modal__content|jpac-modal|apply-drawer"
            r"|chatbot-box|snb-content|drawerContainer|chat-bot|naukri-apply",
            re.I
        ))
        or soup.find(class_=re.compile(
            r"(?<!\w)(modal|dialog|overlay-content|popup-content|drawer|sidebar-content)(?!\w)",
            re.I
        ))
    )

    modal_found_but_empty = False
    if modal:
        test_elements = modal.select(
            'input:not([type="hidden"]), button, select, textarea, '
            '[role="textbox"], [contenteditable="true"], [role="option"], [role="radio"]'
        )
        if not test_elements:
            modal_found_but_empty = True
            modal = None

    search_root = modal if modal else soup

    interactive_selectors = [
        'input:not([type="hidden"])', 'button', 'select', 'textarea', 'a',
        '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]',
        '[role="option"]', '[role="listbox"]', '[role="combobox"]', '[role="tab"]',
        '[role="textbox"]', '[contenteditable="true"]',
        '.btn', '.button', '[onclick]',
        '[class*="apply" i]', '[id*="apply" i]', '[data-test*="apply" i]', '[aria-label*="apply" i]', '[name*="apply" i]',
        '[role="alert"]', '[aria-live="polite"]', '[aria-live="assertive"]',
        '.error', '.invalid-feedback', '.form-error', '[id*="error"]', '[class*="error"]',
    ]

    def build_lines(root) -> list[str]:
        raw_elements = []
        for selector in interactive_selectors:
            for el in root.select(selector):
                raw_elements.append(el)

        lines = []
        seen_ids = set()
        for el in raw_elements:
            el_id = id(el)
            if el_id in seen_ids:
                continue
            seen_ids.add(el_id)

            attrs = {}
            for k in ["type", "placeholder", "aria-label", "title", "role", "value",
                       "href", "id", "name", "aria-labelledby", "checked", "selected",
                       "disabled", "contenteditable", "aria-checked", "aria-selected"]:
                val = el.get(k)
                if val:
                    if isinstance(val, list):
                        val = " ".join(val)
                    attrs[k] = str(val)[:100]

            label_text = ""
            if el.name in ("input", "select", "textarea") or attrs.get("role") in (
                "textbox", "combobox", "listbox", "radio", "checkbox"
            ):
                label_text = _get_nearby_label(el, root)

            if not label_text and el.get("data-label"):
                label_text = el.get("data-label", "")[:100]

            text = el.get_text(separator=" ", strip=True)[:150]

            options_str = ""
            if el.name == "select":
                opts = []
                for opt in el.find_all("option"):
                    ov = opt.get("value", "")
                    ot = opt.get_text(strip=True)
                    if ot:
                        opts.append(f"{ot}" + (f"={ov}" if ov and ov != ot else ""))
                if opts:
                    options_str = " [options: " + " | ".join(opts[:15]) + "]"

            if (not text and not options_str
                    and not any(k in attrs for k in ["aria-label", "placeholder", "title", "id", "name"])
                    and not label_text):
                continue

            idx = el.get("data-agent-idx")
            if not idx:
                continue

            attr_str = " ".join([f'{k}="{v}"' for k, v in attrs.items()])
            label_str = f' label="{label_text}"' if label_text else ""

            lines.append(
                f"<{el.name} data-agent-idx=\"{idx}\"{label_str} {attr_str}>"
                f"{text}{options_str}</{el.name}>"
            )

        return lines

    def build_text_hints(root) -> list[str]:
        hints = []
        seen = set()
        selectors = [
            "h1", "h2", "h3", "[role='heading']", "[role='status']",
            "[aria-live='polite']", "[aria-live='assertive']",
            ".freebirdFormviewerViewResponseConfirmationMessage",
            ".freebirdFormviewerViewItemsItemErrorMessage",
            ".artdeco-inline-feedback--error",
            ".jobs-easy-apply-form-section__group-title",
            ".naukri-apply__title",
            "[class*='confirmation']", "[class*='success']",
            "[class*='error-msg']", "[class*='validat']",
        ]
        for selector in selectors:
            for el in root.select(selector):
                text = el.get_text(separator=" ", strip=True)
                if not text or len(text) < 3:
                    continue
                text = re.sub(r"\s+", " ", text)[:250]
                lowered = text.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                hints.append(f"<text>{text}</text>")
        return hints[:25]

    lines = build_text_hints(search_root) + build_lines(search_root)
    if modal_found_but_empty:
        lines = build_text_hints(soup) + build_lines(soup)

    result = "\n".join(dict.fromkeys(lines))
    result = re.sub(r" +", " ", result)

    if modal_found_but_empty:
        result = "[MODAL DETECTED BUT EMPTY - FULL PAGE FALLBACK]\n" + result
    elif modal:
        result = "[MODAL DETECTED - FOCUS HERE]\n" + result

    if len(result) > 45000:
        result = result[:45000] + "\n... [DOM Truncated]"

    return result

class DOMOptimizer:
    """
    Advanced DOM compression pipeline.
    Reduces prompt size by pruning non-essential nodes and focusing on interactive regions.
    """
    
    def __init__(self, token_budget: int = 5000):
        self.token_budget = token_budget

    def optimize(self, html: str) -> str:
        """
        Main optimization pipeline:
        1. Parse & Initial Prune
        2. Extract Interactive Regions
        3. Semantic Summarization
        """
        # If the input is already simplified DOM string (from simplify_html), 
        # we can just return it or optimize it further.
        # For now, let's assume it might be raw HTML or simplified.
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove definitely useless tags
        for s in soup(["script", "style", "svg", "path", "meta", "link", "noscript", "iframe"]):
            s.decompose()

        # Identify 'Interactive Elements' - elements with our custom attribute
        interactive_elements = soup.find_all(attrs={"data-agent-idx": True})
        
        if not interactive_elements:
            # Fallback to the original simplify_html logic if no indices are found
            # (Though in our pipeline indices should always be there)
            return simplify_html(html)

        # Region Extraction: Find common ancestors for interactive elements
        essential_nodes = set()
        for el in interactive_elements:
            essential_nodes.add(el)
            parent = el.parent
            depth = 0
            while parent and parent.name != "body" and depth < 5:
                essential_nodes.add(parent)
                parent = parent.parent
                depth += 1

        return self._reconstruct_lean_dom(soup.find("body"), essential_nodes)

    def _reconstruct_lean_dom(self, node, essential_nodes) -> str:
        """Recursively builds a string representation of only essential nodes."""
        if not node:
            return ""
        
        if node not in essential_nodes and not isinstance(node, NavigableString):
            text = node.get_text(strip=True)
            if 0 < len(text) < 100:
                return f"<text>{text}</text>\n"
            return ""

        if isinstance(node, NavigableString):
            text = node.strip()
            return text if text else ""

        idx = node.get("data-agent-idx", "")
        tag_str = f"<{node.name}"
        if idx:
            tag_str += f' data-agent-idx="{idx}"'
            
        for attr in ["type", "placeholder", "role", "value"]:
            if node.get(attr):
                tag_str += f' {attr}="{node[attr]}"'
        
        tag_str += ">"
        
        children_str = ""
        for child in node.children:
            children_str += self._reconstruct_lean_dom(child, essential_nodes)
            
        if not children_str and not idx:
            return ""
            
        return f"{tag_str}{children_str}</{node.name}>\n"
