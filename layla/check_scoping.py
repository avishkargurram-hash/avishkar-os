import sys
sys.path.insert(0, '/opt/layla')
import layla_service as L
import layla_interpreter as I

msg = 'Run a bash command to check system uptime on tv-mum-01'
tools = L._select_scoped_tools(msg)
names = [t['function']['name'] for t in tools]
print("Message:", msg)
print("Scoped tool count:", len(tools))
print("Contains run_terminal_command?", 'run_terminal_command' in names)
print("Keywords in norm:")
norm = msg.lower()
for kw in I.KEYWORDS:
    if kw in norm:
        print("  Matched keyword:", kw)

# Check intent gate
print("Question tool match?", L._question_tool_match(msg))
