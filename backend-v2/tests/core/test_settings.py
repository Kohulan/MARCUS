from marcus.core.settings import Settings, get_settings


def test_settings_defaults():
    s = Settings()
    assert s.max_upload_bytes == 20 * 1024 * 1024
    assert s.retention_days == 30
    assert s.enable_fake_engines is False
    assert s.trusted_proxies == []
    assert s.cookie_secure is True


def test_get_settings_cached_and_reads_env(monkeypatch, clear_settings_cache, tmp_path):
    monkeypatch.setenv("MARCUS_DATA_ROOT", str(tmp_path / "a"))
    clear_settings_cache()
    assert get_settings().data_root == tmp_path / "a"
    assert get_settings() is get_settings()


def test_seg_version_setting(monkeypatch, clear_settings_cache):
    assert Settings().seg_version == ""  # unset: the segmentation cache is never used
    monkeypatch.setenv("MARCUS_SEG_VERSION", "d0045d9")
    clear_settings_cache()
    assert get_settings().seg_version == "d0045d9"


def test_owner_ip_retention_days_setting(monkeypatch, clear_settings_cache):
    import pytest
    from pydantic import ValidationError

    assert Settings().owner_ip_retention_days == 30
    monkeypatch.setenv("MARCUS_OWNER_IP_RETENTION_DAYS", "7")
    clear_settings_cache()
    assert get_settings().owner_ip_retention_days == 7
    with pytest.raises(ValidationError):
        Settings(owner_ip_retention_days=0)


def test_annotation_settings(monkeypatch, clear_settings_cache):
    import pytest
    from pydantic import ValidationError

    s = Settings()
    assert s.annotate_enabled is False  # offered only where a worker serves q.llm
    assert (s.annotator, s.llm_url) == ("llama", "http://llama-server:8080")
    assert s.llm_timeout_s < 120  # below the annotate and rgroups steps' soft limit
    assert s.llm_model == "nuextract3-marcus-multi-v1"
    assert s.rate_limit_annotate_per_min == 5
    for bad in ("file:///etc/passwd", "llama-server:8080", "http://a b", "http://x/path"):
        with pytest.raises(ValidationError):
            Settings(llm_url=bad)
    with pytest.raises(ValidationError):
        Settings(annotator="vllm")
    monkeypatch.setenv("MARCUS_ANNOTATE_ENABLED", "1")
    clear_settings_cache()
    assert get_settings().annotate_enabled is True


def test_one_model_server_serves_annotation_and_rgroups():
    """Owner decision 2026-11-22: one model (nuextract3-marcus-multi-v1) on one llama-server
    does both jobs: one URL and one model name for both workers, and every stored result names
    it."""
    s = Settings()
    assert s.llm_url == "http://llama-server:8080"
    assert (s.llm_model, s.llm_model_version) == (
        "nuextract3-marcus-multi-v1",
        "Q8_0 llama.cpp b12554",
    )
