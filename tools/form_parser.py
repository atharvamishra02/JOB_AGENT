import logging
from playwright.sync_api import Page

from tools.deep_browser_tools import (
    index_page_elements,
    find_apply_modal_selector,
    FIND_APPLY_ROOT_JS,
)

logger = logging.getLogger(__name__)

EXTRACT_FORM_JS = """
() => {
    const interactive = '[data-agent-idx]';
    const elements = document.querySelectorAll(interactive);
    let fields = [];
    let buttons = [];

    elements.forEach((el) => {
        const idx = el.getAttribute('data-agent-idx');
        if (!idx) return;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;

        const tag = el.tagName.toLowerCase();
        const type = el.getAttribute('type') || '';
        const role = el.getAttribute('role') || '';

        let label = el.getAttribute('aria-label') || '';
        const labelledBy = el.getAttribute('aria-labelledby') || '';
        function textForIds(ids) {
            return ids.split(/\\s+/).map(id => {
                const ref = document.getElementById(id);
                return ref && ref.innerText ? ref.innerText.trim() : '';
            }).filter(Boolean).join(' ');
        }
        if (!label && labelledBy) label = textForIds(labelledBy);
        if (!label && el.id) {
            const labelEl = document.querySelector(`label[for="${el.id}"]`);
            if (labelEl) label = labelEl.innerText.trim();
        }
        if (!label) {
            const questionRoot = el.closest(
                '.jobs-easy-apply-form-section__grouping, .freebirdFormviewerViewItemsItemItem, ' +
                '.Qr7Oae, .geS5n, .ant-form-item, .form-group, .field, [class*="question" i], [role="listitem"]'
            );
            if (questionRoot && questionRoot.innerText) {
                const lines = questionRoot.innerText.split('\\n')
                    .map(s => s.trim())
                    .filter(Boolean)
                    .filter(s => !/^(required|optional|clear selection|your answer)$/i.test(s));
                label = lines.slice(0, 3).join(' | ');
            }
        }
        if (!label) {
            const googleQuestion = el.closest('.Qr7Oae, [data-params]');
            if (googleQuestion && googleQuestion.innerText) {
                const lines = googleQuestion.innerText.split('\\n')
                    .map(s => s.trim())
                    .filter(Boolean)
                    .filter(s => !/^(required|optional|clear selection|your answer)$/i.test(s));
                label = lines.slice(0, 3).join(' | ');
            }
        }
        if (!label && (tag === 'button' || role === 'button')) label = el.innerText.trim();
        if (!label && el.parentElement && el.parentElement.tagName.toLowerCase() === 'label') {
            label = el.parentElement.innerText.trim();
        }

        const placeholder = el.getAttribute('placeholder') || '';
        let value = '';
        if (tag === 'select') value = (el.value || '').trim();
        else if (role === 'combobox' || role === 'listbox') value = (el.getAttribute('aria-activedescendant') || '').trim();
        else value = (el.value || '').trim();
        const text = el.innerText ? el.innerText.trim().substring(0, 50) : '';
        const name = el.getAttribute('name') || '';
        let optionLabel = '';
        if (type === 'checkbox' || type === 'radio' || role === 'checkbox' || role === 'radio') {
            const optionRoot = el.closest('label, [role="radio"], [role="checkbox"]');
            if (optionRoot && optionRoot.innerText) optionLabel = optionRoot.innerText.trim();
            if (!optionLabel && el.getAttribute('aria-label')) optionLabel = el.getAttribute('aria-label');
        }

        const elementData = {
            id: idx, tag, type, role,
            label: label.substring(0, 120),
            placeholder: placeholder.substring(0, 100),
            name: name.substring(0, 100),
            aria_label: (el.getAttribute('aria-label') || '').substring(0, 100),
            option_label: optionLabel.substring(0, 100),
            value: value.substring(0, 200),
            text: text,
        };

        if (tag === 'select') {
            elementData.options = Array.from(el.querySelectorAll('option'))
                .map(o => o.textContent.trim()).filter(Boolean).slice(0, 25);
        }

        const lowLabel = label.toLowerCase();
        const lowText = text.toLowerCase();
        const isButton = (
            tag === 'button' || role === 'button' || type === 'submit' ||
            lowLabel.includes('next') || lowText === 'next' ||
            lowLabel.includes('continue') || lowLabel.includes('review') ||
            lowLabel.includes('submit') || lowText.includes('submit') ||
            lowLabel.includes('send') || lowText.includes('send')
        );
        if (isButton) buttons.push(elementData);
        else fields.push(elementData);
    });
    return { fields, buttons };
}
"""


def _field_hints(field: dict) -> str:
    keys = ("label", "placeholder", "text", "name", "aria_label", "option_label")
    return " ".join(str(field.get(k, "")) for k in keys).lower()


def _semantic_bucket(field: dict) -> str:
    hints = _field_hints(field)
    if field.get("type", "").lower() == "file":
        return "resume"
    buckets = (
        ("email", ("email", "e-mail")),
        ("phone", ("phone", "mobile", "contact number", "whatsapp", "tel")),
        ("first_name", ("first name", "fname", "given name")),
        ("last_name", ("last name", "lname", "surname", "family name")),
        ("full_name", ("full name", "your name", "candidate name", "legal name")),
        ("linkedin", ("linkedin",)),
        ("location", ("city", "location", "address")),
        ("cover_letter", ("cover letter", "motivation", "message")),
        ("experience", ("years of experience", "total experience", "experience years")),
        ("salary", ("ctc", "salary", "compensation", "expected pay")),
        ("notice", ("notice period", "notice")),
    )
    for key, terms in buckets:
        if any(t in hints for t in terms):
            return key
    if "name" in hints and "company" not in hints and "user" not in hints:
        return "full_name"
    return hints[:60] or field.get("id", "unknown")


