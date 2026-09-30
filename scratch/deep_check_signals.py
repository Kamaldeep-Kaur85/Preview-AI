import ast

with open("app/main.py", "r", encoding="utf-8-sig") as f:
    source = f.read()

tree = ast.parse(source)

preview_window = None
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "PreViewWindow":
        preview_window = node
        break

# Collect all attributes & methods defined in PreViewWindow
defined_attrs = set()
for n in preview_window.body:
    if isinstance(n, ast.FunctionDef):
        defined_attrs.add(n.name)
    elif isinstance(n, ast.Assign):
        for t in n.targets:
            if isinstance(t, ast.Name):
                defined_attrs.add(t.id)

# Also collect all self.<x> assignments inside methods of PreViewWindow
for node in ast.walk(preview_window):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                defined_attrs.add(t.attr)

print(f"Total attributes/methods on PreViewWindow: {len(defined_attrs)}")

# Now find all .connect(...) calls anywhere inside PreViewWindow (excluding inner classes)
# Check every method called on self
missing_calls = []

# Exclude inner classes from self check
inner_class_names = [n.name for n in preview_window.body if isinstance(n, ast.ClassDef)]
print(f"Inner classes in PreViewWindow: {inner_class_names}")

class ConnectVisitor(ast.NodeVisitor):
    def __init__(self):
        self.in_inner_class = False

    def visit_ClassDef(self, node):
        if node.name != "PreViewWindow":
            # skip inner class
            return
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "connect":
            # inspect what is being connected
            for arg in node.args:
                # if it's self.xxx
                if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "self":
                    if arg.attr not in defined_attrs:
                        missing_calls.append((node.lineno, f"self.{arg.attr}"))
                # if it's lambda: self.xxx(...)
                elif isinstance(arg, ast.Lambda):
                    for sub in ast.walk(arg.body):
                        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                            if isinstance(sub.func.value, ast.Name) and sub.func.value.id == "self":
                                if sub.func.attr not in defined_attrs:
                                    missing_calls.append((node.lineno, f"lambda: self.{sub.func.attr}"))
        self.generic_visit(node)

visitor = ConnectVisitor()
visitor.visit(preview_window)

print(f"Missing connections in PreViewWindow: {missing_calls}")
