
import glob, re, os
base = r"D:\ToolCaches\npm\node_modules\@minimax-ai\code"
keys = ["MINIMAX_HOME", "MCODE_HOME", "MINIMAX_CONFIG", "mcp.json"]
for p in glob.glob(base + r"\chunks\*.js") + glob.glob(base + r"\*.js"):
    s = open(p, encoding="utf-8", errors="ignore").read()
    for k in keys:
        if k in s:
            i = s.find(k)
            print("==", k, "in", os.path.basename(p))
            print(s[max(0,i-200):i+300].replace("\n"," "))
            break
