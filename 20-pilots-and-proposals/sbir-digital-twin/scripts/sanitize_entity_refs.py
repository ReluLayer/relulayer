import os
import re

workspace = os.path.expanduser("~/projects/sbir-digital-twin")
targets = ["proposal", "ppa"]

# Text replacements to enforce exact legal structure
replacements = [
    # Refactor standalone Pacific AI Lab references to clarify entity status
    (
        r"operated primarily at the Pacific AI Lab, operated by Atelier Logic Group LLC",
        r"executed at the physical engineering facility of Atelier Logic Group LLC dba ReluLayer™, utilizing the Pacific AI Lab workstation environment"
    ),
    (
        r"Pacific AI Lab / Atelier Logic Group LLC",
        r"Atelier Logic Group LLC dba ReluLayer™ (Pacific AI Lab Workstation Environment)"
    ),
    # Ensure physical vs mailing address context is exact
    (
        r"32 Normandy Drive",
        r"32 Normandy Dr."
    )
]

for target_dir in targets:
    dir_path = os.path.join(workspace, target_dir)
    if not os.path.exists(dir_path):
        continue
    for root, _, files in os.walk(dir_path):
        for file in files:
            if file.endswith((".tex", ".json", ".md", ".py")):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                new_content = content
                for pattern, repl in replacements:
                    new_content = re.sub(pattern, repl, new_content)

                if new_content != content:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"[UPDATED] {filepath}")

print("[STATUS] Step 1 Complete: All source files sanitized.")
