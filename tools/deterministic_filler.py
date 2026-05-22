import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DeterministicFiller:
    def __init__(
        self,
        resume_data: Dict[str, Any],
        learned_data: Dict[str, Any] = None,
        cover_letter: str = "",
    ):
        self.resume_data = resume_data or {}
        self.learned_data = learned_data or {}
        self.cover_letter = (cover_letter or "").strip()

        self.contact = self.resume_data.get("contact", {})
        self.name = self.resume_data.get("name") or self.contact.get("name") or ""
        name_parts = self.name.split(" ", 1)
        self.first_name = name_parts[0] if name_parts else ""
        self.last_name = name_parts[1] if len(name_parts) > 1 else ""

        self.email = self.contact.get("email") or self.resume_data.get("email") or ""
        self.phone = self.contact.get("phone") or self.resume_data.get("phone") or ""
        raw_linkedin = self.contact.get("linkedin") or self.resume_data.get("linkedin") or ""
        self.linkedin = self._normalize_linkedin(raw_linkedin)
        self.github = self.contact.get("github") or self.resume_data.get("github") or ""
        self.website = (
            self.contact.get("website")
            or self.contact.get("portfolio")
            or self.resume_data.get("portfolio")
            or self.github
        )
        self.location = self.contact.get("location") or self.resume_data.get("location") or ""
        self.skills = self._as_list(self.resume_data.get("skills", []))
        self.education = self.resume_data.get("education", [])
        self.summary = self.resume_data.get("summary", "")
        self.years = self.resume_data.get("years_of_experience", "")
        self.experience = self._as_list(self.resume_data.get("experience", []))
        self.current_title = self.resume_data.get("current_title") or self._first_experience_title()
        self.position_keywords = self._position_keywords()

    def _normalize_linkedin(self, url: str) -> str:
        url = (url or "").strip()
        if not url:
            return ""
        if url.startswith("http"):
            return url
        handle = url.lstrip("/").replace("linkedin.com/in/", "").replace("in/", "")
        return f"https://www.linkedin.com/in/{handle}"

    def _is_search_or_nav_field(self, field: dict, hints: str) -> bool:
        """Skip LinkedIn/job-site search bars and nav inputs, not application fields."""
        if field.get("tag", "").lower() == "a":
            return True
        search_terms = (
            "search", "keyword", "titles, skill", "location search",
            "type to search", "filter", "query"
        )
        if any(term in hints for term in search_terms):
            return True
        if "job title" in hints and any(term in hints for term in ("search", "filter", "keyword")):
            return True
        name = str(field.get("name", "")).lower()
        if name in ("keywords", "search", "q", "query", "location"):
            return True
        return False

    def _as_list(self, value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        return [value] if value else []

    def _first_experience_title(self) -> str:
        for exp in self.experience:
            if isinstance(exp, dict) and exp.get("title"):
                return str(exp["title"])
        return ""

    def _education_text(self) -> str:
        if isinstance(self.education, str):
            return self.education
        parts = []
        for item in self._as_list(self.education):
            if isinstance(item, dict):
                parts.extend(str(v) for v in item.values() if v)
            elif item:
                parts.append(str(item))
        return " ".join(parts)

    def _position_keywords(self) -> List[str]:
        keywords = []
        if self.current_title:
            keywords.append(str(self.current_title))
        for exp in self.experience[:3]:
            if isinstance(exp, dict) and exp.get("title"):
                keywords.append(str(exp["title"]))
        keywords.extend(str(skill) for skill in self.skills[:12])
        return [k for k in keywords if k]

    def _selector(self, field_id: str) -> str:
        return f"[data-agent-idx='{field_id}']"

    def _field_hints(self, field: dict) -> str:
        keys = ("label", "placeholder", "text", "name", "aria_label", "option_label")
        return " ".join(str(field.get(k, "")) for k in keys).lower()

    def _learned_value_for_field(self, field: dict) -> Optional[str]:
        if not self.learned_data:
            return None

        hints = self._field_hints(field)
        name = str(field.get("name", "")).lower()
        placeholder = str(field.get("placeholder", "")).lower()
        label = str(field.get("label", "")).lower()

        for key, value in self.learned_data.items():
            if value in (None, ""):
                continue
            key_str = str(key)

            ph_match = re.search(r"placeholder=['\"]([^'\"]+)['\"]", key_str, re.I)
            if ph_match:
                ph = ph_match.group(1).lower()
                if ph and (ph in hints or ph in placeholder or ph in label):
                    return str(value)

            name_match = re.search(r"name=['\"]([^'\"]+)['\"]", key_str, re.I)
            if name_match and name_match.group(1).lower() == name:
                return str(value)

            label_match = re.search(r"data-label=['\"]([^'\"]+)['\"]", key_str, re.I)
            if label_match:
                dl = re.sub(r"\s+", " ", label_match.group(1).lower()).strip()
                if dl and (dl[:30] in label or dl[:30] in hints):
                    return str(value)

            if key_str.startswith("[data-agent-idx="):
                idx_match = re.search(r"data-agent-idx=['\"]([^'\"]+)['\"]", key_str, re.I)
                if idx_match:
                    idx = idx_match.group(1)
                    if idx.startswith(("p_", "f")):
                        continue  # Skip dynamic page-specific index matches
                    if idx == field.get("id"):
                        return str(value)

        return None

    def memory_key_for_field(self, field: dict) -> str:
        """Stable key for saving learned answers after a successful fill."""
        placeholder = field.get("placeholder", "")
        if placeholder:
            return f"[placeholder='{placeholder}']"
        name = field.get("name", "")
        if name:
            return f"[name='{name}']"
        label = field.get("label", "")
        if label:
            return f"[data-label='{label[:80]}']"
        field_id = field.get("id")
        if field_id and not field_id.startswith(("p_", "f")):
            return f"[data-agent-idx='{field_id}']"
        return ""

    def _answer_for_text_field(self, hints: str, type_attr: str) -> Optional[str]:
        if any(x in hints for x in ["cover letter", "coverletter", "motivation letter", "why do you want", "message to hiring"]):
            return self.cover_letter or self.summary
        if "email" in hints or type_attr == "email":
            return self.email
        if "first name" in hints or "fname" in hints or hints.strip() == "first":
            return self.first_name
        if "last name" in hints or "lname" in hints or hints.strip() == "last":
            return self.last_name
        if any(x in hints for x in ["full name", "your name", "legal name", "candidate name", "applicant name", "as per certificate"]):
            return self.name
        if any(x in hints for x in ["phone", "mobile", "contact", "whatsapp", "contact number"]) or type_attr == "tel":
            return self.phone
        if "linkedin" in hints:
            return self.linkedin
        if any(x in hints for x in ["website", "portfolio", "github", "blog"]):
            return self.website
        if any(x in hints for x in ["city", "location", "address"]) and "state" not in hints:
            return self.location
        if any(x in hints for x in ["current title", "current role", "job title", "designation", "position"]):
            return self.current_title
        if any(x in hints for x in ["experience", "years"]) and self.years != "":
            return str(self.years)
        if any(x in hints for x in ["skill", "technology", "tech stack"]):
            return ", ".join(str(s) for s in self.skills[:10])
        if any(x in hints for x in ["education", "qualification", "degree", "university", "college"]):
            return self._education_text()
        if any(x in hints for x in ["summary", "about you", "tell us about"]):
            return self.summary
        if "notice" in hints:
            return "Immediate"
        if any(x in hints for x in ["ctc", "salary", "compensation"]):
            return "Negotiable"
        if re.search(r"(^|\s)name(\s|\*|$)", hints) and not any(
            x in hints for x in ["user", "company", "file", "project", "course", "school", "username", "job title"]
        ):
            return self.name
        return None

    def _default_option_value(self, hints: str) -> str:
        if "phone country code" in hints or "country code" in hints:
            return "India (+91)"
        if any(x in hints for x in ["position", "role", "job title", "designation", "profile"]):
            return self.current_title or (self.position_keywords[0] if self.position_keywords else "")
        if "country" in hints:
            return "India"
        if "notice" in hints:
            return "Immediate"
        if any(x in hints for x in ["experience", "level"]):
            try:
                years = float(self.years or 0)
                if years < 1:
                    return "Entry Level"
                if years < 4:
                    return "Mid Level"
                return "Senior"
            except Exception:
                return str(self.years or "")
        if any(x in hints for x in ["job type", "employment"]):
            return "Full-time"
        if any(x in hints for x in ["work authorization", "authorized"]):
            return "Authorized to work"
        if any(x in hints for x in ["source", "hear about"]):
            return "LinkedIn"
        if any(x in hints for x in ["gender", "race", "veteran", "disability"]):
            return "Prefer not to say"
        if any(x in hints for x in ["skill", "technology", "stack"]):
            return str(self.skills[0]) if self.skills else ""
        return self.current_title or ""

    def _score_option_text(self, option_text: str) -> int:
        text = re.sub(r"\s+", " ", option_text.lower()).strip()
        if not text or text in ("choose", "select", "clear selection"):
            return 0
        score = 0
        for keyword in self.position_keywords:
            key = str(keyword).lower().strip()
            if not key:
                continue
            if key == text or key in text or text in key:
                score = max(score, 3)
                continue
            key_tokens = {t for t in re.split(r"[^a-z0-9+#.]+", key) if len(t) > 1}
            text_tokens = {t for t in re.split(r"[^a-z0-9+#.]+", text) if len(t) > 1}
            overlap = len(key_tokens & text_tokens)
            if overlap:
                score = max(score, overlap)
        return score

    def _choice_action(self, field: dict, hints: str) -> Optional[dict]:
        field_id = field.get("id")
        role = field.get("role", "").lower()
        type_attr = field.get("type", "").lower()
        selector = self._selector(field_id)
        text = f"{hints} {field.get('text', '').lower()} {field.get('option_label', '').lower()}"

        if any(x in text for x in ["sponsor", "visa sponsorship", "require sponsorship"]):
            if any(x in text for x in ["no", "not require", "false", "without"]):
                return {"type": "radio", "selector": selector}
            return None
        if any(x in text for x in ["relocate", "authorized", "eligible", "legally", "background check", "terms", "agree", "confirm", "consent"]):
            if type_attr == "checkbox" or role == "checkbox":
                return {"type": "check", "selector": selector}
            if any(x in text for x in ["yes", "true", "agree", "accept"]):
                return {"type": "radio", "selector": selector}
            return None
        if any(x in text for x in ["gender", "race", "veteran", "disability"]):
            if any(x in text for x in ["prefer not", "decline", "do not wish", "rather not"]):
                return {"type": "radio", "selector": selector}
            return None
        return None

    def _semantic_bucket(self, field: dict) -> str:
        hints = self._field_hints(field)
        if field.get("type", "").lower() == "file":
            return "resume"
        if "email" in hints or field.get("type") == "email":
            return "email"
        if any(x in hints for x in ("phone", "mobile", "whatsapp", "tel")):
            return "phone"
        if "first name" in hints or "fname" in hints:
            return "first_name"
        if "last name" in hints or "lname" in hints:
            return "last_name"
        if any(x in hints for x in ("full name", "your name", "legal name")):
            return "full_name"
        if "linkedin" in hints:
            return "linkedin"
        if "cover letter" in hints or "motivation" in hints:
            return "cover_letter"
        if any(x in hints for x in ("city", "location")) and "state" not in hints:
            return "location"
        if "notice" in hints:
            return "notice"
        if any(x in hints for x in ("ctc", "salary")):
            return "salary"
        if any(x in hints for x in ("years of experience", "total experience")):
            return "experience_years"
        if "experience" in hints and "years" in hints:
            return "experience_years"
        if any(x in hints for x in ("job position", "job role", "position applying", "role applying")):
            return "job_position"
        return field.get("id", hints[:40])

    def determine_actions(self, form_json: dict) -> tuple[List[dict], dict]:
        actions = []
        unhandled_fields = []
        used_buckets: set[str] = set()
        best_option_action: Optional[tuple[int, dict, dict]] = None

        for field in form_json.get("fields", []):
            field_id = field.get("id")
            if not field_id:
                continue

            type_attr = field.get("type", "").lower()
            role = field.get("role", "").lower()
            tag = field.get("tag", "").lower()
            combined_hints = self._field_hints(field)
            logger.info("Field hints: [%s] -> %s", field_id, combined_hints)
            if self._is_search_or_nav_field(field, combined_hints):
                logger.info("Skipping search/nav field: %s", field_id)
                continue

            current_value = str(field.get("value", "")).strip()
            if current_value:
                is_choice_shell = tag not in ("input", "textarea", "select") or role in (
                    "listbox", "combobox", "option", "radio", "checkbox"
                )
                if not is_choice_shell:
                    continue

            action = None
            learned_value = self._learned_value_for_field(field)

            is_upload_eligible = type_attr == "file"
            if is_upload_eligible and tag != "a" and role != "link":
                action = {
                    "type": "upload",
                    "selector": self._selector(field_id),
                    "_field": field,
                }
            elif tag == "select" or role in ("listbox", "combobox"):
                value = learned_value or self._default_option_value(combined_hints)
                if value:
                    action = {
                        "type": "select_dropdown",
                        "selector": self._selector(field_id),
                        "value": value,
                        "keywords": self.position_keywords,
                    }
            elif role == "option":
                option_text = f"{field.get('option_label', '')} {field.get('text', '')} {field.get('label', '')}".lower()
                score = self._score_option_text(option_text)
                if score >= 1 and any(x in combined_hints for x in ("job position", "job role", "position")):
                    candidate = {"type": "click", "selector": self._selector(field_id), "_field": field}
                    if not best_option_action or score > best_option_action[0]:
                        best_option_action = (score, candidate, field)
                    action = None
            elif type_attr in ("checkbox", "radio") or role in ("checkbox", "radio"):
                action = self._choice_action(field, combined_hints)
            else:
                is_fillable = (
                    tag in ("input", "textarea")
                    or role == "textbox"
                    or field.get("contenteditable") == "true"
                )
                if is_fillable:
                    value = learned_value or self._answer_for_text_field(combined_hints, type_attr)
                    if value:
                        action = {
                            "type": "fill",
                            "selector": self._selector(field_id),
                            "value": value,
                            "_field": field,
                        }

            if action:
                bucket = self._semantic_bucket(field)
                if bucket in used_buckets and action.get("type") == "fill":
                    continue
                used_buckets.add(bucket)
                logger.info("Deterministic match: %s -> %s", field_id, action.get("value", action["type"]))
                actions.append(action)
            else:
                unhandled_fields.append(field)

        if best_option_action and "job_position" not in used_buckets:
            _, option_action, option_field = best_option_action
            used_buckets.add("job_position")
            logger.info("Deterministic option match: %s", option_field.get("id"))
            actions.append(option_action)

        return actions, {"fields": unhandled_fields, "buttons": form_json.get("buttons", [])}
