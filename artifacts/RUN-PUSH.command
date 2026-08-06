#!/bin/bash
# Double-click or: open artifacts/RUN-PUSH.command
cd /Users/dex/.grok/plugins/ai-film-grok || exit 1
/bin/bash /Users/dex/.cache/dex-sched/aifilm-push-once.sh
echo "---"
head -20 /tmp/aifilm-push-result.txt
echo "Press Enter to close"
read -r _