def _is_noise_field(field: dict) -> bool:
    hints = _field_hints(field)
    if field.get("tag", "").lower() == "a":
        return True
    noise = (
        "search", "keyword", "titles, skill", "type to search",
        "filter", "sign in", "join now", "messaging", "notifications",
        "tailor my resume", "guide overlay", "post a job", "talent solutions",
    )
    if any(term in hints for term in noise):
        return True
    if "job title" in hints and any(term in hints for term in ("search", "filter", "keyword")):
        return True
    name = str(field.get("name", "")).lower()
    return name in ("keywords", "search", "q", "query", "geo")


def _dedupe_fields(fields: list) -> list:
    """Keep one field per semantic type (avoids filling phone twice)."""
    best_by_bucket: dict[str, dict] = {}
    order = []
    for field in fields:
        bucket = _semantic_bucket(field)
        if bucket not in best_by_bucket:
            best_by_bucket[bucket] = field
            order.append(bucket)
            continue
        prev = best_by_bucket[bucket]
        prev_hints = len(_field_hints(prev))
        new_hints = len(_field_hints(field))
        if new_hints > prev_hints or (field.get("label") and not prev.get("label")):
            best_by_bucket[bucket] = field
    return [best_by_bucket[b] for b in order]


def _score_apply_form(form_json: dict) -> int:
    score = 0
    scope = form_json.get("_scope", "").lower()
    
    # Large bonus for modals as they are almost certainly the application surface
    if "modal" in scope:
        score += 25
    elif "frame" in scope:
        score += 10

    apply_terms = (
        "first name", "last name", "email", "phone", "resume", "cover letter",
        "linkedin", "experience", "notice", "ctc", "salary",
    )
    for field in form_json.get("fields", []):
        hints = _field_hints(field)
        if any(term in hints for term in apply_terms):
            score += 3
        if field.get("type", "").lower() == "file":
            score += 8
    for btn in form_json.get("buttons", []):
        text = _field_hints(btn)
        if any(term in text for term in ("next", "continue", "review", "submit application", "submit")):
            score += 5
    return score


def _meaningful_buttons(buttons: list) -> list:
    flow_terms = ("apply", "next", "continue", "review", "submit", "send", "finish", "upload")
    result = []
    for btn in buttons:
        text = _field_hints(btn)
        if any(term in text for term in flow_terms):
            result.append(btn)
    return result


def _extract_from_context(page: Page, root_selector: str, scope_label: str) -> dict:
    page.evaluate(FIND_APPLY_ROOT_JS)
    index_page_elements(page, root_selector=root_selector, reset=True)
    data = page.evaluate(EXTRACT_FORM_JS) or {"fields": [], "buttons": []}
    fields = _dedupe_fields([f for f in data.get("fields", []) if not _is_noise_field(f)])
    buttons = data.get("buttons", [])
    if not fields:
        buttons = _meaningful_buttons(buttons)
    return {
        "fields": fields,
        "buttons": buttons,
        "_scope": scope_label,
    }


def extract_form_json(page: Page) -> dict:
    """
    Extract form fields from apply modal first, then best-scoring page region.
    Indexes once per call; selectors remain stable until next extract.
    """
    try:
        page.evaluate(FIND_APPLY_ROOT_JS)
    except Exception:
        pass

    modal_sel = find_apply_modal_selector(page)
    candidates = []

    if modal_sel:
        try:
            modal_data = _extract_from_context(page, modal_sel, f"modal:{modal_sel}")
            if modal_data.get("fields") or modal_data.get("buttons"):
                candidates.append(modal_data)
        except Exception as exc:
            logger.warning("Modal extract failed: %s", exc)

    try:
        main_data = _extract_from_context(page, "", "main")
        if main_data.get("fields") or main_data.get("buttons"):
            candidates.append(main_data)
    except Exception as exc:
        logger.warning("Main extract failed: %s", exc)

    frame_counter = 1
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            if frame.is_detached():
                continue
            index_page_elements(frame, prefix=f"f{frame_counter}_", reset=True)
            frame_data = frame.evaluate(EXTRACT_FORM_JS) or {"fields": [], "buttons": []}
            fields = _dedupe_fields([f for f in frame_data.get("fields", []) if not _is_noise_field(f)])
            buttons = _meaningful_buttons(frame_data.get("buttons", []))
            if fields or buttons:
                candidates.append({
                    "fields": fields,
                    "buttons": buttons,
                    "_scope": f"frame:{frame_counter}",
                })
            frame_counter += 1
        except Exception:
            continue

    if not candidates:
        logger.warning("Form scope: no fields found on page")
        return {"fields": [], "buttons": []}

    best = max(candidates, key=_score_apply_form)
    logger.info(
        "Form scope: %s (%s fields, score=%s)",
        best.get("_scope"),
        len(best.get("fields", [])),
        _score_apply_form(best),
    )
    return best
