"""Fault-injection runner (#54): offline (fake LLM, mock MCP server; see conftest)."""

import pytest

from eval.faults import CASES, run_case

BY_ID = {c.id: c for c in CASES}


@pytest.mark.parametrize("case_id", sorted(BY_ID))
def test_fault_case_triggers_and_passes_offline(case_id):
    r = run_case(BY_ID[case_id])
    assert r["passed"], r["failures"]


def test_untriggered_fault_is_reported_as_failure():
    from eval.faults import FaultCase, on
    case = FaultCase("FX", "never triggered", "Recommend a card game.", on("web.search", lambda a, o: None))
    r = run_case(case)  # catalog-only request: web.search is never called
    assert not r["passed"] and "never triggered" in r["failures"][0]
