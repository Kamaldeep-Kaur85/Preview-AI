import ast

with open("app/main.py", "r", encoding="utf-8-sig") as f:
    tree = ast.parse(f.read())

preview_window_methods = set()
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "PreViewWindow":
        for n in node.body:
            if isinstance(n, ast.FunctionDef):
                preview_window_methods.add(n.name)

required_methods = [
    "_open_file",
    "_reveal_in_os_explorer",
    "_cut_selection",
    "_copy_selection",
    "_paste_selection",
    "_rename_file",
    "_delete_file",
    "_move_to_dialog",
    "_copy_to_dialog",
    "_copy_as_path",
    "_new_folder",
    "_new_file",
    "_start_scan",
    "_show_impact_for",
    "_show_deps_for",
    "_ask_ai_about",
    "_show_properties",
    "_get_current_directory",
    "_index_current_folder",
    "_refresh"
]

print(f"Total methods in PreViewWindow: {len(preview_window_methods)}")
for m in required_methods:
    exists = m in preview_window_methods
    print(f"  {m}: {'EXISTS' if exists else 'MISSING'}")
