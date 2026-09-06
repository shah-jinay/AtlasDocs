from app.rag.generation import MockGenerationProvider, _parse_structured_response


def test_mock_provider_answers_from_top_source():
    context = (
        "[SOURCE S1]\nfilename: a.pdf\npage: 1\nchunk_id: x\ntext: The retention period is 90 days.\n\n"
        "[SOURCE S2]\nfilename: b.pdf\npage: 2\nchunk_id: y\ntext: Unrelated passage.\n"
    )
    result = MockGenerationProvider().generate(system_prompt="", user_message=f"{context}\n\nQuestion: q")
    assert "S1" in result.answer
    assert result.citations[0].source_id == "S1"
    assert not result.insufficient_evidence


def test_mock_provider_abstains_with_no_sources():
    result = MockGenerationProvider().generate(system_prompt="", user_message="Question: q")
    assert result.insufficient_evidence
    assert result.citations == []


def test_parse_structured_response_extracts_json():
    text = 'Here you go: {"answer": "The answer.", "citations": [{"source_id": "S1", "claim": "c"}]}'
    result = _parse_structured_response(text)
    assert result.answer == "The answer."
    assert result.citations[0].source_id == "S1"


def test_parse_structured_response_falls_back_on_malformed_json():
    result = _parse_structured_response("not json at all")
    assert result.citations == []
    assert result.answer == "not json at all"
