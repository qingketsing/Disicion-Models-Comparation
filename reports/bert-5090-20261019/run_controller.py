"""Run the unchanged experiment CLI with a recorded 1 ms Windows timer request."""
import ctypes
import os
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
os.chdir(root)
sys.path.insert(0, str(root))
started_timer = False
if os.name == "nt":
    started_timer = ctypes.windll.winmm.timeBeginPeriod(1) == 0
    if not started_timer:
        raise RuntimeError("Windows 1 ms timer request failed")
try:
    sys.argv = ["scripts.bert_experiment", *sys.argv[1:]]
    runpy.run_module("scripts.bert_experiment", run_name="__main__")
finally:
    if started_timer:
        ctypes.windll.winmm.timeEndPeriod(1)
