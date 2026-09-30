3131:             if p.is_dir():
3132:                 self._navigate_to(path)
3133:             elif p.is_file():
3134:                 self._open_file(path)
3135: 
3136:         # ── Context menu ──────────────────────────────────────────────────
3137:         # ── Context menu ──────────────────────────────────────────────────
3138:         def _show_context_menu(self, pos):
3139:             index = self._file_view.indexAt(pos)
3140:             menu = QMenu(self)
3141: 
3142:             def act(label, slot, shortcut=None, enabled=True):
3143:                 a = QAction(label, menu)
3144:                 a.setEnabled(enabled)
3145:                 a.triggered.connect(slot)
3146:                 if shortcut:
3147:                     a.setShortcut(shortcut)
3148:                 menu.addAction(a)
3149:                 return a
3150: 
3151:             has_clip = bool(getattr(self, "_clipboard_path", None) and Path(self._clipboard_path).exists())
3152: 
3153:             if index.isValid():
3154:                 path = self._fs_model.filePath(index)
3155:                 p = Path(path)
3156: 
3157:                 act("📂  Open\tEnter", lambda: self._open_file(path))
3158:                 act("🪟  Reveal in Windows Explorer", lambda: self._reveal_in_os_explorer(path))
3159:                 menu.addSeparator()
3160: 
3161:                 act("✂️  Cut\tCtrl+X", lambda: self._cut_selection(path))
3162:                 act("📋  Copy\tCtrl+C", lambda: self._copy_selection(path))
3163:                 act("📥  Paste\tCtrl+V", self._paste_selection, enabled=has_clip)
3164:                 act("✏️  Rename…\tF2", lambda: self._rename_file(path))
3165:                 act("🗑️  Delete…\tDel", lambda: self._delete_file(path))
3166:                 menu.addSeparator()
3167: 
3168:                 act("📦  Move to…", lambda: self._move_to_dialog(path))
3169:                 act("📂  Copy to…", lambda: self._copy_to_dialog(path))
3170:                 act("🔗  Copy as Path\tCtrl+Shift+C", lambda: self._copy_as_path(path))
3171:                 menu.addSeparator()
3172: 
3173:                 # New Submenu
3174:                 new_sub = menu.addMenu("➕  New")
3175:                 a_fld = QAction("📁  Folder\tCtrl+Shift+N", new_sub)
3176:                 a_fld.triggered.connect(self._new_folder)
3177:                 new_sub.addAction(a_fld)
3178: 
3179:                 a_doc = QAction("📄  Text Document", new_sub)
3180:                 a_doc.triggered.connect(lambda: self._new_file("New Document.txt"))
3181:                 new_sub.addAction(a_doc)
3182: 
3183:                 a_py = QAction("🐍  Python Script", new_sub)
3184:                 a_py.triggered.connect(lambda: self._new_file("script.py"))
3185:                 new_sub.addAction(a_py)
3186: 
3187:                 a_cfg = QAction("⚙️  Config File (.json)", new_sub)
3188:                 a_cfg.triggered.connect(lambda: self._new_file("config.json"))
3189:                 new_sub.addAction(a_cfg)
3190:                 menu.addSeparator()
3191: 
3192:                 # PreView AI Power Actions
3193:                 if p.is_dir():
3194:                     act("⚡  Index as Project", lambda: self._start_scan(path))
3195:                 act("⚡  Simulate Impact", lambda: self._show_impact_for(path))
3196:                 act("📊  Show in Dependency Graph", lambda: self._show_deps_for(path))
3197:                 act("✨  Ask PreView AI", lambda: self._ask_ai_about(path))
3198:                 menu.addSeparator()
3199: 
3200:                 act("ℹ️  Properties\tAlt+Enter", lambda: self._show_properties(path))
3201:             else:
3202:                 # Clicked on blank space in current directory
3203:                 cur_dir = str(self._get_current_directory())
3204: 
3205:                 new_sub = menu.addMenu("➕  New")
3206:                 a_fld = QAction("📁  Folder\tCtrl+Shift+N", new_sub)
3207:                 a_fld.triggered.connect(self._new_folder)
3208:                 new_sub.addAction(a_fld)
3209: 
3210:                 a_doc = QAction("📄  Text Document", new_sub)
3211:                 a_doc.triggered.connect(lambda: self._new_file("New Document.txt"))
3212:                 new_sub.addAction(a_doc)
3213: 
3214:                 a_py = QAction("🐍  Python Script", new_sub)
3215:                 a_py.triggered.connect(lambda: self._new_file("script.py"))
3216:                 new_sub.addAction(a_py)
3217: 
3218:                 a_cfg = QAction("⚙️  Config File (.json)", new_sub)
3219:                 a_cfg.triggered.connect(lambda: self._new_file("config.json"))
3220:                 new_sub.addAction(a_cfg)
3221:                 menu.addSeparator()
3222: 
3223:                 act("📥  Paste\tCtrl+V", self._paste_selection, enabled=has_clip)
3224:                 menu.addSeparator()
3225: 
3226:                 act("⚡  Index Current Folder as Project", self._index_current_folder)
3227:                 act("🔄  Refresh\tF5", self._refresh)
3228:                 act("🪟  Open in Windows Explorer", lambda: self._reveal_in_os_explorer(cur_dir))
3229:                 menu.addSeparator()
3230:                 act("ℹ️  Folder Properties\tAlt+Enter", lambda: self._show_properties(cur_dir))
3231: 
3232:             menu.exec(QCursor.pos())
3233: 
3234:         # ── Scanning ──────────────────────────────────────────────────────
3235:         def _start_scan(self, path_str: str):
3236:             p = Path(path_str).resolve()
3237:             if len(p.parts) <= 1 or p.parent == p:
3238:                 QMessageBox.warning(self, "Invalid Project Scope", "Cannot index an entire filesystem drive root as a project. Please select a specific project directory.")
3239:                 return
3240:             self._sim_btn.setEnabled(False)
3241:             self._exec_btn.setEnabled(False)
3242:             self._progress.show()
3243:             self._idx_status.setText("Indexing…")
3244:             self._log_stream(f"Indexing project: {path_str}")
3245:             self._status.showMessage(f"Indexing {path_str}…")
3246: 
3247:             self._scan_worker = ScanWorker(self._service, path_str)
3248:             self._scan_worker.progress.connect(lambda m: self._log_stream(m))
3249:             self._scan_worker.finished.connect(self._on_scan_done)
3250:             self._scan_worker.start()
3251: 
3252:         def _on_scan_done(self, ok: bool, msg: str):
3253:             self._progress.hide()
3254:             self._sim_btn.setEnabled(True)
3255:             if ok and self._service.current_graph:
3256:                 stats = self._service.get_graph_stats()
3257:                 self._stats_label.setText(
3258:                     f"Files: {stats['nodes']}   Relations: {stats['edges']}"
3259:                 )
3260:                 self._idx_status.setText(
3261:                     f"✓ Indexed  ({stats['nodes']} files, {stats['edges']} relations)"
3262:                 )
3263:                 self._log_stream(
3264:                     f"✓ Project indexed — {stats['nodes']} files, {stats['edges']} relationships"
3265:                 )
3266:                 self._status.showMessage(
3267:                     f"{self._service.project_root.name} — {stats['nodes']} files, {stats['edges']} relations"
3268:                 )
3269:                 self._update_graph_tab()
3270:                 self._populate_left_tree()
3271:                 # Update address bar badge
3272:                 if hasattr(self, "_current_dir") and self._current_dir:
3273:                     self._update_index_badge(self._current_dir)
3274:                 # Auto-start watcher
3275:                 if not self._service.watcher_active:
3276:                     self._start_watcher()
3277:                 # Trigger impact lookup for currently selected file now that index is ready
3278:                 if self._selected_path and Path(self._selected_path).is_file():
3279:                     self._start_impact_lookup(self._selected_path)
3280: 
3281:                 # Resume pending simulation if requested
3282:                 if hasattr(self, "_pending_sim_intent") and self._pending_sim_intent:
3283:                     pending = self._pending_sim_intent
3284:                     self._pending_sim_intent = None
3285:                     self._intent_edit.setText(pending)
3286:                     self._run_simulation()
3287:             else:
3288:                 self._idx_status.setText("⚠ Indexing failed")
3289:                 self._log_stream(f"ERROR: {msg}")
3290:                 self._status.showMessage(f"Scan failed: {msg}")
3291: 
3292:         # ── Watcher ───────────────────────────────────────────────────────
3293:         def _start_watcher(self):
3294:             def on_change(event: ChangeEvent, impact: ImpactResult):
3295:                 self.fs_change_signal.emit(event, impact)
3296: 
3297:             ok = self._service.start_watcher(on_change)
3298:             if ok:
3299:                 self._monitor_dot.setText("⬤ MONITORING ON")
3300:                 self._monitor_dot.setStyleSheet(
