# fix_parse_post_range.py
import re

file_path = r"c:\Users\Rajendra Pal\Downloads\Save-Restricted-Content\Save-Restricted-Content\Rajendra\start.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_pattern = r'def parse_post_range\(text: str\):.*?return link, start_id, end_id'

new_function = '''def parse_post_range(text: str):
    # Match formats: https://t.me/channel/123 or https://t.me/channel 123
    # Also: https://t.me/c/12345/678, https://t.me/b/bot/901
    # And ranges: 123-456 or 123 5
    match = re.search(
        r"https://t\\.me/(?:" 
        r"(?:c|b)/[^/\\s]+/(\\d+)|"      # private or bot: c/id/msgid or b/id/msgid
        r"([^/\\s]+)/(\\d+)|"            # public: channel/msgid
        r"([^/\\s]+)\\s+(\\d+)"           # public with space: channel msgid
        r")(?:\\s*-\\s*(\\d+))?(?:\\?single)?(?:\\s+(\\d+))?",
        text
    )
    if not match:
        return None, None, None

    start_id_str = match.group(1) or match.group(3) or match.group(5)
    start_id = int(start_id_str) if start_id_str else None

    if match.group(1):  # private/bot format
        link_prefix = text[:text.rfind('/')]
        link = f"{link_prefix}/{start_id}"
    else:
        channel = match.group(2) or match.group(4)
        link = f"https://t.me/{channel}/{start_id}"

    if match.group(6):  # range format: 123-456
        end_id = int(match.group(6))
    elif match.group(7):  # count format: 123 5
        count = int(match.group(7))
        end_id = start_id + count - 1 if count > 0 else start_id
    else:
        end_id = start_id

    return link, start_id, end_id'''

new_content = re.sub(old_pattern, new_function, content, flags=re.DOTALL)

if new_content == content:
    print("No occurrence of `parse_post_range` matched — no changes written.")
else:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("✓ Fix applied successfully!")