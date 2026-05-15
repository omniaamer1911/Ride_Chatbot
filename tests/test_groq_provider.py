from app.chatbot.providers.groq_provider import _parse_failed_generation


def test_parse_failed_generation_maadi():
    text = '<function=resolve_location{"query": "المعادي"}</function>\n'
    tcs = _parse_failed_generation(text)
    assert len(tcs) == 1
    assert tcs[0].name == "resolve_location"
    assert '"query": "المعادي"' in tcs[0].arguments


def test_parse_failed_generation_invalid_json_skipped():
    text = "<function=bad_tool{not json}</function>"
    assert _parse_failed_generation(text) == []
