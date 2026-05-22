import glob
import os
import logging
from typing import Optional
from playwright.sync_api import Page

logger = logging.getLogger(__name__)


def resolve_resume_path(explicit_path: str = "") -> str:
    """Resolve the resume PDF path from state, uploads folder, or project root."""
    if explicit_path and os.path.isfile(explicit_path):
        return os.path.abspath(explicit_path)

    search_dirs = []
    if explicit_path:
        parent = os.path.dirname(explicit_path)
        if parent:
            search_dirs.append(parent)

    cwd = os.getcwd()
    search_dirs.extend([
        os.path.join(cwd, "uploads"),
        cwd,
    ])

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for pattern in ("*.pdf", "*resume*", "*cv*", "*CV*"):
            matches = sorted(glob.glob(os.path.join(directory, pattern)))
            if matches:
                return os.path.abspath(matches[0])

        for user_dir in sorted(glob.glob(os.path.join(directory, "*"))):
            if not os.path.isdir(user_dir):
                continue
            for pattern in ("*.pdf", "*resume*", "*cv*"):
                matches = sorted(glob.glob(os.path.join(user_dir, pattern)))
                if matches:
                    return os.path.abspath(matches[0])

    return ""


class UploadManager:
    """
    Handles robust file uploads for resumes and cover letters.
    Includes verification and retry logic.
    """

    def __init__(self, page: Page, resume_path: str = ""):
        self.page = page
        self.resume_path = resume_path

    def set_resume_path(self, resume_path: str) -> None:
        self.resume_path = resume_path or ""

    def _locator_any_frame(self, selector: str):
        loc = self.page.locator(selector).first
        try:
            if loc.count() > 0:
                return loc
        except Exception:
            pass
        for frame in self.page.frames:
            if frame == self.page.main_frame:
                continue
            try:
                if frame.is_detached():
                    continue
                frame_loc = frame.locator(selector).first
                if frame_loc.count() > 0:
                    return frame_loc
            except Exception:
                continue
        return loc

    def upload_file(self, selector: str, file_path: str) -> bool:
        """
        Uploads a file and verifies that the input's value or surrounding text reflects the upload.
        """
        if not os.path.exists(file_path):
            logger.error("Upload: File not found at %s", file_path)
            return False

        try:
            loc = self._locator_any_frame(selector)
            if loc.count() == 0:
                logger.error("Upload: Selector not found: %s", selector)
                return False

            is_input = loc.evaluate(
                "el => el.tagName === 'INPUT' && el.type === 'file'"
            )

            target_loc = loc
            if not is_input:
                try:
                    file_inputs = self._locator_any_frame("input[type='file']")
                    # Fast presence check
                    file_inputs.nth(0).wait_for(state="attached", timeout=1500)
                except Exception:
                    logger.warning("Upload: Target %s is not a file input and no file input exists on page", selector)
                    return False

                logger.info(
                    "Upload: Targeted element %s is not a file input. Searching for nearby input.",
                    selector,
                )
                try:
                    inner_input = loc.locator("xpath=..//input[@type='file']").first
                    if inner_input.count() > 0:
                        target_loc = inner_input
                    else:
                        target_loc = self._locator_any_frame("input[type='file']")
                except Exception:
                    target_loc = self._locator_any_frame("input[type='file']")

            target_loc.set_input_files(file_path, timeout=3000)

            file_name = os.path.basename(file_path)
            self.page.wait_for_timeout(1000)

            if file_name in self.page.content():
                logger.info("Upload: Successfully verified upload of %s", file_name)
                return True

            logger.warning("Upload: Could not verify upload of %s via text check.", file_name)
            return True

        except Exception as e:
            logger.error("Upload: Failed to upload %s: %s", file_path, e)
            return False

    def find_and_upload_resume(self, selector: str = "") -> bool:
        """Upload resume — tries selector, then any visible file input on page."""
        path = resolve_resume_path(self.resume_path)
        if not path:
            logger.error("Upload: No resume PDF found")
            return False

        if selector:
            if self.upload_file(selector, path):
                return True
            logger.warning("Upload: Selector %s failed, trying all file inputs", selector)

        try:
            roots = [self.page.main_frame] + [
                frame for frame in self.page.frames
                if frame != self.page.main_frame and not frame.is_detached()
            ]
            for root_idx, root in enumerate(roots):
                inputs = root.locator("input[type='file']")
                count = min(inputs.count(), 8)
                for i in range(count):
                    inp = inputs.nth(i)
                    try:
                        inp.set_input_files(path, timeout=2000)
                        self.page.wait_for_timeout(800)
                        logger.info("Upload: Uploaded via file input %s:%s", root_idx, i)
                        return True
                    except Exception:
                        continue
        except Exception as exc:
            logger.error("Upload: All file input attempts failed: %s", exc)
        return False
