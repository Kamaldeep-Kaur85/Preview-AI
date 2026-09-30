"""
scratch/patch_main.py
Updates app/main.py with environment dependency support and UI performance optimizations.
"""
import re

with open("app/main.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update get_risk_colors to include CRITICAL
old_colors = '''def get_risk_colors(colors):

    return {

        "HIGH": colors["red"], "MEDIUM": colors["yellow"], "LOW": colors["green"],'''
new_colors = '''def get_risk_colors(colors):

    return {

        "CRITICAL": colors["red"],

        "HIGH": colors["red"], "MEDIUM": colors["yellow"], "LOW": colors["green"],'''

if old_colors in content:
    content = content.replace(old_colors, new_colors, 1)
    print("1. get_risk_colors patched")
else:
    print("1. get_risk_colors NOT matched")

# 2. ConsequenceDeleteDialog: add environment dependencies table
old_del_aff = '''            aff_files = self.impact.affected_files if self.impact else []

            if aff_files:

                html_body += f"""

                <div style=\'font-weight:700; color:{self.C[\'red\']}; margin-bottom:8px; font-size:12px;\'>

                  🚨 {len(aff_files)} project file{\'s\' if len(aff_files) != 1 else \'\'} depend on this component and will BREAK:

                </div>

                <table width=\'100%\' cellpadding=\'6\' cellspacing=\'0\' style=\'border-collapse:collapse; border:1px solid {self.C[\'border\']};\'>

                  <tr style=\'background:{self.C[\'bg_card\']}; font-size:10px; font-weight:bold; color:{self.C[\'text_muted\']};\'>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>AFFECTED FILE</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>RELATIONSHIP</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>CONSEQUENCE & WHY</th>

                  </tr>

                """

                for f in aff_files:

                    html_body += f"""

                    <tr style=\'border-bottom:1px solid {self.C[\'border\']}; font-size:11px;\'>

                      <td style=\'padding:6px 8px; color:{self.C[\'yellow\']}; font-weight:bold;\'>{f.name}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_sec\']}; font-size:10px;\'>{f.relationship}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_pri\']}; font-size:10px;\'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            else:

                html_body += f"""

                <div style=\'padding:12px; color:{self.C[\'green\']}; font-weight:bold; font-size:12px;\'>

                  ✓ No dependent project files found. It appears safe to remove.

                </div>

                """'''

new_del_aff = '''            aff_files = self.impact.affected_files if self.impact else []

            env_deps = getattr(self.impact, "environment_dependencies", []) if self.impact else []

            if env_deps:

                html_body += f"""

                <div style=\'font-weight:700; color:{self.C[\'yellow\']}; margin-bottom:8px; font-size:12px;\'>

                  ⚠️ {len(env_deps)} Environment Dependenc{\'ies\' if len(env_deps) != 1 else \'y\'} detected:

                </div>

                <table width=\'100%\' cellpadding=\'6\' cellspacing=\'0\' style=\'border-collapse:collapse; border:1px solid {self.C[\'border\']}; margin-bottom:12px;\'>

                  <tr style=\'background:{self.C[\'bg_card\']}; font-size:10px; font-weight:bold; color:{self.C[\'text_muted\']};\'>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>VARIABLE & SOURCE</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>CATEGORY</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>EVIDENCE & WHY IT MATTERS</th>

                  </tr>

                """

                for f in env_deps:

                    html_body += f"""

                    <tr style=\'border-bottom:1px solid {self.C[\'border\']}; font-size:11px;\'>

                      <td style=\'padding:6px 8px; color:{self.C[\'yellow\']}; font-weight:bold;\'>{f.name}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_sec\']}; font-size:10px;\'>{f.relationship}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_pri\']}; font-size:10px;\'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            if aff_files:

                html_body += f"""

                <div style=\'font-weight:700; color:{self.C[\'red\']}; margin-bottom:8px; font-size:12px;\'>

                  🚨 {len(aff_files)} project file{\'s\' if len(aff_files) != 1 else \'\'} depend on this component and will BREAK:

                </div>

                <table width=\'100%\' cellpadding=\'6\' cellspacing=\'0\' style=\'border-collapse:collapse; border:1px solid {self.C[\'border\']};\'>

                  <tr style=\'background:{self.C[\'bg_card\']}; font-size:10px; font-weight:bold; color:{self.C[\'text_muted\']};\'>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>AFFECTED FILE</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>RELATIONSHIP</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>CONSEQUENCE & WHY</th>

                  </tr>

                """

                for f in aff_files:

                    html_body += f"""

                    <tr style=\'border-bottom:1px solid {self.C[\'border\']}; font-size:11px;\'>

                      <td style=\'padding:6px 8px; color:{self.C[\'yellow\']}; font-weight:bold;\'>{f.name}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_sec\']}; font-size:10px;\'>{f.relationship}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_pri\']}; font-size:10px;\'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            elif not env_deps:

                html_body += f"""

                <div style=\'padding:12px; color:{self.C[\'green\']}; font-weight:bold; font-size:12px;\'>

                  ✓ No dependent project files or environment references found. It appears safe to remove.

                </div>

                """'''

if old_del_aff in content:
    content = content.replace(old_del_aff, new_del_aff, 1)
    print("2. ConsequenceDeleteDialog patched")
else:
    print("2. ConsequenceDeleteDialog NOT matched")

# 3. ConsequenceMoveDialog: add environment dependencies table
old_move_aff = '''            aff_files = self.impact.affected_files if self.impact else []

            if aff_files:

                html_body += f"""

                <div style=\'font-weight:700; color:{self.C[\'red\']}; margin-bottom:8px; font-size:12px;\'>

                  🚨 {len(aff_files)} project file{\'s\' if len(aff_files) != 1 else \'\'} depend on this component at its current location and will BREAK:

                </div>

                <table width=\'100%\' cellpadding=\'6\' cellspacing=\'0\' style=\'border-collapse:collapse; border:1px solid {self.C[\'border\']};\'>

                  <tr style=\'background:{self.C[\'bg_card\']}; font-size:10px; font-weight:bold; color:{self.C[\'text_muted\']};\'>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>AFFECTED FILE</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>RELATIONSHIP</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>CONSEQUENCE</th>

                  </tr>

                """

                for f in aff_files:

                    html_body += f"""

                    <tr style=\'border-bottom:1px solid {self.C[\'border\']}; font-size:11px;\'>

                      <td style=\'padding:6px 8px; color:{self.C[\'yellow\']}; font-weight:bold;\'>{f.name}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_sec\']}; font-size:10px;\'>{f.relationship}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_pri\']}; font-size:10px;\'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            else:

                html_body += f"""

                <div style=\'padding:12px; color:{self.C[\'green\']}; font-weight:bold; font-size:12px;\'>

                  ✓ No broken references detected. It appears safe to move.

                </div>

                """'''

new_move_aff = '''            aff_files = self.impact.affected_files if self.impact else []

            env_deps = getattr(self.impact, "environment_dependencies", []) if self.impact else []

            if env_deps:

                html_body += f"""

                <div style=\'font-weight:700; color:{self.C[\'yellow\']}; margin-bottom:8px; font-size:12px;\'>

                  ⚠️ {len(env_deps)} Environment Dependenc{\'ies\' if len(env_deps) != 1 else \'y\'} detected:

                </div>

                <table width=\'100%\' cellpadding=\'6\' cellspacing=\'0\' style=\'border-collapse:collapse; border:1px solid {self.C[\'border\']}; margin-bottom:12px;\'>

                  <tr style=\'background:{self.C[\'bg_card\']}; font-size:10px; font-weight:bold; color:{self.C[\'text_muted\']};\'>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>VARIABLE & SOURCE</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>CATEGORY</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>EVIDENCE & WHY IT MATTERS</th>

                  </tr>

                """

                for f in env_deps:

                    html_body += f"""

                    <tr style=\'border-bottom:1px solid {self.C[\'border\']}; font-size:11px;\'>

                      <td style=\'padding:6px 8px; color:{self.C[\'yellow\']}; font-weight:bold;\'>{f.name}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_sec\']}; font-size:10px;\'>{f.relationship}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_pri\']}; font-size:10px;\'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            if aff_files:

                html_body += f"""

                <div style=\'font-weight:700; color:{self.C[\'red\']}; margin-bottom:8px; font-size:12px;\'>

                  🚨 {len(aff_files)} project file{\'s\' if len(aff_files) != 1 else \'\'} depend on this component at its current location and will BREAK:

                </div>

                <table width=\'100%\' cellpadding=\'6\' cellspacing=\'0\' style=\'border-collapse:collapse; border:1px solid {self.C[\'border\']};\'>

                  <tr style=\'background:{self.C[\'bg_card\']}; font-size:10px; font-weight:bold; color:{self.C[\'text_muted\']};\'>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>AFFECTED FILE</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>RELATIONSHIP</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>CONSEQUENCE</th>

                  </tr>

                """

                for f in aff_files:

                    html_body += f"""

                    <tr style=\'border-bottom:1px solid {self.C[\'border\']}; font-size:11px;\'>

                      <td style=\'padding:6px 8px; color:{self.C[\'yellow\']}; font-weight:bold;\'>{f.name}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_sec\']}; font-size:10px;\'>{f.relationship}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_pri\']}; font-size:10px;\'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            elif not env_deps:

                html_body += f"""

                <div style=\'padding:12px; color:{self.C[\'green\']}; font-weight:bold; font-size:12px;\'>

                  ✓ No broken references detected. It appears safe to move.

                </div>

                """'''

if old_move_aff in content:
    content = content.replace(old_move_aff, new_move_aff, 1)
    print("3. ConsequenceMoveDialog patched")
else:
    print("3. ConsequenceMoveDialog NOT matched")

# 4. ConsequenceRenameDialog: add environment dependencies table
old_rename_aff = '''            if aff_files:

                html_body += f"""

                <div style=\'font-weight:700; color:{self.C[\'red\']}; margin-bottom:8px; font-size:12px;\'>

                  🚨 {len(aff_files)} project file{\'s\' if len(aff_files) != 1 else \'\'} depend on \'{self.src.name}\' and will break if renamed:

                </div>

                <table width=\'100%\' cellpadding=\'6\' cellspacing=\'0\' style=\'border-collapse:collapse; border:1px solid {self.C[\'border\']};\'>

                  <tr style=\'background:{self.C[\'bg_card\']}; font-size:10px; font-weight:bold; color:{self.C[\'text_muted\']};\'>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>AFFECTED FILE</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>RELATIONSHIP</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>CONSEQUENCE</th>

                  </tr>

                """

                for f in aff_files:

                    html_body += f"""

                    <tr style=\'border-bottom:1px solid {self.C[\'border\']}; font-size:11px;\'>

                      <td style=\'padding:6px 8px; color:{self.C[\'yellow\']}; font-weight:bold;\'>{f.name}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_sec\']}; font-size:10px;\'>{f.relationship}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_pri\']}; font-size:10px;\'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            else:

                html_body += f"""

                <div style=\'padding:12px; color:{self.C[\'green\']}; font-weight:bold; font-size:12px;\'>

                  ✓ No dependent files found in this project. It is safe to rename \'{self.src.name}\'.

                </div>

                """'''

new_rename_aff = '''            env_deps = getattr(self.impact, "environment_dependencies", []) if self.impact else []

            if env_deps:

                html_body += f"""

                <div style=\'font-weight:700; color:{self.C[\'yellow\']}; margin-bottom:8px; font-size:12px;\'>

                  ⚠️ {len(env_deps)} Environment Dependenc{\'ies\' if len(env_deps) != 1 else \'y\'} detected:

                </div>

                <table width=\'100%\' cellpadding=\'6\' cellspacing=\'0\' style=\'border-collapse:collapse; border:1px solid {self.C[\'border\']}; margin-bottom:12px;\'>

                  <tr style=\'background:{self.C[\'bg_card\']}; font-size:10px; font-weight:bold; color:{self.C[\'text_muted\']};\'>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>VARIABLE & SOURCE</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>CATEGORY</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>EVIDENCE & WHY IT MATTERS</th>

                  </tr>

                """

                for f in env_deps:

                    html_body += f"""

                    <tr style=\'border-bottom:1px solid {self.C[\'border\']}; font-size:11px;\'>

                      <td style=\'padding:6px 8px; color:{self.C[\'yellow\']}; font-weight:bold;\'>{f.name}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_sec\']}; font-size:10px;\'>{f.relationship}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_pri\']}; font-size:10px;\'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            if aff_files:

                html_body += f"""

                <div style=\'font-weight:700; color:{self.C[\'red\']}; margin-bottom:8px; font-size:12px;\'>

                  🚨 {len(aff_files)} project file{\'s\' if len(aff_files) != 1 else \'\'} depend on \'{self.src.name}\' and will break if renamed:

                </div>

                <table width=\'100%\' cellpadding=\'6\' cellspacing=\'0\' style=\'border-collapse:collapse; border:1px solid {self.C[\'border\']};\'>

                  <tr style=\'background:{self.C[\'bg_card\']}; font-size:10px; font-weight:bold; color:{self.C[\'text_muted\']};\'>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>AFFECTED FILE</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>RELATIONSHIP</th>

                    <th align=\'left\' style=\'padding:5px 8px; border-bottom:1px solid {self.C[\'border\']};\'>CONSEQUENCE</th>

                  </tr>

                """

                for f in aff_files:

                    html_body += f"""

                    <tr style=\'border-bottom:1px solid {self.C[\'border\']}; font-size:11px;\'>

                      <td style=\'padding:6px 8px; color:{self.C[\'yellow\']}; font-weight:bold;\'>{f.name}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_sec\']}; font-size:10px;\'>{f.relationship}</td>

                      <td style=\'padding:6px 8px; color:{self.C[\'text_pri\']}; font-size:10px;\'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            elif not env_deps:

                html_body += f"""

                <div style=\'padding:12px; color:{self.C[\'green\']}; font-weight:bold; font-size:12px;\'>

                  ✓ No dependent files found in this project. It is safe to rename \'{self.src.name}\'.

                </div>

                """'''

if old_rename_aff in content:
    content = content.replace(old_rename_aff, new_rename_aff, 1)
    print("4. ConsequenceRenameDialog patched")
else:
    print("4. ConsequenceRenameDialog NOT matched")

# 5. Fix _find_project_root_for_path to be fast and not treat arbitrary folders as projects
old_find_proj = '''        def _find_project_root_for_path(self, path: Path) -> Path:

            try:

                p = path.resolve()

            except Exception:

                p = path

            if p.is_file():

                p = p.parent

            if len(p.parts) <= 1 or p.parent == p:

                return p

            # Check upward for common project root markers

            markers = {".git", "requirements.txt", "pyproject.toml", "setup.py", "package.json", "Pipfile", "poetry.lock"}

            curr = p

            best_root = p

            found_marker = False

            while len(curr.parts) > 1 and curr.parent != curr:

                for m in markers:

                    if (curr / m).exists():

                        best_root = curr

                        found_marker = True

                        break

                if found_marker:

                    break

                try:

                    if any(curr.glob("*.py")):

                        best_root = curr

                except Exception:

                    pass

                curr = curr.parent

            if not found_marker and p.parent != p and len(p.parent.parts) > 1:

                try:

                    if not list(p.glob("*.py")) and list(p.parent.glob("*.py")):

                        return p.parent

                except Exception:

                    pass

            return best_root'''

new_find_proj = '''        def _find_project_root_for_path(self, path: Path) -> Optional[Path]:

            try:

                p = path.resolve()

            except Exception:

                p = path

            if p.is_file():

                p = p.parent

            if len(p.parts) <= 1 or p.parent == p:

                return None

            # Skip huge system/runtime directories from being auto-detected as code projects

            p_str_lower = str(p).lower()

            skip_terms = ("windows", "program files", "program files (x86)", "appdata", "local settings", "system volume information", "$recycle.bin")

            if any(term in p_str_lower for term in skip_terms):

                return None

            # Check upward for common project root markers

            markers = {".git", "requirements.txt", "pyproject.toml", "setup.py", "package.json", "Pipfile", "poetry.lock"}

            curr = p

            best_root = None

            found_marker = False

            while len(curr.parts) > 1 and curr.parent != curr:

                for m in markers:

                    if (curr / m).exists():

                        best_root = curr

                        found_marker = True

                        break

                if found_marker:

                    break

                try:

                    with os.scandir(curr) as it:

                        for entry in it:

                            if entry.is_file() and entry.name.endswith(".py"):

                                best_root = curr

                                break

                except Exception:

                    pass

                curr = curr.parent

            return best_root'''

if old_find_proj in content:
    content = content.replace(old_find_proj, new_find_proj, 1)
    print("5. _find_project_root_for_path patched")
else:
    print("5. _find_project_root_for_path NOT matched")

# 6. Remove redundant _auto_index_if_needed from file selection changed
old_sel_changed = '''                if self._ai_open:

                    b_stat = self._service.model_manager.get_status()

                    self._ai_ctx.setText(f"Context: {Path(sel_path).name}  |  AI: {b_stat[\'backend\']} ({b_stat[\'accelerator\']})")

                self._auto_index_if_needed(sel_path)

                if self._service.current_graph and Path(sel_path).is_file():'''

new_sel_changed = '''                if self._ai_open:

                    b_stat = self._service.model_manager.get_status()

                    self._ai_ctx.setText(f"Context: {Path(sel_path).name}  |  AI: {b_stat[\'backend\']} ({b_stat[\'accelerator\']})")

                if self._service.current_graph and Path(sel_path).is_file():'''

if old_sel_changed in content:
    content = content.replace(old_sel_changed, new_sel_changed, 1)
    print("6. _on_file_selection_changed patched")
else:
    print("6. _on_file_selection_changed NOT matched")

# 7. In _start_scan: never block UI with wait(1000)
old_start_scan = '''            if hasattr(self, "_scan_worker") and self._scan_worker is not None and self._scan_worker.isRunning():

                self._scan_worker.wait(1000)

                if self._scan_worker.isRunning():

                    return'''

new_start_scan = '''            if hasattr(self, "_scan_worker") and self._scan_worker is not None and self._scan_worker.isRunning():

                if hasattr(self._scan_worker, "path") and str(self._scan_worker.path) == str(p):

                    return

                try:

                    self._scan_worker.finished.disconnect()

                    self._scan_worker.progress.disconnect()

                except Exception:

                    pass'''

if old_start_scan in content:
    content = content.replace(old_start_scan, new_start_scan, 1)
    print("7. _start_scan non-blocking patched")
else:
    print("7. _start_scan NOT matched")

# 8. Update _render_sim_result to show environment dependencies card
old_render_sim = '''            no_impact = ""

            if not impact.affected_files and impact.analysis_complete:

                no_impact = f"""

                <div style=\'color:{C[\'green\']}; padding:10px; background:{C[\'bg_card\']};

                            border-radius:5px; border:1px solid {C[\'border\']}; margin-bottom:10px;\'>

                  ✓ No confirmed dependent files found.<br>

                  <span style=\'font-size:10px; color:{C[\'text_muted\']};\'>This change appears safe.</span>

                </div>"""'''

new_render_sim = '''            env_deps = getattr(impact, "environment_dependencies", [])

            env_section_html = ""

            if env_deps:

                env_rows = ""

                for i, f in enumerate(env_deps, 1):

                    env_rows += f"""

                    <tr style=\'border-bottom:1px solid {C[\'border\']};\'>

                      <td style=\'padding:7px 10px; color:{C[\'yellow\']};\'>{i}. {f.name}</td>

                      <td style=\'padding:7px 10px; color:{C[\'text_sec\']}; font-size:10px;\'>{f.relationship}</td>

                      <td style=\'padding:7px 10px; color:{C[\'green\']}; font-size:10px;\'>{f.confidence.value}</td>

                      <td style=\'padding:7px 10px; color:{C[\'text_muted\']}; font-size:10px;\'>{f.evidence_summary}</td>

                    </tr>"""

                env_section_html = f"""

                <div style=\'background:{C[\'bg_card\']}; border:1px solid {C[\'border\']};

                            border-radius:6px; margin-bottom:10px;\'>

                  <div style=\'padding:7px 10px; border-bottom:1px solid {C[\'border\']};\'>

                    <span style=\'color:{C[\'text_muted\']}; font-size:9px; font-weight:bold; letter-spacing:1px;\'>

                      ENVIRONMENT DEPENDENCIES

                    </span>

                    &nbsp;

                    <span style=\'color:{C[\'yellow\']}; font-size:11px; font-weight:bold;\'>

                      {len(env_deps)} reference{\'s\' if len(env_deps)!=1 else \'\'}

                    </span>

                  </div>

                  <table style=\'width:100%; border-collapse:collapse;\'>

                    <tr style=\'background:{C[\'bg_input\']};\'>

                      <th style=\'padding:5px 10px; text-align:left; color:{C[\'text_muted\']}; font-size:9px; font-weight:bold;\'>VARIABLE & SOURCE</th>

                      <th style=\'padding:5px 10px; text-align:left; color:{C[\'text_muted\']}; font-size:9px; font-weight:bold;\'>CATEGORY</th>

                      <th style=\'padding:5px 10px; text-align:left; color:{C[\'text_muted\']}; font-size:9px; font-weight:bold;\'>CONFIDENCE</th>

                      <th style=\'padding:5px 10px; text-align:left; color:{C[\'text_muted\']}; font-size:9px; font-weight:bold;\'>EVIDENCE & WHY</th>

                    </tr>

                    {env_rows}

                  </table>

                </div>"""

            no_impact = ""

            has_any_deps = bool(impact.affected_files or env_deps)

            if not has_any_deps and impact.analysis_complete:

                no_impact = f"""

                <div style=\'color:{C[\'green\']}; padding:10px; background:{C[\'bg_card\']};

                            border-radius:5px; border:1px solid {C[\'border\']}; margin-bottom:10px;\'>

                  ✓ No confirmed dependent files or environment references found.<br>

                  <span style=\'font-size:10px; color:{C[\'text_muted\']};\'>This change appears safe.</span>

                </div>"""'''

if old_render_sim in content:
    content = content.replace(old_render_sim, new_render_sim, 1)
    # Also add {env_section_html} into the template
    content = content.replace(
        "              {no_impact if not impact.affected_files else \"\"}",
        "              {env_section_html}\n\n              {no_impact if not has_any_deps else \"\"}",
        1
    )
    print("8. _render_sim_result patched")
else:
    print("8. _render_sim_result NOT matched")

# 9. _detect_project_root and _get_consequence_analyzer
old_detect = '''        def _detect_project_root(self, path_str: str) -> Optional[Path]:

            try:

                p = Path(path_str).resolve()

                start = p if p.is_dir() else p.parent

                for ancestor in [start] + list(start.parents):

                    # Never treat filesystem drive root as project root

                    if len(ancestor.parts) <= 1 or ancestor.parent == ancestor:

                        continue

                    if list(ancestor.glob("*.py")) or (ancestor / "requirements.txt").exists() or (ancestor / "setup.py").exists() or (ancestor / ".git").exists():

                        return ancestor

                if start.exists() and start.is_dir() and len(start.parts) > 1 and start.parent != start:

                    return start

            except Exception:

                pass

            return None'''

new_detect = '''        def _detect_project_root(self, path_str: str) -> Optional[Path]:

            try:

                p = Path(path_str).resolve()

                start = p if p.is_dir() else p.parent

                skip_terms = ("windows", "program files", "program files (x86)", "appdata", "local settings", "system volume information", "$recycle.bin")

                if any(term in str(start).lower() for term in skip_terms):

                    return None

                for ancestor in [start] + list(start.parents):

                    if len(ancestor.parts) <= 1 or ancestor.parent == ancestor:

                        continue

                    if (ancestor / ".git").exists() or (ancestor / "requirements.txt").exists() or (ancestor / "pyproject.toml").exists() or (ancestor / "setup.py").exists():

                        return ancestor

                try:

                    with os.scandir(start) as it:

                        for entry in it:

                            if entry.is_file() and entry.name.endswith(".py"):

                                return start

                except Exception:

                    pass

            except Exception:

                pass

            return None'''

if old_detect in content:
    content = content.replace(old_detect, new_detect, 1)
    print("9. _detect_project_root patched")
else:
    print("9. _detect_project_root NOT matched")

# 10. In _get_consequence_analyzer: avoid freezing UI with heavy synchronous build
old_analyzer_call = '''                    proj_cand = self._detect_project_root(target)

                    if proj_cand:

                        builder = GraphBuilder(proj_cand)

                        graph = builder.build()

                        self._service.current_graph = graph

                        self._service.project_root = proj_cand

                        return ConsequenceAnalyzer(graph)'''

new_analyzer_call = '''                    proj_cand = self._detect_project_root(target)

                    if proj_cand:

                        if self._service.project_root and str(self._service.project_root) == str(proj_cand) and self._service.current_graph:

                            return ConsequenceAnalyzer(self._service.current_graph)

                        # Return consequence analyzer for state graph, auto-indexing in background

                        from app.graph.builder import StateGraph

                        return ConsequenceAnalyzer(self._service.current_graph or StateGraph(proj_cand))'''

if old_analyzer_call in content:
    content = content.replace(old_analyzer_call, new_analyzer_call, 1)
    print("10. _get_consequence_analyzer patched")
else:
    print("10. _get_consequence_analyzer NOT matched")

with open("app/main.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patching complete!")
