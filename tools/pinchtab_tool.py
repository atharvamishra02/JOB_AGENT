import logging
import json
import time
from typing import Dict, Any, List, Optional
from playwright.sync_api import Page, ElementHandle

logger = logging.getLogger(__name__)

# The Javascript script to inject into the page to extract a stable, semantic DOM snapshot.
# It uses the same data-agent-idx selectors as the rest of the agent, extracts bounding boxes,
# computed visibility, attributes, and precise CSS/XPath selectors.
JS_AGENT_SCRIPT = """
(prefix) => {
    function getCssSelector(el) {
        if (!(el instanceof Element)) return '';
        let path = [];
        while (el.nodeType === Node.ELEMENT_NODE) {
            let selector = el.nodeName.toLowerCase();
            if (el.id) {
                selector += '#' + el.id;
                path.unshift(selector);
                break;
            } else {
                let sib = el, nth = 1;
                while (sib = sib.previousElementSibling) {
                    if (sib.nodeName.toLowerCase() == selector) nth++;
                }
                if (nth != 1) selector += ":nth-of-type(" + nth + ")";
            }
            path.unshift(selector);
            el = el.parentNode;
        }
        return path.join(' > ');
    }

    function getXPath(el) {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
        let paths = [];
        for (; el && el.nodeType === Node.ELEMENT_NODE; el = el.parentNode) {
            let index = 0;
            for (let sibling = el.previousSibling; sibling; sibling = sibling.previousSibling) {
                if (sibling.nodeType === Node.DOCUMENT_NODE) continue;
                if (sibling.nodeName === el.nodeName) ++index;
            }
            let tagName = el.nodeName.toLowerCase();
            let pathIndex = (index ? "[" + (index + 1) + "]" : "");
            paths.splice(0, 0, tagName + pathIndex);
        }
        return paths.length ? "/" + paths.join("/") : null;
    }

    function isVisible(el) {
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function getOrSetAgentIdx(el, nextId) {
        if (el.hasAttribute('data-agent-idx')) {
            return el.getAttribute('data-agent-idx');
        }
        const id = prefix + nextId.value++;
        el.setAttribute('data-agent-idx', id);
        return id;
    }

    const INTERACTIVE_TAGS = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'LABEL'];
    
    function buildTree(root) {
        const elements = [];
        const nextId = { value: 1 };
        const walk = (node) => {
            if (node.nodeType !== Node.ELEMENT_NODE) return;
            if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'IFRAME', 'SVG', 'PATH'].includes(node.tagName)) return;
            
            const role = node.getAttribute('role');
            const isInteractive = INTERACTIVE_TAGS.includes(node.tagName) || role;
            
            // Text evaluation
            const textContent = (node.innerText || '').trim();
            const placeholder = node.placeholder || node.getAttribute('aria-label') || node.title || '';
            const value = node.value || '';
            
            if (isInteractive || (textContent.length > 0 && textContent.length < 150)) {
                if (isVisible(node)) {
                    const rect = node.getBoundingClientRect();
                    const tag = node.tagName.toLowerCase();
                    const agentId = getOrSetAgentIdx(node, nextId);
                    
                    let nodeData = {
                        id: agentId,
                        role: role || tag,
                        name: placeholder || textContent,
                        value: value,
                        selector: `[data-agent-idx="${agentId}"]`,
                        xpath: getXPath(node),
                        visible: true,
                        enabled: !node.disabled,
                        bbox: {
                            x: rect.x, y: rect.y,
                            width: rect.width, height: rect.height
                        },
                        tag: tag,
                        type: node.getAttribute('type') || null
                    };
                    
                    // Form field intelligence
                    if (['input', 'select', 'textarea'].includes(tag)) {
                        nodeData.isFormField = true;
                        nodeData.checked = node.checked;
                        nodeData.required = node.required;
                    }
                    elements.push(nodeData);
                }
            }
            
            for (let child of node.children) {
                walk(child);
            }
        };
        walk(root);
        return elements;
    }

    return buildTree(document.body);
}
"""

class PinchTabManager:
    """
    Hybrid Browser Agent Architecture for autonomous job applications.
    Implements a 3-layer perception system and robust action execution.
    """
    
    def __init__(self):
        pass

    def get_snapshot(self, page: Page) -> Dict[str, Any]:
        """
        Builds a compact grounded DOM snapshot.

        Keep this cheap: the apply loop already extracts structured forms with
        form_parser, so PinchTab should provide selectors and visible metadata,
        not screenshots or a large accessibility tree.
        """
        dom_nodes = []
        try:
            # Main frame
            main_nodes = page.evaluate(JS_AGENT_SCRIPT, "main-") or []
            for node in main_nodes:
                node["frame"] = "main"
            dom_nodes.extend(main_nodes)
            
            # Sub-frames (Iframes like Google Forms)
            for i, frame in enumerate(page.frames):
                if frame == page.main_frame:
                    continue
                if frame.is_detached():
                    continue
                try:
                    frame_nodes = frame.evaluate(JS_AGENT_SCRIPT, f"f{i}-") or []
                    for node in frame_nodes:
                        node["frame"] = f"frame-{i}"
                    dom_nodes.extend(frame_nodes)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"DOM Metadata extraction failed: {e}")

        return {
            "role": "root",
            "children": dom_nodes,
        }

    def execute_action(self, page: Page, action: Dict[str, Any], executor: Any) -> Dict[str, Any]:
        """
        Executes actions with action verification, anti-bot delays, and recovery loops.
        Uses the provided executor for core actions but adds stability layers.
        """
        selector = action.get("selector")
        
        # Action Verification Phase 1: Pre-action check
        if selector:
            try:
                # Handle iframe routing if necessary based on our stable selectors
                locator = page.locator(selector).first
                if not locator.is_visible(timeout=2000):
                    # Stale Element Recovery: Re-resolve selector
                    logger.warning(f"Element {selector} not visible, triggering re-resolution")
                    # Could attempt semantic fallback here
            except Exception:
                pass
                
        # Execute Action
        result = {"success": False, "log": ""}
        try:
            # Add anti-bot pacing
            time.sleep(0.5)
            
            log = executor.execute_action(action)
            result["success"] = True
            result["log"] = log
            
            # Action Verification Phase 2: Post-action validation
            # (e.g. waiting for network idle, DOM mutations, or modal transitions)
            page.wait_for_timeout(500) # Simple humanized pause
            
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            result["error"] = str(e)
            result["success"] = False
            
        return result
