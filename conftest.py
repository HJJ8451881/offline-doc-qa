"""空的根層 conftest.py：讓 pytest 把 repo root 加進 sys.path，
這樣 tests/ 底下的測試才能用 `from app import ...` 匯入套件。
"""
