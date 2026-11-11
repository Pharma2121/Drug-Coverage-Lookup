#!/bin/sh
# Rebuild the lookup from the files in ../sources, then reconcile the result against them.
set -e
cd "$(dirname "$0")"
python3 stage1_partd.py
python3 stage2_drugs.py
python3 stage3_medical.py
python3 stage4_plans.py
python3 stage5_page.py
python3 verify_build.py
