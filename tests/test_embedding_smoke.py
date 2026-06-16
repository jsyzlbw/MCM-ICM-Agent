import httpx
import respx

from mcm_agent.config import Settings
from mcm_agent.providers.smoke import DEFAULT_SMOKE_PROVIDERS, ProviderSmokeTester, SmokeStatus


def test_embedding_smoke_skipped_without_key(tmp_path):
    tester = ProviderSmokeTester(Settings(), workspace_root=tmp_path)
    result = tester.check("embedding")
    assert result.status == SmokeStatus.SKIPPED
    assert "Voyage" in result.detail or "embedding" in result.detail.lower()


def test_embedding_in_default_smoke_providers():
    assert "embedding" in DEFAULT_SMOKE_PROVIDERS


@respx.mock
def test_embedding_smoke_passes_with_mocked_voyage(tmp_path):
    respx.post("https://api.voyageai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})
    )
    settings = Settings(embedding_provider="voyage", voyage_api_key="vk-test")
    tester = ProviderSmokeTester(settings, workspace_root=tmp_path)
    result = tester.check("embedding")
    assert result.status == SmokeStatus.PASSED
    assert "dim=3" in result.detail
