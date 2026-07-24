# RaceMap Task 11 Completion Design

## Goal

Complete Task 11 of the RaceMap integration plan: remove stale participant devices safely, finalize project metadata and tooling, and verify the integration in WSL because Home Assistant's test runner requires the POSIX `fcntl` module.

## Device Cleanup

The sensor platform owns stale-device cleanup because participant sensors and device trackers share one participant device. On coordinator updates it will:

- derive the selected participant device identifiers for the current event;
- inspect only devices attached to the current config entry;
- ignore the event device and identifiers for other events;
- remove the current config entry association from a deselected participant device rather than force-deleting the device.

Home Assistant will remove the device once it has no remaining associations. The tracker platform continues to listen for coordinator updates to create trackers for newly selected participants but does not duplicate cleanup.

## Tests

The dynamic-device test sets up two selected participants, then deselects one through entry options. It verifies that the retained participant and event device remain, the deselected participant device is gone, and an unrelated RaceMap device is untouched. The test contains no debugging output or filesystem writes.

## Tooling And Verification

`requirements_test.txt`, `pyproject.toml`, `hacs.json`, and `README.md` are committed as Task 11 deliverables. The configured Ruff and mypy policies are made green without weakening their declared strictness. Tests, coverage, linting, formatting, and type checking run in WSL, where the Home Assistant test stack can import `fcntl`.

## Completion Criteria

- No `print()` or temporary debugging code remains.
- Dynamic cleanup has regression coverage.
- Ruff check and format check pass.
- Mypy passes for `custom_components/racemap`.
- Full pytest and coverage pass in WSL, with at least 95% coverage for each integration module.
