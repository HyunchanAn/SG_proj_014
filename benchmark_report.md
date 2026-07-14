# Benchmark & E2E Test Report

- **Repository**: SG_proj_014
- **Date**: 2026-07-14 22:45:16

## 1. E2E Testing Summary
❌ **Status**: FAILED

### Test Logs (Snippet)
```text
plugins: anyio-4.12.1, cov-7.1.0, hypothesis-6.155.7, hydra-core-1.3.2, respx-0.23.1
collected 2 items / 2 errors

==================================== ERRORS ====================================
_____________________ ERROR collecting tests/test_main.py ______________________
ImportError while importing test module '/Users/hyunchanan/Documents/GitHub/SG_proj_014/tests/test_main.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Caskroom/miniconda/base/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_main.py:6: in <module>
    from src.schemas import ProcessabilityResult, MatchingResponse, VerificationResult
E   ImportError: cannot import name 'MatchingResponse' from 'src.schemas' (/Users/hyunchanan/Documents/GitHub/SG_proj_011/src/schemas.py)
_______ ERROR collecting cross_module_tests/test_schema_domain_rules.py ________
ImportError while importing test module '/Users/hyunchanan/Documents/GitHub/SG_proj_014/cross_module_tests/test_schema_domain_rules.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/homebrew/Caskroom/miniconda/base/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
cross_module_tests/test_schema_domain_rules.py:3: in <module>
    from src.schemas import Step2Target, Step1Metrics, OrchestrationRequest
E   ImportError: cannot import name 'Step2Target' from 'src.schemas' (/Users/hyunchanan/Documents/GitHub/SG_proj_011/src/schemas.py)
=========================== short test summary info ============================
ERROR tests/test_main.py
ERROR cross_module_tests/test_schema_domain_rules.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
============================== 2 errors in 2.39s ===============================

```

## 2. Models Detected
- No pre-trained weights or models detected in this repository.
