import ast

with open("app/main.py", "r", encoding="utf-8-sig") as f:
    source = f.read()

tree = ast.parse(source)

# Find PreViewWindow class
preview_window = None
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "PreViewWindow":
        preview_window = node
        break

pw_methods = set()
for n in preview_window.body:
    if isinstance(n, ast.FunctionDef):
        pw_methods.add(n.name)

# Collect all self.<method> callbacks connected to signals inside PreViewWindow
connections = []
for node in ast.walk(preview_window):
    if isinstance(node, ast.Call):
        # look for .connect(self.xxx) or similar
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "connect":
            if node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "self":
                    connections.append((node.lineno, arg.attr))

print(f"Total direct self.<callback> signal connections found: {len(connections)}")
missing = []
for lineno, method in connections:
    if method not in pw_methods:
        missing.append((lineno, method))
        print(f"  Line {lineno}: MISSING method 'self.{method}'")
    else:
        # print(f"  Line {lineno}: self.{method} (OK)")
        pass

if not missing:
    print("ALL direct self.<callback> signal connections EXIST!")
else:
    print(f"FOUND {len(missing)} MISSING METHODS!")
