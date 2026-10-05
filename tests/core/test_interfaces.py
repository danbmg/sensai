from sensai.core.interfaces import Event, GuardResult, ToolResult


def test_guard_result_defaults():
    result = GuardResult("Que prend [PATIENT_1] ?")
    assert not result.blocked
    assert result.reason == ""
    assert result.mapping == {}


def test_guard_result_mapping_not_shared_between_instances():
    a, b = GuardResult("a"), GuardResult("b")
    a.mapping["[PATIENT_1]"] = "Mme Dupont"
    assert b.mapping == {}


def test_tool_result_and_event_defaults():
    assert ToolResult("ok").is_error is False
    assert Event("done").data is None
