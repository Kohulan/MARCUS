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
