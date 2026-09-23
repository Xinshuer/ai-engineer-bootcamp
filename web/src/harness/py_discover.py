# Test runner for "testwrite" exercises. Runs after the learner's test file (main.py),
# with the code under test loaded first as setup: calls every test_* function once,
# in the order written. A test fails when it raises (usually an AssertionError).
_cc_found = [(_n, _f) for _n, _f in list(globals().items()) if _n.startswith("test_") and callable(_f)]
if not _cc_found:
    expect_true(_tr("没有找到以 test_ 开头的测试函数", "No test function starting with test_ was found"), lambda: False)
for _cc_n, _cc_f in _cc_found:
    expect_true(_cc_n, lambda _cc_f=_cc_f: (_cc_f(), True)[1])
