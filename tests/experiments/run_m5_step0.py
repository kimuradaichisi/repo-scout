"""Run M5's model-free checks and report PASS/FAIL. No model calls."""

from m5_step0_checks import ALL_CHECKS


def main() -> int:
    results = [check() for check in ALL_CHECKS]
    for result in results:
        print(f"[{'PASS' if result.passed else 'FAIL'}] {result.name}")
        print(f"      {result.detail}")
    all_passed = all(result.passed for result in results)
    print(f"\n{sum(r.passed for r in results)}/{len(results)} passed")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
