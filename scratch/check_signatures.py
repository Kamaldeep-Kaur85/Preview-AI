import ast

with open("app/main.py", "r", encoding="utf-8-sig") as f:
    tree = ast.parse(f.read())

preview_window = None
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "PreViewWindow":
        preview_window = node
        break

check_funcs = [
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
    "_refresh",
]

for n in preview_window.body:
    if isinstance(n, ast.FunctionDef) and n.name in check_funcs:
        args = [a.arg for a in n.args.args]
        defaults = [ast.unparse(d) for d in n.args.defaults]
        print(f"def {n.name}({', '.join(args)}): defaults={defaults}")
