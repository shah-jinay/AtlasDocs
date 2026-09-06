from app.rag.embeddings import MockEmbeddingProvider


def test_mock_embedding_dimension_matches_config():
    provider = MockEmbeddingProvider(dimension=384)
    vector = provider.embed_query("hello world")
    assert len(vector) == 384


def test_mock_embedding_is_deterministic():
    provider = MockEmbeddingProvider(dimension=384)
    assert provider.embed_query("same text") == provider.embed_query("same text")


def test_mock_embedding_differs_for_different_text():
    provider = MockEmbeddingProvider(dimension=384)
    assert provider.embed_query("alpha") != provider.embed_query("beta")


def test_mock_embedding_is_unit_normalized():
    import math

    provider = MockEmbeddingProvider(dimension=384)
    vector = provider.embed_query("normalize me please")
    norm = math.sqrt(sum(x * x for x in vector))
    assert abs(norm - 1.0) < 1e-6


def test_empty_text_returns_zero_vector():
    provider = MockEmbeddingProvider(dimension=16)
    assert provider.embed_query("") == [0.0] * 16
