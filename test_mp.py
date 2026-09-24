import sys
import os
import hashlib
import multiprocessing as mp

def _get_app_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))

def worker():
    d = _get_app_base_dir()
    with open('mp_hash_output.txt', 'w') as f:
        f.write(f"base_dir: {d}\n")
        f.write(f"hash: {hashlib.sha256(d.encode()).hexdigest()[:12]}\n")
        f.write(f"executable: {sys.executable}\n")
        f.write(f"frozen: {getattr(sys, 'frozen', False)}\n")

if __name__ == '__main__':
    mp.freeze_support()
    mp.set_start_method('spawn', force=True)
    p = mp.Process(target=worker)
    p.start()
    p.join()
